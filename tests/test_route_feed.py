"""Tests for /api/feed endpoint."""
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
    db.insert_post("p1", "wallstreetbets", "PLTR bull case", "Long DD",
                   100, "https://reddit.com/p1", "2026-03-13T06:00:00")
    db.insert_post("p2", "stocks", "CRWD is overvalued", "Bear case",
                   50, "https://reddit.com/p2", "2026-03-13T05:00:00")
    db.insert_analysis("post", "p1", "PLTR", "bull", 80, 85, 70, 65, 76,
                       "NATO contract thesis", True, True)
    db.insert_analysis("post", "p2", "CRWD", "bear", 70, 65, 55, 60, 63,
                       "Overvalued at 80x PE", True, True)
    db.close()

    from src.api.app import create_app
    app = create_app()
    return TestClient(app)


def test_feed_returns_paginated_items(client):
    resp = client.get("/api/feed")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert len(data["items"]) >= 1


def test_feed_filter_by_sentiment(client):
    resp = client.get("/api/feed?sentiment=bull")
    data = resp.json()
    for item in data["items"]:
        assert item["sentiment"] == "bull"


def test_feed_filter_by_ticker(client):
    resp = client.get("/api/feed?ticker=CRWD")
    data = resp.json()
    for item in data["items"]:
        assert item["ticker"] == "CRWD"


def test_feed_filter_by_min_score(client):
    resp = client.get("/api/feed?min_score=70")
    data = resp.json()
    for item in data["items"]:
        assert item["overall_score"] >= 70


def test_feed_sort_by_score(client):
    resp = client.get("/api/feed?sort=score")
    data = resp.json()
    scores = [item["overall_score"] for item in data["items"]]
    assert scores == sorted(scores, reverse=True)


def test_feed_pagination(client):
    resp = client.get("/api/feed?page=1&limit=1")
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["pages"] >= 1
