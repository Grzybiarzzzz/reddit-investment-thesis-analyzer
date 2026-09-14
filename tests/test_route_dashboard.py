"""Tests for /api/dashboard endpoint."""
import pytest
from fastapi.testclient import TestClient
from src.db.database import Database


@pytest.fixture
def client(monkeypatch, tmp_path):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("config.settings.DASHBOARD_API_KEY", "")
    monkeypatch.setattr("config.settings.DB_PATH", db_path)

    # Seed test data
    db = Database(db_path)
    db.initialize()
    db.insert_post("p1", "wallstreetbets", "PLTR is amazing", "Great DD on Palantir",
                   100, "https://reddit.com/p1", "2026-03-13T06:00:00")
    db.insert_analysis("post", "p1", "PLTR", "bull", 80, 85, 70, 65, 76,
                       "Strong NATO contract thesis", True, True)
    db.insert_tracked_stock("PLTR", 78.40, "XLK", 5, 76.0, 520.0, 210.0)
    db.close()

    from src.api.app import create_app
    app = create_app()
    return TestClient(app)


def test_dashboard_returns_kpis(client):
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "kpis" in data
    assert data["kpis"]["tracked_count"] >= 0


def test_dashboard_returns_active_stocks(client):
    resp = client.get("/api/dashboard")
    data = resp.json()
    assert "active_stocks" in data
    assert len(data["active_stocks"]) >= 1
    assert data["active_stocks"][0]["ticker"] == "PLTR"


def test_dashboard_returns_recent_feed(client):
    resp = client.get("/api/dashboard")
    data = resp.json()
    assert "recent_feed" in data
    assert len(data["recent_feed"]) >= 1


def test_dashboard_returns_top_tickers(client):
    resp = client.get("/api/dashboard")
    data = resp.json()
    assert "top_tickers" in data
