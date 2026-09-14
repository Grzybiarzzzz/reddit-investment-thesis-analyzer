"""Portfolio simulation API route."""
import statistics as st
from fastapi import APIRouter, Query, HTTPException
from src.api.app import get_db
from config.settings import MIN_AVG_SCORE

router = APIRouter()


def _compute_checkpoint(filtered: list[dict], days: int) -> dict | None:
    """Compute checkpoint data for a list of filtered stocks at given days."""
    price_key = f"price_{days}d"
    spy_key = f"spy_price_{days}d"
    sector_key = f"sector_etf_price_{days}d"
    stocks_at_cp = []
    for s in filtered:
        if not s.get(price_key) or not s.get("discovery_price") or s["discovery_price"] <= 0:
            continue
        stock_ret = (s[price_key] - s["discovery_price"]) / s["discovery_price"]
        # Compare only complete stock/benchmark pairs; missing is not zero return.
        if not s.get(spy_key) or not s.get("spy_price_discovery") or s["spy_price_discovery"] <= 0:
            continue
        spy_ret = 0
        if s.get(spy_key) and s.get("spy_price_discovery") and s["spy_price_discovery"] > 0:
            spy_ret = (s[spy_key] - s["spy_price_discovery"]) / s["spy_price_discovery"]
        sector_ret = None
        if s.get(sector_key) and s.get("sector_etf_price_discovery") and s["sector_etf_price_discovery"] > 0:
            sector_ret = (s[sector_key] - s["sector_etf_price_discovery"]) / s["sector_etf_price_discovery"]
        stocks_at_cp.append({
            "ticker": s["ticker"],
            "stock_id": s["id"],
            "observed_at": s.get(f"observed_at_{days}d"),
            "stock_return": round(stock_ret * 100, 2),
            "spy_return": round(spy_ret * 100, 2),
            "sector_return": round(sector_ret * 100, 2) if sector_ret is not None else None,
            "alpha": round((stock_ret - spy_ret) * 100, 2),
        })

    if not stocks_at_cp:
        return None

    n = len(stocks_at_cp)
    invested = n * 1000
    portfolio_value = sum(1000 * (1 + s["stock_return"] / 100) for s in stocks_at_cp)
    spy_value = sum(1000 * (1 + s["spy_return"] / 100) for s in stocks_at_cp)
    wins = sum(1 for s in stocks_at_cp if s["alpha"] > 0)
    return {
        "count": n,
        "total": len(stocks_at_cp),
        "invested": invested,
        "portfolio_value": round(portfolio_value, 2),
        "spy_value": round(spy_value, 2),
        "pnl": round(portfolio_value - invested, 2),
        "spy_pnl": round(spy_value - invested, 2),
        "avg_return": round(sum(s["stock_return"] for s in stocks_at_cp) / n, 2),
        "avg_spy_return": round(sum(s["spy_return"] for s in stocks_at_cp) / n, 2),
        "win_rate": round(wins / n * 100, 1),
        "wins": wins,
        "stocks": sorted(stocks_at_cp, key=lambda x: x["stock_return"], reverse=True),
    }


@router.get("/api/portfolio")
async def portfolio_simulation(
    min_score: float = Query(0, ge=0, le=100),
    min_mentions: int = Query(0, ge=0),
    ticker: str = Query(""),
    discovered_after: str = Query(""),
    discovered_before: str = Query(""),
    sentiment: str = Query(""),
    checkpoint: int = Query(7),
):
    if checkpoint not in (7, 14, 30, 90):
        raise HTTPException(status_code=422, detail="Checkpoint must be 7, 14, 30, or 90")
    db = get_db()
    try:
        # Fetch all tracked stocks
        rows = db.execute(
            "SELECT * FROM tracked_stocks ORDER BY discovered_at DESC"
        ).fetchall()
        all_stocks = [dict(r) for r in rows]

        # Historical records without a snapshot remain unknown. Later posts
        # must not be used to invent a sentiment at an earlier discovery.
        for s in all_stocks:
            s["_dominant_sentiment"] = s.get("discovery_sentiment") or "unknown"

        # Date range for the response (so frontend knows the bounds)
        date_range = db.execute(
            "SELECT MIN(date(discovered_at)) as earliest, MAX(date(discovered_at)) as latest FROM tracked_stocks"
        ).fetchone()
        earliest_date = date_range["earliest"] if date_range else None
        latest_date = date_range["latest"] if date_range else None

        # Apply filters (except min_score — applied below; we need unfiltered-by-score for the curve)
        base_filtered = all_stocks
        if min_mentions > 0:
            base_filtered = [s for s in base_filtered if (s.get("mention_count") or 0) >= min_mentions]
        if ticker:
            t = ticker.upper()
            base_filtered = [s for s in base_filtered if t in s.get("ticker", "")]
        if discovered_after:
            base_filtered = [s for s in base_filtered if (s.get("discovered_at") or "") >= discovered_after]
        if discovered_before:
            base_filtered = [s for s in base_filtered if (s.get("discovered_at") or "") <= discovered_before + "T23:59:59"]
        if sentiment:
            base_filtered = [s for s in base_filtered if s["_dominant_sentiment"] == sentiment]

        # Apply min_score filter for main results
        filtered = base_filtered
        if min_score > 0:
            filtered = [s for s in filtered if (s.get("avg_quality_score") or 0) >= min_score]

        # Score-profit curve: sweep min_score from 0 to 100 in steps of 5
        score_profit_curve = {}
        for days in [7, 14, 30, 90]:
            curve_points = []
            best_score = 0
            best_return = None
            for threshold in range(50, 101, 5):
                subset = [s for s in base_filtered if (s.get("avg_quality_score") or 0) >= threshold]
                cp = _compute_checkpoint(subset, days)
                avg_ret = cp["avg_return"] if cp else None
                count = cp["count"] if cp else 0
                curve_points.append({"min_score": threshold, "avg_return": avg_ret, "count": count})
                if avg_ret is not None and (best_return is None or avg_ret > best_return):
                    best_return = avg_ret
                    best_score = threshold
            score_profit_curve[str(days)] = {
                "points": curve_points,
                "best_score": best_score,
                "best_return": best_return,
            }

        # Per-checkpoint simulation
        checkpoints = {}
        for days in [7, 14, 30, 90]:
            cp = _compute_checkpoint(filtered, days)
            if cp:
                cp["total"] = len(filtered)
            checkpoints[days] = cp

        # Individual stock rows for the table (with computed return/alpha from latest checkpoint)
        stock_rows = []
        for s in filtered:
            ret = None
            alpha = None
            spy_ret_pct = None
            cp_days = None
            for days in [90, 30, 14, 7]:
                price_key = f"price_{days}d"
                spy_key = f"spy_price_{days}d"
                if s.get(price_key) and s.get("discovery_price") and s["discovery_price"] > 0:
                    ret = round((s[price_key] - s["discovery_price"]) / s["discovery_price"] * 100, 2)
                    if s.get(spy_key) and s.get("spy_price_discovery") and s["spy_price_discovery"] > 0:
                        spy_ret_pct = round((s[spy_key] - s["spy_price_discovery"]) / s["spy_price_discovery"] * 100, 2)
                        alpha = round(ret - spy_ret_pct, 2)
                    cp_days = days
                    break
            stock_rows.append({
                "ticker": s["ticker"],
                "discovery_price": s["discovery_price"],
                "mention_count": s.get("mention_count"),
                "avg_quality_score": s.get("avg_quality_score"),
                "sentiment": s.get("_dominant_sentiment", "neutral"),
                "return_pct": ret,
                "alpha_pct": alpha,
                "checkpoint_days": cp_days,
                "status": s.get("status"),
                "discovered_at": s.get("discovered_at"),
            })

        # ---- Insights / Analytics ----
        # All aggregate insights use the selected nominal horizon and paired benchmarks.
        cp = _compute_checkpoint(filtered, checkpoint)
        by_id = {s["id"]: s for s in filtered}
        returns_list = []
        for result in (cp["stocks"] if cp else []):
            source = by_id[result["stock_id"]]
            returns_list.append({
                "return_pct": result["stock_return"], "alpha": result["alpha"],
                "score": source.get("avg_quality_score") or 0,
                "mention_count": source.get("mention_count") or 0,
                "ticker": source["ticker"], "stock_id": source["id"],
                "sentiment": source["_dominant_sentiment"],
            })

        insights = {}

        if returns_list:
            rets = [r["return_pct"] for r in returns_list]
            alphas = [r["alpha"] for r in returns_list]
            n = len(rets)

            # 1. Return distribution (histogram buckets)
            buckets = [
                {"label": "< -20%", "min": -999, "max": -20},
                {"label": "-20% to -10%", "min": -20, "max": -10},
                {"label": "-10% to -5%", "min": -10, "max": -5},
                {"label": "-5% to 0%", "min": -5, "max": 0},
                {"label": "0% to +5%", "min": 0, "max": 5},
                {"label": "+5% to +10%", "min": 5, "max": 10},
                {"label": "+10% to +20%", "min": 10, "max": 20},
                {"label": "> +20%", "min": 20, "max": 999},
            ]
            distribution = []
            for b in buckets:
                count = sum(1 for r in rets if b["min"] <= r < b["max"])
                # Include the top edge for the last bucket
                if b["max"] == 999:
                    count = sum(1 for r in rets if r >= b["min"])
                distribution.append({"label": b["label"], "count": count})
            insights["return_distribution"] = distribution

            # Descriptive statistics only: these observations are selected,
            # correlated, and lack the design required for a significance claim.
            insights["statistics"] = {
                "n": n,
                "mean_alpha": round(st.mean(alphas), 2),
                "std_alpha": round(st.stdev(alphas), 2) if n > 1 else None,
                "win_rate": round(100 * sum(a > 0 for a in alphas) / n, 1),
                "median_return": round(st.median(rets), 2),
                "max_return": round(max(rets), 2),
                "min_return": round(min(rets), 2),
            }

            # 3. Score buckets vs return
            score_buckets = [
                {"label": "65-70", "min": 65, "max": 70},
                {"label": "70-75", "min": 70, "max": 75},
                {"label": "75-80", "min": 75, "max": 80},
                {"label": "80+", "min": 80, "max": 999},
            ]
            score_vs_return = []
            for b in score_buckets:
                items = [r for r in returns_list if b["min"] <= r["score"] < b["max"]]
                if b["max"] == 999:
                    items = [r for r in returns_list if r["score"] >= b["min"]]
                if items:
                    score_vs_return.append({
                        "range": b["label"],
                        "count": len(items),
                        "avg_return": round(sum(i["return_pct"] for i in items) / len(items), 2),
                        "avg_alpha": round(sum(i["alpha"] for i in items) / len(items), 2),
                        "win_rate": round(sum(1 for i in items if i["alpha"] > 0) / len(items) * 100, 1),
                    })
                else:
                    score_vs_return.append({
                        "range": b["label"],
                        "count": 0,
                        "avg_return": None,
                        "avg_alpha": None,
                        "win_rate": None,
                    })
            insights["score_vs_return"] = score_vs_return

            # 4. Mention count vs return
            mention_buckets = [
                {"label": "5-7", "min": 5, "max": 8},
                {"label": "8-12", "min": 8, "max": 13},
                {"label": "13-20", "min": 13, "max": 21},
                {"label": "20+", "min": 21, "max": 9999},
            ]
            mentions_vs_return = []
            for b in mention_buckets:
                items = [r for r in returns_list if b["min"] <= r["mention_count"] < b["max"]]
                if b["max"] == 9999:
                    items = [r for r in returns_list if r["mention_count"] >= b["min"]]
                if items:
                    mentions_vs_return.append({
                        "range": b["label"],
                        "count": len(items),
                        "avg_return": round(sum(i["return_pct"] for i in items) / len(items), 2),
                        "avg_alpha": round(sum(i["alpha"] for i in items) / len(items), 2),
                    })
                else:
                    mentions_vs_return.append({
                        "range": b["label"],
                        "count": 0,
                        "avg_return": None,
                        "avg_alpha": None,
                    })
            insights["mentions_vs_return"] = mentions_vs_return

            # 5. Sentiment accuracy (using pre-computed dominant sentiments)
            sentiment_accuracy = {"bull": {"count": 0, "avg_return": 0, "wins": 0},
                                  "bear": {"count": 0, "avg_return": 0, "wins": 0},
                                  "neutral": {"count": 0, "avg_return": 0, "wins": 0},
                                  "unknown": {"count": 0, "avg_return": 0, "wins": 0}}
            for r in returns_list:
                sent = r["sentiment"]
                sentiment_accuracy[sent]["count"] += 1
                sentiment_accuracy[sent]["avg_return"] += r["return_pct"]
                if (sent == "bull" and r["return_pct"] > 0) or \
                   (sent == "bear" and r["return_pct"] < 0):
                    sentiment_accuracy[sent]["wins"] += 1

            for sent in sentiment_accuracy:
                sa = sentiment_accuracy[sent]
                if sa["count"] > 0:
                    sa["avg_return"] = round(sa["avg_return"] / sa["count"], 2)
                    sa["accuracy"] = round(sa["wins"] / sa["count"] * 100, 1) if sent in ("bull", "bear") else None
                else:
                    sa["avg_return"] = None
                    sa["accuracy"] = None
            insights["sentiment_accuracy"] = sentiment_accuracy

            # 6. Sector concentration
            sector_counts = {}
            for s in filtered:
                etf = s.get("sector_etf") or "Unknown"
                if etf not in sector_counts:
                    sector_counts[etf] = {"count": 0, "returns": []}
                sector_counts[etf]["count"] += 1
                # Find return for this ticker
                for r in returns_list:
                    if r["ticker"] == s["ticker"]:
                        sector_counts[etf]["returns"].append(r["return_pct"])
                        break

            sector_breakdown = []
            for etf, data in sorted(sector_counts.items(), key=lambda x: x[1]["count"], reverse=True):
                avg_ret = round(sum(data["returns"]) / len(data["returns"]), 2) if data["returns"] else None
                sector_breakdown.append({
                    "sector_etf": etf,
                    "count": data["count"],
                    "pct_of_portfolio": round(data["count"] / len(filtered) * 100, 1),
                    "avg_return": avg_ret,
                })
            insights["sector_breakdown"] = sector_breakdown

        return {
            "checkpoint_days": checkpoint,
            "measurement_note": "Exploratory price returns. Nominal horizons may be delayed; legacy observation times and discovery sentiment are unknown. Benchmark differences are not risk-adjusted alpha.",
            "total_tracked": len(all_stocks),
            "filtered_count": len(filtered),
            "checkpoints": checkpoints,
            "stocks": stock_rows,
            "earliest_date": earliest_date,
            "latest_date": latest_date,
            "insights": insights,
            "default_min_score": MIN_AVG_SCORE,
            "score_profit_curve": score_profit_curve,
        }
    finally:
        db.close()
