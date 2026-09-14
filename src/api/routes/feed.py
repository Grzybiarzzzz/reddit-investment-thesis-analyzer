"""Feed API route."""
from fastapi import APIRouter, Query
from src.api.app import get_db

router = APIRouter()


@router.get("/api/feed")
async def feed(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    sentiment: str | None = None,
    subreddit: str | None = None,
    min_score: int | None = None,
    ticker: str | None = None,
    sort: str = Query("newest", pattern="^(newest|score)$"),
):
    db = get_db()
    try:
        # Build query with filters
        where_clauses = ["a.llm_scored = 1"]
        params = []

        if sentiment:
            where_clauses.append("a.sentiment = ?")
            params.append(sentiment)
        if subreddit:
            where_clauses.append("COALESCE(p.subreddit, cp.subreddit) = ?")
            params.append(subreddit)
        if min_score is not None:
            where_clauses.append("a.overall_score >= ?")
            params.append(min_score)
        if ticker:
            where_clauses.append("a.ticker = ?")
            params.append(ticker.upper())

        where_sql = " AND ".join(where_clauses)

        order_sql = "a.analyzed_at DESC" if sort == "newest" else "a.overall_score DESC"

        # Count total
        count_sql = f"""
            SELECT COUNT(*) FROM analysis a
            LEFT JOIN posts p ON a.source_type = 'post' AND a.source_id = p.id
            LEFT JOIN comments c ON a.source_type = 'comment' AND a.source_id = c.id
            LEFT JOIN posts cp ON a.source_type = 'comment' AND c.post_id = cp.id
            WHERE {where_sql}
        """
        total = db.execute(count_sql, tuple(params)).fetchone()[0]

        # Fetch page
        offset = (page - 1) * limit
        query_sql = f"""
            SELECT a.*,
                   COALESCE(p.title, cp.title) as title,
                   COALESCE(p.subreddit, cp.subreddit) as subreddit,
                   COALESCE(p.url, cp.url) as reddit_url,
                   COALESCE(p.score, c.score) as post_score,
                   CASE WHEN a.source_type = 'post' THEN substr(p.body, 1, 200)
                        ELSE substr(c.body, 1, 200) END as body_snippet
            FROM analysis a
            LEFT JOIN posts p ON a.source_type = 'post' AND a.source_id = p.id
            LEFT JOIN comments c ON a.source_type = 'comment' AND a.source_id = c.id
            LEFT JOIN posts cp ON a.source_type = 'comment' AND c.post_id = cp.id
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT ? OFFSET ?
        """
        rows = db.execute(query_sql, tuple(params) + (limit, offset)).fetchall()

        pages = max(1, (total + limit - 1) // limit)

        return {
            "items": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "pages": pages,
        }
    finally:
        db.close()
