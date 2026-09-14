"""Tests for /api/analytics endpoint."""
import pytest
from fastapi.testclient import TestClient
from src.db.database import Database


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("config.settings.DASHBOARD_API_KEY", "")
    monkeypatch.setattr("config.settings.DB_PATH", db_path)

    db = Database(db_path)
    db.initialize()
    # Seed varied data
    for i in range(5):
        db.insert_post(f"p{i}", "wallstreetbets", f"Post {i}", f"Body {i}",
                       50 + i * 10, f"https://reddit.com/p{i}", "2026-03-13T06:00:00")
        db.insert_analysis("post", f"p{i}", "PLTR", "bull",
                           60 + i * 5, 70 + i * 3, 50 + i * 4, 55 + i * 2, 60 + i * 4,
                           f"Reason {i}", True, True)
    for i in range(3):
        db.insert_post(f"b{i}", "stocks", f"Bear {i}", f"Body {i}",
                       30 + i * 5, f"https://reddit.com/b{i}", "2026-03-13T05:00:00")
        db.insert_analysis("post", f"b{i}", "CRWD", "bear",
                           40 + i * 5, 35 + i * 3, 30 + i * 4, 45 + i * 2, 38 + i * 4,
                           f"Bear reason {i}", True, True)
    db.close()

    from src.api.app import create_app
    app = create_app()
    return TestClient(app)


def test_analytics_returns_score_distribution(client):
    resp = client.get("/api/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert "score_distribution" in data
    assert len(data["score_distribution"]) > 0


def test_analytics_returns_sentiment_by_subreddit(client):
    resp = client.get("/api/analytics")
    data = resp.json()
    assert "sentiment_by_subreddit" in data
    assert len(data["sentiment_by_subreddit"]) > 0
    entry = data["sentiment_by_subreddit"][0]
    assert "subreddit" in entry
    assert "bull" in entry


def test_analytics_returns_subreddit_leaderboard(client):
    resp = client.get("/api/analytics")
    data = resp.json()
    assert "subreddit_leaderboard" in data


def test_analytics_returns_daily_volume(client):
    resp = client.get("/api/analytics")
    data = resp.json()
    assert "daily_volume" in data


def test_analytics_respects_days_param(client):
    resp = client.get("/api/analytics?days=1")
    assert resp.status_code == 200
