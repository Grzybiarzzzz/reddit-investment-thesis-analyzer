"""Tracked stocks API route."""
from fastapi import APIRouter, HTTPException, Query
from src.api.app import get_db

router = APIRouter()


def _format_stock(row: dict) -> dict:
    """Format a tracked stock row with computed fields."""
    s = dict(row)
    checkpoints = {}
    for days in [7, 14, 30, 90]:
        price = s.get(f"price_{days}d")
        spy = s.get(f"spy_price_{days}d")
        sector = s.get(f"sector_etf_price_{days}d")
        if price is not None:
            checkpoints[days] = {"price": price, "spy": spy, "sector": sector, "observed_at": s.get(f"observed_at_{days}d"),
                                 "timing": "recorded" if s.get(f"observed_at_{days}d") else "unknown"}
        else:
            checkpoints[days] = None

    # Compute return and alpha from latest checkpoint
    return_pct = None
    alpha_pct = None
    for days in [90, 30, 14, 7]:
        if checkpoints[days] is not None and s.get("discovery_price"):
            price = checkpoints[days]["price"]
            return_pct = round((price - s["discovery_price"]) / s["discovery_price"] * 100, 1)
            spy_price = checkpoints[days]["spy"]
            if spy_price and s.get("spy_price_discovery"):
                spy_ret = (spy_price - s["spy_price_discovery"]) / s["spy_price_discovery"] * 100
                alpha_pct = round(return_pct - spy_ret, 1)
            break

    s["checkpoints"] = checkpoints
    s["return_pct"] = return_pct
    s["alpha_pct"] = alpha_pct
    return s


@router.get("/api/tracked")
async def tracked_list(status: str = Query("all", pattern="^(active|completed|all)$")):
    db = get_db()
    try:
        if status == "all":
            rows = db.execute("SELECT * FROM tracked_stocks ORDER BY discovered_at DESC").fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM tracked_stocks WHERE status = ? ORDER BY discovered_at DESC",
                (status,),
            ).fetchall()

        stocks = [_format_stock(dict(r)) for r in rows]
        return {"stocks": stocks}
    finally:
        db.close()


@router.get("/api/tracked/{ticker}")
async def tracked_detail(ticker: str):
    db = get_db()
    try:
        ticker = ticker.upper()
        row = db.execute(
            "SELECT * FROM tracked_stocks WHERE ticker = ? ORDER BY discovered_at DESC LIMIT 1",
            (ticker,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Ticker {ticker} not found")

        stock = _format_stock(dict(row))

        # Only show mentions available by this discovery (not later discussion).
        mentions = db.execute("""
            SELECT a.*,
                   COALESCE(p.title, cp.title) AS title,
                   COALESCE(p.subreddit, cp.subreddit) AS subreddit
            FROM analysis a
            LEFT JOIN posts p ON a.source_type = 'post' AND a.source_id = p.id
            LEFT JOIN comments c ON a.source_type = 'comment' AND a.source_id = c.id
            LEFT JOIN posts cp ON c.post_id = cp.id
            WHERE a.ticker = ? AND a.llm_scored = 1
              AND datetime(a.analyzed_at) <= datetime(?)
            ORDER BY a.overall_score DESC
        """, (ticker, stock["discovered_at"])).fetchall()

        return {
            "stock": stock,
            "mentions": [dict(m) for m in mentions],
        }
    finally:
        db.close()
