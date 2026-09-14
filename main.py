# main.py
import argparse
import os
import sys
from config.settings import (
    REDDIT_USER_AGENT, SCRAPER_DELAY,
    ANTHROPIC_API_KEY, GEMINI_API_KEY, SUBREDDITS, SORT_MODES, POSTS_PER_SORT,
    MIN_COMMENT_SCORE, MIN_COMMENT_LENGTH, FINANCIAL_KEYWORDS,
    SCORING_BACKEND, SCORING_MODEL, OLLAMA_MODEL, OLLAMA_BASE_URL,
    GEMINI_MODEL, GEMINI_FALLBACK_MODEL, GEMINI_API_KEY, GEMINI_VERTEX_PROJECT, GEMINI_VERTEX_LOCATION,
    LLM_RATE_LIMIT_DELAY,
    LLM_BATCH_SIZE, SCORE_WEIGHTS, MIN_MENTIONS, MIN_AVG_SCORE,
    MENTION_LOOKBACK_DAYS, RETRACK_COOLDOWN_DAYS, CHECKPOINTS,
    SECTOR_ETF_MAP, DB_PATH,
)
from src.db.database import Database
from src.scraper.reddit_scraper import RedditScraper
from src.analyzer.ticker_extractor import TickerExtractor
from src.analyzer.heuristic_filter import HeuristicFilter
from src.analyzer.llm_scorer import analyze_content
from src.scoring.factory import create_scorer
from src.tracker.stock_tracker import StockTracker
from src.reports.console_reporter import ConsoleReporter


def get_data_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "data", filename)


def stage_scrape(db):
    print("\n[Stage 1] Scraping Reddit...")
    scraper = RedditScraper(
        user_agent=REDDIT_USER_AGENT,
        delay=SCRAPER_DELAY,
    )
    posts, comments = scraper.scrape(
        subreddits=SUBREDDITS,
        sort_modes=SORT_MODES,
        posts_per_sort=POSTS_PER_SORT,
        min_comment_score=MIN_COMMENT_SCORE,
    )

    for post in posts:
        db.insert_post(
            id=post.id, subreddit=post.subreddit, title=post.title,
            body=post.body, score=post.score,
            url=post.url, created_at=post.created_at,
        )
    for comment in comments:
        db.insert_comment(
            id=comment.id, post_id=comment.post_id, body=comment.body,
            score=comment.score, created_at=comment.created_at,
        )
    print(f"  Scraped {len(posts)} posts and {len(comments)} comments")


def stage_analyze(db):
    print("\n[Stage 2] Analyzing content...")
    ticker_extractor = TickerExtractor(
        tickers_path=get_data_path("tickers.csv"),
        company_names_path=get_data_path("company_names.json"),
    )
    heuristic_filter = HeuristicFilter(
        ticker_extractor=ticker_extractor,
        min_length=MIN_COMMENT_LENGTH,
        financial_keywords=FINANCIAL_KEYWORDS,
    )

    scorer_kwargs = {}
    if SCORING_BACKEND == "anthropic":
        scorer_kwargs = {"api_key": ANTHROPIC_API_KEY, "model": SCORING_MODEL}
    elif SCORING_BACKEND == "ollama":
        scorer_kwargs = {"model": OLLAMA_MODEL, "base_url": OLLAMA_BASE_URL}
    elif SCORING_BACKEND == "gemini":
        scorer_kwargs = {"api_key": GEMINI_API_KEY, "model": GEMINI_MODEL,
                         "project": GEMINI_VERTEX_PROJECT, "location": GEMINI_VERTEX_LOCATION,
                         "fallback_model": GEMINI_FALLBACK_MODEL}
    scorer = create_scorer(SCORING_BACKEND, **scorer_kwargs)

    stats = analyze_content(db, heuristic_filter, scorer, SCORE_WEIGHTS, LLM_BATCH_SIZE, LLM_RATE_LIMIT_DELAY)
    print(f"  Analyzed {stats['posts_analyzed']} posts, {stats['comments_analyzed']} comments")
    print(f"  Filtered out: {stats['filtered_out']}, LLM scored: {stats['scored']}")


def stage_track(db):
    print("\n[Stage 3] Tracking stocks...")
    tracker = StockTracker(
        db=db,
        min_mentions=MIN_MENTIONS,
        min_avg_score=MIN_AVG_SCORE,
        mention_lookback_days=MENTION_LOOKBACK_DAYS,
        retrack_cooldown_days=RETRACK_COOLDOWN_DAYS,
        checkpoints=CHECKPOINTS,
        sector_etf_map=SECTOR_ETF_MAP,
    )
    discoveries = tracker.discover()
    checkpoint_updates = tracker.update_checkpoints()
    print(f"  New discoveries: {len(discoveries)}")
    print(f"  Checkpoint updates: {len(checkpoint_updates)}")

    completed = db.get_active_tracked_stocks()
    reporter = ConsoleReporter()
    reporter.print_report(discoveries, checkpoint_updates, completed)


def run_pipeline(stages):
    print("Starting Reddit Stock Analyzer pipeline...")
    print(f"  Stages: {', '.join(stages)}")

    db = Database(DB_PATH)
    db.initialize()

    if "scrape" in stages:
        stage_scrape(db)
    if "analyze" in stages:
        stage_analyze(db)
    if "track" in stages:
        stage_track(db)

    db.close()
    print("\nPipeline complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reddit Stock Market Analyzer")
    parser.add_argument("command", nargs="?", default="all",
                        choices=["all", "scrape", "analyze", "track", "dashboard"],
                        help="Which stage to run (default: all)")
    args = parser.parse_args()

    if args.command == "all":
        run_pipeline(["scrape", "analyze", "track"])
    elif args.command == "scrape":
        run_pipeline(["scrape"])
    elif args.command == "analyze":
        run_pipeline(["analyze"])
    elif args.command == "track":
        run_pipeline(["track"])
    elif args.command == "dashboard":
        from src.api.app import main as dashboard_main
        dashboard_main()
