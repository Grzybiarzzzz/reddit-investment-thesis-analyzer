"""Dashboard API route."""
from fastapi import APIRouter
from src.api.app import get_db, data_as_of, PERMALINK_SQL

router = APIRouter()


@router.get("/api/dashboard")
async def dashboard():
    db = get_db()
    try:
        # KPIs
        tracked_count = db.execute("SELECT COUNT(*) FROM tracked_stocks").fetchone()[0]
        active_count = db.execute("SELECT COUNT(*) FROM tracked_stocks WHERE status = 'active'").fetchone()[0]
        # "Today" is the latest day with data, so a frozen snapshot is not empty.
        as_of = data_as_of(db)
        posts_today = db.execute(
            "SELECT COUNT(*) FROM posts WHERE scraped_at >= date(?)", (as_of,)
        ).fetchone()[0]
        scored_today = db.execute(
            "SELECT COUNT(*) FROM analysis WHERE llm_scored = 1 AND analyzed_at >= date(?)", (as_of,)
        ).fetchone()[0]
        comments_today = db.execute(
            "SELECT COUNT(*) FROM comments WHERE scraped_at >= date(?)", (as_of,)
        ).fetchone()[0]

        # Win rate: stocks where return > SPY return at latest checkpoint
        completed = db.execute(
            "SELECT * FROM tracked_stocks WHERE price_7d IS NOT NULL"
        ).fetchall()
        wins = 0
        total_with_data = 0
        total_alpha = 0.0
        for row in completed:
            s = dict(row)
            # Use the latest available checkpoint
            for days in [7]:
                price_key = f"price_{days}d"
                spy_key = f"spy_price_{days}d"
                if s.get(price_key) and s.get(spy_key) and s.get("spy_price_discovery") and s.get("discovery_price"):
                    stock_ret = (s[price_key] - s["discovery_price"]) / s["discovery_price"]
                    spy_ret = (s[spy_key] - s["spy_price_discovery"]) / s["spy_price_discovery"] if s["spy_price_discovery"] else 0
                    alpha = stock_ret - spy_ret
                    total_alpha += alpha
                    total_with_data += 1
                    if alpha > 0:
                        wins += 1
                    break

        win_rate = wins / total_with_data if total_with_data else None
        avg_alpha = (total_alpha / total_with_data * 100) if total_with_data else None

        # Per-checkpoint portfolio simulation: equal-weight $1000 per stock
        portfolio = {}
        best_pick = None
        worst_pick = None
        total_return_sum = 0.0
        total_return_count = 0
        total_tracked = len(completed) + db.execute(
            "SELECT COUNT(*) FROM tracked_stocks WHERE price_7d IS NULL"
        ).fetchone()[0]
        for days in [7, 14, 30, 90]:
            price_key = f"price_{days}d"
            spy_key = f"spy_price_{days}d"
            stocks_at_cp = []
            for row in completed:
                s = dict(row)
                if s.get(price_key) and s.get("discovery_price") and s["discovery_price"] > 0:
                    stock_ret = (s[price_key] - s["discovery_price"]) / s["discovery_price"]
                    if not s.get(spy_key) or not s.get("spy_price_discovery"):
                        continue
                    spy_ret = 0
                    if s.get(spy_key) and s.get("spy_price_discovery") and s["spy_price_discovery"] > 0:
                        spy_ret = (s[spy_key] - s["spy_price_discovery"]) / s["spy_price_discovery"]
                    stocks_at_cp.append({
                        "ticker": s["ticker"],
                        "stock_return": round(stock_ret * 100, 2),
                        "spy_return": round(spy_ret * 100, 2),
                        "alpha": round((stock_ret - spy_ret) * 100, 2),
                    })
            if stocks_at_cp:
                n = len(stocks_at_cp)
                invested = n * 1000  # $1000 per stock
                portfolio_value = sum(1000 * (1 + s["stock_return"] / 100) for s in stocks_at_cp)
                spy_value = sum(1000 * (1 + s["spy_return"] / 100) for s in stocks_at_cp)
                avg_ret = sum(s["stock_return"] for s in stocks_at_cp) / n
                avg_spy = sum(s["spy_return"] for s in stocks_at_cp) / n
                portfolio[days] = {
                    "count": n,
                    "total": total_tracked,
                    "invested": invested,
                    "portfolio_value": round(portfolio_value, 2),
                    "spy_value": round(spy_value, 2),
                    "pnl": round(portfolio_value - invested, 2),
                    "spy_pnl": round(spy_value - invested, 2),
                    "avg_return": round(avg_ret, 2),
                    "avg_spy_return": round(avg_spy, 2),
                }

        # Best/worst picks (by latest checkpoint return)
        for row in completed:
            s = dict(row)
            for days in [7]:
                price_key = f"price_{days}d"
                if s.get(price_key) and s.get("discovery_price") and s["discovery_price"] > 0:
                    ret = (s[price_key] - s["discovery_price"]) / s["discovery_price"] * 100
                    total_return_sum += ret
                    total_return_count += 1
                    if best_pick is None or ret > best_pick["return_pct"]:
                        best_pick = {"ticker": s["ticker"], "return_pct": round(ret, 1)}
                    if worst_pick is None or ret < worst_pick["return_pct"]:
                        worst_pick = {"ticker": s["ticker"], "return_pct": round(ret, 1)}
                    break

        avg_return = round(total_return_sum / total_return_count, 1) if total_return_count else None

        kpis = {
            "tracked_count": tracked_count,
            "active_count": active_count,
            "avg_alpha_30d": round(avg_alpha, 1) if avg_alpha is not None else None,
            "checkpoint_days": 7,
            "posts_today": posts_today,
            "comments_today": comments_today,
            "scored_today": scored_today,
            "win_rate": round(win_rate, 2) if win_rate is not None else None,
            "wins": wins,
            "total_with_data": total_with_data,
            "avg_return": avg_return,
            "best_pick": best_pick,
            "worst_pick": worst_pick,
            "portfolio": portfolio,
        }

        # Active stocks
        active_rows = db.execute(
            "SELECT * FROM tracked_stocks WHERE status = 'active' ORDER BY discovered_at DESC LIMIT 10"
        ).fetchall()
        active_stocks = []
        for row in active_rows:
            s = dict(row)
            checkpoints_done = []
            for days in [7, 14, 30, 90]:
                if s.get(f"price_{days}d") is not None:
                    checkpoints_done.append(days)
            active_stocks.append({**s, "checkpoints_done": checkpoints_done})

        # Recent feed (top 5 scored today)
        feed_rows = db.execute(f"""
            SELECT a.*,
                   COALESCE(p.title, cp.title) as title,
                   COALESCE(p.subreddit, cp.subreddit) as subreddit,
                   {PERMALINK_SQL} as reddit_url
            FROM analysis a
            LEFT JOIN posts p ON a.source_type = 'post' AND a.source_id = p.id
            LEFT JOIN comments c ON a.source_type = 'comment' AND a.source_id = c.id
            LEFT JOIN posts cp ON a.source_type = 'comment' AND c.post_id = cp.id
            WHERE a.llm_scored = 1
            ORDER BY a.analyzed_at DESC, a.overall_score DESC
            LIMIT 5
        """).fetchall()
        recent_feed = [dict(r) for r in feed_rows]

        # Top tickers (last 7 days)
        ticker_rows = db.execute("""
            SELECT ticker,
                   COUNT(*) as mention_count,
                   ROUND(AVG(overall_score), 0) as avg_score,
                   SUM(CASE WHEN sentiment = 'bull' THEN 1 ELSE 0 END) as bull_count,
                   SUM(CASE WHEN sentiment = 'bear' THEN 1 ELSE 0 END) as bear_count,
                   SUM(CASE WHEN sentiment = 'neutral' THEN 1 ELSE 0 END) as neutral_count
            FROM analysis
            WHERE llm_scored = 1 AND analyzed_at >= datetime(?, '-7 days')
            GROUP BY ticker
            ORDER BY mention_count DESC
            LIMIT 10
        """, (as_of,)).fetchall()
        top_tickers = []
        for r in ticker_rows:
            d = dict(r)
            # Determine dominant sentiment
            sentiments = {"bull": d["bull_count"], "bear": d["bear_count"], "neutral": d["neutral_count"]}
            d["dominant_sentiment"] = max(sentiments, key=sentiments.get)
            top_tickers.append(d)

        return {
            "as_of": as_of,
            "kpis": kpis,
            "active_stocks": active_stocks,
            "recent_feed": recent_feed,
            "top_tickers": top_tickers,
        }
    finally:
        db.close()
