"""Integration tests for the full dashboard."""
import pytest
from fastapi.testclient import TestClient
from src.db.database import Database


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("config.settings.DASHBOARD_API_KEY", "")
    monkeypatch.setattr("config.settings.DB_PATH", db_path)

    # Seed realistic data
    db = Database(db_path)
    db.initialize()

    # Posts from multiple subreddits
    subreddits = ["wallstreetbets", "stocks", "investing"]
    for i, sub in enumerate(subreddits):
        for j in range(3):
            pid = f"p{i}{j}"
            db.insert_post(pid, sub, f"Post {pid}", f"Body {pid}",
                           50 + j * 20, f"https://reddit.com/{pid}",
                           "2026-03-13T06:00:00")
            db.insert_analysis("post", pid, ["PLTR", "CRWD", "SOFI"][j],
                               ["bull", "bear", "neutral"][j],
                               70 + j * 5, 65 + j * 3, 60 + j * 4, 55 + j * 2,
                               65 + j * 5, f"Reason {pid}", True, True)

    # Tracked stocks
    db.insert_tracked_stock("PLTR", 78.40, "XLK", 5, 76.0, 520.0, 210.0)
    db.insert_tracked_stock("SOFI", 12.85, "XLF", 3, 65.0, 520.0, 40.0)
    db.close()

    from src.api.app import create_app
    app = create_app()
    return TestClient(app)


def test_full_dashboard_flow(client):
    """Dashboard loads with all sections populated."""
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert data["kpis"]["tracked_count"] == 2
    assert len(data["active_stocks"]) == 2
    assert len(data["recent_feed"]) > 0
    assert len(data["top_tickers"]) > 0


def test_feed_to_tracked_flow(client):
    """Can browse feed and then look up tracked detail."""
    feed = client.get("/api/feed?ticker=PLTR").json()
    assert len(feed["items"]) > 0

    detail = client.get("/api/tracked/PLTR").json()
    assert detail["stock"]["ticker"] == "PLTR"
    assert len(detail["mentions"]) > 0


def test_analytics_with_data(client):
    """Analytics returns meaningful data."""
    resp = client.get("/api/analytics").json()
    assert len(resp["score_distribution"]) > 0
    assert len(resp["sentiment_by_subreddit"]) > 0


def test_static_files_served(client):
    """Static HTML is served at root."""
    resp = client.get("/")
    assert resp.status_code == 200
