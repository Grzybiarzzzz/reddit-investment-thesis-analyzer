"""The dashboard must be able to serve a frozen database snapshot.

Viewing must not modify the file, and relative time windows are anchored to the
latest data rather than the wall clock.
"""
import hashlib
import sqlite3

import pytest
from fastapi.testclient import TestClient

from config.settings import FINANCIAL_KEYWORDS, SCORE_WEIGHTS, SECTOR_ETF_MAP
from src.analyzer.heuristic_filter import HeuristicFilter
from src.analyzer.llm_scorer import analyze_content
from src.analyzer.ticker_extractor import TickerExtractor
from src.db.database import Database
from src.scoring.scorer_interface import PerTicketScoreResult, ScorerInterface

OLD_DAY = "2025-06-01"


@pytest.fixture
def snapshot(monkeypatch, tmp_path):
    """A database whose newest activity is long in the past."""
    db_path = str(tmp_path / "snapshot.db")
    monkeypatch.setattr("config.settings.DASHBOARD_API_KEY", "")
    monkeypatch.setattr("config.settings.DB_PATH", db_path)

    db = Database(db_path)
    db.initialize()
    db.insert_post("p1", "StockMarket", "PLTR bull case", "Long DD", 100,
                   "https://i.redd.it/image.jpeg", "2025-05-31T06:00:00")
    db.insert_comment("c1", "p1", "PLTR is overvalued here", 5, "2025-05-31T07:00:00")
    db.insert_analysis("post", "p1", "PLTR", "bull", 80, 85, 70, 65, 76, "thesis", True, True)
    db.insert_analysis("comment", "c1", "PLTR", "bear", 60, 60, 60, 60, 60, "counter", True, True)
    db.close()

    # Backdate everything, as in a published snapshot.
    con = sqlite3.connect(db_path)
    con.execute("UPDATE posts SET scraped_at = ?", (f"{OLD_DAY} 10:00:00",))
    con.execute("UPDATE comments SET scraped_at = ?", (f"{OLD_DAY} 10:00:00",))
    con.execute("UPDATE analysis SET analyzed_at = ?", (f"{OLD_DAY} 12:00:00",))
    con.commit()
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.close()

    from src.api.app import create_app
    return TestClient(create_app()), db_path


def _sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_serving_requests_leaves_database_unchanged(snapshot):
    client, db_path = snapshot
    before = _sha256(db_path)
    for url in ("/api/dashboard", "/api/feed", "/api/tracked", "/api/analytics", "/api/portfolio"):
        assert client.get(url).status_code == 200
    assert _sha256(db_path) == before


def test_dashboard_windows_follow_latest_data(snapshot):
    client, _ = snapshot
    data = client.get("/api/dashboard").json()
    assert data["as_of"].startswith(OLD_DAY)
    assert data["kpis"]["posts_today"] == 1
    assert data["kpis"]["comments_today"] == 1
    assert data["kpis"]["scored_today"] == 2
    assert [t["ticker"] for t in data["top_tickers"]] == ["PLTR"]


def test_analytics_default_window_follows_latest_data(snapshot):
    client, _ = snapshot
    data = client.get("/api/analytics").json()
    assert data["as_of"].startswith(OLD_DAY)
    assert sum(b["count"] for b in data["score_distribution"]) == 2
    assert data["daily_volume"] == [{"date": OLD_DAY, "posts": 1}]


def test_feed_links_to_reddit_thread_not_submitted_url(snapshot):
    client, _ = snapshot
    items = {i["source_type"]: i for i in client.get("/api/feed").json()["items"]}
    assert items["post"]["reddit_url"] == "https://www.reddit.com/r/StockMarket/comments/p1/"
    assert items["comment"]["reddit_url"] == "https://www.reddit.com/r/StockMarket/comments/p1/_/c1/"


def test_feed_subreddit_filter_ignores_case(snapshot):
    client, _ = snapshot
    assert client.get("/api/feed?subreddit=stockmarket").json()["total"] == 2


def test_score_of_100_stays_in_top_bucket(snapshot):
    client, db_path = snapshot
    con = sqlite3.connect(db_path)
    con.execute("UPDATE analysis SET overall_score = 100 WHERE source_id = 'p1'")
    con.commit()
    con.close()
    buckets = [b["bucket"] for b in client.get("/api/analytics").json()["score_distribution"]]
    assert buckets == ["60-69", "90-100"]


def test_items_without_a_thesis_are_not_rescored(tmp_path):
    db_path = str(tmp_path / "pipeline.db")
    extractor = TickerExtractor("data/tickers.csv", "data/company_names.json")
    heuristic = HeuristicFilter(extractor, 20, FINANCIAL_KEYWORDS)

    class NoThesisScorer(ScorerInterface):
        calls = 0

        def score_batch(self, texts):
            NoThesisScorer.calls += 1
            return [PerTicketScoreResult(ticker_scores=[]) for _ in texts]

    for _ in range(2):
        db = Database(db_path)
        db.initialize()
        db.insert_post("p1", "stocks", "$NVDA is a buy after earnings", "body", 1, "u", "2026-01-01")
        analyze_content(db, heuristic, NoThesisScorer(), SCORE_WEIGHTS, 10)
        db.close()

    assert NoThesisScorer.calls == 1


def test_sector_map_uses_yahoo_finance_sector_names():
    # Names returned by yfinance; GICS names such as "Financials" never match.
    for sector in ("Financial Services", "Consumer Cyclical", "Consumer Defensive", "Basic Materials"):
        assert sector in SECTOR_ETF_MAP
