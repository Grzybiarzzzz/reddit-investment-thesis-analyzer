# src/analyzer/llm_scorer.py
import logging
import time
from src.db.database import Database
from src.analyzer.heuristic_filter import HeuristicFilter
from src.scoring.scorer_interface import ScorerInterface

logger = logging.getLogger(__name__)

# ETFs and benchmarks that should not be tracked as individual stock picks
EXCLUDED_TICKERS = {
    # Broad market ETFs
    "SPY", "QQQ", "IWM", "DIA", "VOO", "VTI", "VXUS", "VEA", "VWO",
    # Sector ETFs
    "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE",
    # Bond / commodity / money market ETFs
    "TLT", "BND", "GLD", "SLV", "IAU", "SGOV", "SHY", "AGG", "HYG", "LQD",
    # Leveraged / inverse ETFs
    "TQQQ", "SQQQ", "SPXU", "SPXL", "SVXY", "UVXY",
}

# Max tickers per post — posts listing more are likely portfolio dumps, not theses
MAX_TICKERS_PER_POST = 5

# LLM often returns alternate ticker symbols — map to canonical form
TICKER_ALIASES = {
    "GOOG": "GOOGL",
    "BRK.A": "BRK-B",
    "BRK/A": "BRK-B",
    "BRK/B": "BRK-B",
}


def _validate_and_filter_tickers(
    tickers: list[str],
    valid_tickers: set[str],
    company_map_lower: dict[str, str],
) -> list[str]:
    """Validate LLM-returned tickers against known ticker list, normalize names."""
    result = []
    seen = set()
    for raw in tickers:
        raw_stripped = raw.strip()
        if not raw_stripped:
            continue

        # Normalize aliases (e.g. GOOG -> GOOGL)
        upper = TICKER_ALIASES.get(raw_stripped.upper(), raw_stripped.upper())
        if upper in valid_tickers and upper not in seen:
            seen.add(upper)
            result.append(upper)
            continue

        # Try company name -> ticker mapping
        lower = raw_stripped.lower()
        if lower in company_map_lower and company_map_lower[lower] not in seen:
            canonical = company_map_lower[lower]
            seen.add(canonical)
            result.append(canonical)
            continue

        # Unknown ticker — skip it
        logger.debug("Dropping unrecognized ticker from LLM: %s", raw_stripped)

    return result


def analyze_content(db: Database, heuristic_filter: HeuristicFilter,
                    scorer: ScorerInterface, weights: dict[str, float],
                    batch_size: int, rate_limit_delay: float = 0) -> dict:
    stats = {"posts_analyzed": 0, "comments_analyzed": 0, "filtered_out": 0, "scored": 0}

    # Get ticker validation data from the heuristic filter's extractor
    valid_tickers = heuristic_filter.ticker_extractor.valid_tickers
    company_map_lower = heuristic_filter.ticker_extractor.company_map_lower

    # Gather all unanalyzed content
    posts = db.get_unanalyzed_posts()
    comments = db.get_unanalyzed_comments()

    items = []
    for post in posts:
        text = f"{post['title']} {post.get('body', '')}"
        items.append(("post", post["id"], text))
    for comment in comments:
        post_title = comment.get("post_title", "")
        text = f"[Post: {post_title}] {comment['body']}" if post_title else comment["body"]
        items.append(("comment", comment["id"], text))

    print(f"    Total unanalyzed: {len(items)}")

    # Pass 1: Heuristic filter
    survivors = []
    for source_type, source_id, text in items:
        result = heuristic_filter.apply(text)
        if result.passed:
            survivors.append((source_type, source_id, text, result.tickers))
        else:
            db.mark_processed(source_type, source_id)
            stats["filtered_out"] += 1
    db.commit()

    total_batches = (len(survivors) + batch_size - 1) // batch_size if survivors else 0
    print(f"    Passed filter: {len(survivors)} ({total_batches} batches of {batch_size})")

    if not survivors:
        return stats

    # Pass 2: LLM scoring in batches
    start_time = time.time()
    for i in range(0, len(survivors), batch_size):
        batch = survivors[i:i + batch_size]
        batch_num = i // batch_size + 1
        items_done = min(i + batch_size, len(survivors))
        elapsed = time.time() - start_time

        if batch_num > 1:
            avg_per_batch = elapsed / (batch_num - 1)
            remaining = (total_batches - batch_num + 1) * avg_per_batch
            mins_left = remaining / 60
            print(f"    Scoring batch {batch_num}/{total_batches} ({items_done}/{len(survivors)} items) ~{mins_left:.0f}min left", flush=True)
        else:
            print(f"    Scoring batch {batch_num}/{total_batches} ({items_done}/{len(survivors)} items)...", flush=True)

        texts = [text for _, _, text, _ in batch]
        score_results = scorer.score_batch(texts)

        if not score_results:
            logger.warning("Batch %d returned no results (scoring may have failed)", batch_num)
            continue

        for j, (source_type, source_id, text, filter_tickers) in enumerate(batch):
            if j >= len(score_results):
                break

            per_text_result = score_results[j]

            # Collect all tickers: from LLM per-ticker scores + heuristic filter
            llm_tickers_with_scores = {}
            for score in per_text_result.ticker_scores:
                for t in score.tickers_mentioned:
                    validated = _validate_and_filter_tickers(
                        [t], valid_tickers, company_map_lower
                    )
                    for vt in validated:
                        if vt not in EXCLUDED_TICKERS:
                            llm_tickers_with_scores[vt] = score

            # Merge: LLM tickers get their own scores; heuristic-only tickers
            # are skipped (no LLM thesis = no score to record)
            all_tickers = set(llm_tickers_with_scores.keys())

            # Cap tickers per post to prevent portfolio dump inflation
            if len(all_tickers) > MAX_TICKERS_PER_POST:
                # Keep the highest-scored tickers
                sorted_tickers = sorted(
                    all_tickers,
                    key=lambda t: llm_tickers_with_scores[t].calculate_overall(weights)
                    if t in llm_tickers_with_scores else 0,
                    reverse=True,
                )
                all_tickers = set(sorted_tickers[:MAX_TICKERS_PER_POST])
                logger.info(
                    "Capped tickers for %s:%s from %d to %d",
                    source_type, source_id, len(sorted_tickers), MAX_TICKERS_PER_POST,
                )

            for ticker in all_tickers:
                score = llm_tickers_with_scores[ticker]
                overall = score.calculate_overall(weights)

                db.insert_analysis(
                    source_type=source_type,
                    source_id=source_id,
                    ticker=ticker,
                    sentiment=score.sentiment,
                    reasoning_score=score.reasoning_score,
                    specificity_score=score.specificity_score,
                    novelty_score=score.novelty_score,
                    credibility_score=score.credibility_score,
                    overall_score=overall,
                    reasoning_summary=score.reasoning_summary,
                    passed_heuristic=True,
                    llm_scored=True,
                )

            db.mark_processed(source_type, source_id)

            if source_type == "post":
                stats["posts_analyzed"] += 1
            else:
                stats["comments_analyzed"] += 1
            stats["scored"] += 1

        # Rate limit delay between batches (for API quota limits)
        if rate_limit_delay > 0 and i + batch_size < len(survivors):
            time.sleep(rate_limit_delay)

    # mark_processed does not commit on its own; without this, items after the
    # last stored assessment would be scored again on the next run.
    db.commit()

    total_time = time.time() - start_time
    print(f"    Scoring complete in {total_time/60:.1f} minutes")

    return stats
