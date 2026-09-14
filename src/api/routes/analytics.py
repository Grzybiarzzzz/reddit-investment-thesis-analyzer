"""Analytics API route."""
from fastapi import APIRouter, Query, HTTPException
from src.api.app import get_db

router = APIRouter()


@router.get("/api/analytics")
async def analytics(days: int = Query(30, ge=1, le=365),
                    checkpoint: int = Query(7)):
    if checkpoint not in (7, 14, 30, 90):
        raise HTTPException(status_code=422, detail="Checkpoint must be 7, 14, 30, or 90")
    db = get_db()
    try:
        date_filter = f"-{days} days"

        # Score distribution (buckets of 10)
        score_rows = db.execute("""
            SELECT (overall_score / 10) * 10 as bucket, COUNT(*) as count
            FROM analysis
            WHERE llm_scored = 1 AND analyzed_at >= datetime('now', ?)
            GROUP BY bucket
            ORDER BY bucket
        """, (date_filter,)).fetchall()
        score_distribution = [
            {"bucket": f"{d['bucket']}-{d['bucket'] + 9}", "count": d["count"]}
            for d in [dict(r) for r in score_rows]
        ]

        # Sentiment by subreddit (posts + comments via parent post)
        sentiment_rows = db.execute("""
            SELECT sub, SUM(bull) as bull, SUM(bear) as bear, SUM(neutral) as neutral
            FROM (
                SELECT p.subreddit as sub,
                       CASE WHEN a.sentiment = 'bull' THEN 1 ELSE 0 END as bull,
                       CASE WHEN a.sentiment = 'bear' THEN 1 ELSE 0 END as bear,
                       CASE WHEN a.sentiment = 'neutral' THEN 1 ELSE 0 END as neutral
                FROM analysis a
                JOIN posts p ON a.source_type = 'post' AND a.source_id = p.id
                WHERE a.llm_scored = 1 AND a.analyzed_at >= datetime('now', ?)
                UNION ALL
                SELECT p.subreddit as sub,
                       CASE WHEN a.sentiment = 'bull' THEN 1 ELSE 0 END as bull,
                       CASE WHEN a.sentiment = 'bear' THEN 1 ELSE 0 END as bear,
                       CASE WHEN a.sentiment = 'neutral' THEN 1 ELSE 0 END as neutral
                FROM analysis a
                JOIN comments c ON a.source_type = 'comment' AND a.source_id = c.id
                JOIN posts p ON c.post_id = p.id
                WHERE a.llm_scored = 1 AND a.analyzed_at >= datetime('now', ?)
            )
            GROUP BY sub
            ORDER BY (bull + bear + neutral) DESC
        """, (date_filter, date_filter)).fetchall()
        sentiment_by_subreddit = [{"subreddit": r["sub"], "bull": r["bull"], "bear": r["bear"], "neutral": r["neutral"]} for r in sentiment_rows]

        # One discovery per observation, using the score stored at discovery.
        # Source-level joins would overweight popular stocks and admit future text.
        accuracy_rows = db.execute(f"""
            SELECT CASE WHEN avg_quality_score >= 70 THEN '70-100'
                        WHEN avg_quality_score >= 50 THEN '50-70'
                        ELSE '0-50' END AS score_range,
                   COUNT(*) AS count,
                   ROUND(AVG((price_{checkpoint}d / discovery_price - 1) * 100), 4) AS avg_return
            FROM tracked_stocks
            WHERE discovery_price > 0 AND price_{checkpoint}d IS NOT NULL
            GROUP BY score_range ORDER BY score_range DESC
        """).fetchall()
        accuracy_by_score = [dict(r) for r in accuracy_rows]

        # Subreddit leaderboard (posts + comments via parent post)
        leaderboard_rows = db.execute("""
            SELECT sub as subreddit, ROUND(AVG(score), 0) as avg_score, COUNT(*) as pick_count
            FROM (
                SELECT p.subreddit as sub, a.overall_score as score
                FROM analysis a
                JOIN posts p ON a.source_type = 'post' AND a.source_id = p.id
                WHERE a.llm_scored = 1 AND a.analyzed_at >= datetime('now', ?)
                UNION ALL
                SELECT p.subreddit as sub, a.overall_score as score
                FROM analysis a
                JOIN comments c ON a.source_type = 'comment' AND a.source_id = c.id
                JOIN posts p ON c.post_id = p.id
                WHERE a.llm_scored = 1 AND a.analyzed_at >= datetime('now', ?)
            )
            GROUP BY sub
            ORDER BY avg_score DESC
        """, (date_filter, date_filter)).fetchall()
        subreddit_leaderboard = [dict(r) for r in leaderboard_rows]

        # Daily volume
        volume_rows = db.execute("""
            SELECT date(scraped_at) as date,
                   COUNT(*) as posts
            FROM posts
            WHERE scraped_at >= datetime('now', ?)
            GROUP BY date(scraped_at)
            ORDER BY date
        """, (date_filter,)).fetchall()
        daily_volume = [dict(r) for r in volume_rows]

        # Daily comment volume
        comment_volume_rows = db.execute("""
            SELECT date(scraped_at) as date,
                   COUNT(*) as comments
            FROM comments
            WHERE scraped_at >= datetime('now', ?)
            GROUP BY date(scraped_at)
            ORDER BY date
        """, (date_filter,)).fetchall()
        daily_comment_volume = [dict(r) for r in comment_volume_rows]

        return {
            "score_distribution": score_distribution,
            "sentiment_by_subreddit": sentiment_by_subreddit,
            "accuracy_by_score": accuracy_by_score,
            "checkpoint_days": checkpoint,
            "measurement_note": "Nominal horizons; legacy checkpoint observation times are unknown.",
            "subreddit_leaderboard": subreddit_leaderboard,
            "daily_volume": daily_volume,
            "daily_comment_volume": daily_comment_volume,
        }
    finally:
        db.close()
