"""Tests for /api/tracked endpoints."""
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
    db.insert_post("p1", "wallstreetbets", "PLTR DD", "Long DD",
                   100, "https://reddit.com/p1", "2026-03-13T06:00:00")
    db.insert_analysis("post", "p1", "PLTR", "bull", 80, 85, 70, 65, 76,
                       "NATO contract", True, True)
    db.insert_tracked_stock("PLTR", 78.40, "XLK", 5, 76.0, 520.0, 210.0)
    db.execute("UPDATE tracked_stocks SET price_7d = 80.50, spy_price_7d = 522.30, sector_etf_price_7d = 212.0 WHERE ticker = 'PLTR'")
    db.conn.commit()
    db.close()

    from src.api.app import create_app
    app = create_app()
    return TestClient(app)


def test_tracked_list_all(client):
    resp = client.get("/api/tracked")
    assert resp.status_code == 200
    data = resp.json()
    assert "stocks" in data
    assert len(data["stocks"]) >= 1


def test_tracked_filter_by_status(client):
    resp = client.get("/api/tracked?status=active")
    data = resp.json()
    for s in data["stocks"]:
        assert s["status"] == "active"


def test_tracked_includes_checkpoints(client):
    resp = client.get("/api/tracked")
    data = resp.json()
    stock = data["stocks"][0]
    assert "checkpoints" in stock
    assert 7 in stock["checkpoints"] or "7" in stock["checkpoints"]


def test_tracked_includes_return_and_alpha(client):
    resp = client.get("/api/tracked")
    data = resp.json()
    stock = data["stocks"][0]
    assert "return_pct" in stock
    assert "alpha_pct" in stock


def test_tracked_detail_by_ticker(client):
    resp = client.get("/api/tracked/PLTR")
    assert resp.status_code == 200
    data = resp.json()
    assert "stock" in data
    assert "mentions" in data
    assert data["stock"]["ticker"] == "PLTR"


def test_tracked_detail_not_found(client):
    resp = client.get("/api/tracked/ZZZZ")
    assert resp.status_code == 404
