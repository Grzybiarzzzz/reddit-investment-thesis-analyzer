"""FastAPI dashboard application."""
import os
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from config import settings
from src.api.auth import check_api_key, record_failed_attempt, is_locked_out, clear_attempts
from src.db.database import Database


def get_db() -> Database:
    """Open the database for a request.

    An existing database is opened read-only: serving the dashboard must not
    migrate or otherwise modify it. A missing one is created empty so a fresh
    checkout still renders.
    """
    db = Database(settings.DB_PATH)
    if os.path.exists(settings.DB_PATH):
        db.open_read_only()
    else:
        db.initialize()
    return db


def data_as_of(db: Database) -> str | None:
    """Latest scrape or assessment timestamp in the database (UTC), if any.

    Relative windows ("latest day", "last 7 days") are anchored here rather than
    at the wall clock, so a frozen snapshot shows its final days of activity
    instead of empty panels. For a live database the two are equivalent.
    """
    return db.execute(
        """SELECT MAX(t) FROM (SELECT MAX(scraped_at) AS t FROM posts
                               UNION ALL SELECT MAX(scraped_at) FROM comments
                               UNION ALL SELECT MAX(analyzed_at) FROM analysis)"""
    ).fetchone()[0]


# Reddit thread (or comment) permalink. posts.url is the submitted link, which
# for link and image posts points away from Reddit.
PERMALINK_SQL = """'https://www.reddit.com/r/' || COALESCE(p.subreddit, cp.subreddit)
                   || '/comments/' || COALESCE(p.id, cp.id) || '/'
                   || CASE WHEN a.source_type = 'comment' THEN '_/' || c.id || '/' ELSE '' END"""


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(title="Reddit Stock Analyzer Dashboard")

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        # Skip auth for static files
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        # Check lockout
        if is_locked_out(client_ip):
            return JSONResponse(
                status_code=429,
                content={"error": "Too many failed attempts. Try again later."},
            )

        # Check API key
        provided_key = request.headers.get("X-API-Key", "")
        if not check_api_key(provided_key, settings.DASHBOARD_API_KEY):
            record_failed_attempt(client_ip)
            return JSONResponse(
                status_code=401,
                content={"error": "Invalid API key"},
            )

        clear_attempts(client_ip)
        return await call_next(request)

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    from src.api.routes.dashboard import router as dashboard_router
    app.include_router(dashboard_router)

    from src.api.routes.feed import router as feed_router
    app.include_router(feed_router)

    from src.api.routes.tracked import router as tracked_router
    app.include_router(tracked_router)

    from src.api.routes.analytics import router as analytics_router
    app.include_router(analytics_router)

    from src.api.routes.portfolio import router as portfolio_router
    app.include_router(portfolio_router)

    # Mount static files (create dir if needed)
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    os.makedirs(static_dir, exist_ok=True)
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app


def main():
    """Run the dashboard server."""
    import uvicorn

    if not settings.DASHBOARD_API_KEY:
        print("WARNING: No DASHBOARD_API_KEY set. Auth is disabled.")
        print("  Set DASHBOARD_API_KEY in .env for security.\n")

    print(f"Starting dashboard at http://{settings.DASHBOARD_HOST}:{settings.DASHBOARD_PORT}")
    uvicorn.run(create_app(), host=settings.DASHBOARD_HOST, port=settings.DASHBOARD_PORT)


if __name__ == "__main__":
    main()
