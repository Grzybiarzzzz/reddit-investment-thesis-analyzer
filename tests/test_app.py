"""Tests for FastAPI dashboard app."""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client_no_auth(monkeypatch, tmp_path):
    """Client with auth disabled (no API key configured)."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("config.settings.DASHBOARD_API_KEY", "")
    monkeypatch.setattr("config.settings.DB_PATH", db_path)
    from src.api.app import create_app
    app = create_app()
    return TestClient(app)


@pytest.fixture
def client_with_auth(monkeypatch, tmp_path):
    """Client with auth enabled."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("config.settings.DASHBOARD_API_KEY", "test-secret-key")
    monkeypatch.setattr("config.settings.DB_PATH", db_path)
    from src.api.app import create_app
    app = create_app()
    return TestClient(app)


def test_health_endpoint(client_no_auth):
    resp = client_no_auth.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_api_requires_auth_when_configured(client_with_auth):
    resp = client_with_auth.get("/api/health")
    assert resp.status_code == 401


def test_api_auth_with_valid_key(client_with_auth):
    resp = client_with_auth.get("/api/health", headers={"X-API-Key": "test-secret-key"})
    assert resp.status_code == 200


def test_api_auth_with_invalid_key(client_with_auth):
    resp = client_with_auth.get("/api/health", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


def test_no_auth_required_when_not_configured(client_no_auth):
    resp = client_no_auth.get("/api/health")
    assert resp.status_code == 200
