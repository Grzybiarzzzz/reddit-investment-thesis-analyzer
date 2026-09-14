# tests/test_database.py
import os
import sqlite3
import pytest
from src.db.database import Database


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / "test.db")
    database = Database(db_path)
    database.initialize()
    yield database
    database.close()


class TestDatabaseInit:
    def test_creates_tables(self, db):
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "posts" in table_names
        assert "comments" in table_names
        assert "analysis" in table_names
        assert "tracked_stocks" in table_names

    def test_posts_table_schema(self, db):
        row = db.execute("PRAGMA table_info(posts)").fetchall()
        columns = [r[1] for r in row]
        assert "id" in columns
        assert "subreddit" in columns
        assert "title" in columns
        assert "body" in columns
        assert "score" in columns
        assert "url" in columns
        assert "created_at" in columns
        assert "scraped_at" in columns


class TestPostOperations:
    def test_insert_post(self, db):
        db.insert_post(
            id="abc123",
            subreddit="stocks",
            title="AAPL is going up",
            body="I think Apple will beat earnings",
            score=42,
            url="https://reddit.com/r/stocks/abc123",
            created_at="2026-03-12T10:00:00",
        )
        result = db.execute("SELECT * FROM posts WHERE id = 'abc123'").fetchone()
        assert result is not None
        assert result[1] == "stocks"

    def test_insert_duplicate_post_ignored(self, db):
        post_data = dict(
            id="abc123",
            subreddit="stocks",
            title="AAPL",
            body="body",
            score=10,
            url="https://reddit.com/abc123",
            created_at="2026-03-12T10:00:00",
        )
        db.insert_post(**post_data)
        db.insert_post(**post_data)  # should not raise
        count = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        assert count == 1


class TestCommentOperations:
    def test_insert_comment(self, db):
        db.insert_post(
            id="post1", subreddit="stocks", title="T", body="B",
            score=1, url="http://x", created_at="2026-03-12T10:00:00",
        )
        db.insert_comment(
            id="comm1",
            post_id="post1",
            body="I think AAPL has great fundamentals",
            score=15,
            created_at="2026-03-12T11:00:00",
        )
        result = db.execute("SELECT * FROM comments WHERE id = 'comm1'").fetchone()
        assert result is not None
        assert result[2] == "I think AAPL has great fundamentals"


class TestAnalysisOperations:
    def test_insert_analysis(self, db):
        analysis_id = db.insert_analysis(
            source_type="comment",
            source_id="comm1",
            ticker="AAPL",
            sentiment="bull",
            reasoning_score=75,
            specificity_score=60,
            novelty_score=50,
            credibility_score=80,
            overall_score=66,
            reasoning_summary="Solid earnings argument with data",
            passed_heuristic=True,
            llm_scored=True,
        )
        assert analysis_id is not None
        result = db.execute("SELECT * FROM analysis WHERE id = ?", (analysis_id,)).fetchone()
        assert result is not None

    def test_get_unanalyzed_posts(self, db):
        db.insert_post(
            id="p1", subreddit="stocks", title="T", body="Body text here",
            score=10, url="http://x", created_at="2026-03-12T10:00:00",
        )
        unanalyzed = db.get_unanalyzed_posts()
        assert len(unanalyzed) == 1
        assert unanalyzed[0]["id"] == "p1"

    def test_get_unanalyzed_comments(self, db):
        db.insert_post(
            id="p1", subreddit="stocks", title="T", body="B",
            score=1, url="http://x", created_at="2026-03-12T10:00:00",
        )
        db.insert_comment(
            id="c1", post_id="p1", body="Some comment about stocks",
            score=5, created_at="2026-03-12T11:00:00",
        )
        unanalyzed = db.get_unanalyzed_comments()
        assert len(unanalyzed) == 1
        assert unanalyzed[0]["id"] == "c1"

    def test_mark_processed_excludes_from_unanalyzed(self, db):
        db.insert_post(
            id="p1", subreddit="stocks", title="T", body="Body",
            score=10, url="http://x", created_at="2026-03-12T10:00:00",
        )
        db.insert_post(
            id="p2", subreddit="stocks", title="T2", body="Body2",
            score=5, url="http://y", created_at="2026-03-12T11:00:00",
        )
        assert len(db.get_unanalyzed_posts()) == 2
        db.mark_processed("post", "p1")
        db.conn.commit()
        unanalyzed = db.get_unanalyzed_posts()
        assert len(unanalyzed) == 1
        assert unanalyzed[0]["id"] == "p2"


class TestTrackedStockOperations:
    def test_insert_tracked_stock(self, db):
        stock_id = db.insert_tracked_stock(
            ticker="AAPL",
            discovery_price=178.50,
            sector_etf="XLK",
            mention_count=5,
            avg_quality_score=72.5,
            spy_price_discovery=512.30,
            sector_etf_price_discovery=198.40,
        )
        assert stock_id is not None
        result = db.execute("SELECT * FROM tracked_stocks WHERE id = ?", (stock_id,)).fetchone()
        assert result is not None

    def test_get_active_tracked_stocks(self, db):
        db.insert_tracked_stock(
            ticker="AAPL", discovery_price=178.50, sector_etf="XLK",
            mention_count=5, avg_quality_score=72.5,
            spy_price_discovery=512.30, sector_etf_price_discovery=198.40,
        )
        active = db.get_active_tracked_stocks()
        assert len(active) == 1
        assert active[0]["ticker"] == "AAPL"

    def test_update_checkpoint(self, db):
        stock_id = db.insert_tracked_stock(
            ticker="AAPL", discovery_price=178.50, sector_etf="XLK",
            mention_count=5, avg_quality_score=72.5,
            spy_price_discovery=512.30, sector_etf_price_discovery=198.40,
        )
        db.update_checkpoint(stock_id, 7, stock_price=185.00, spy_price=520.00, sector_etf_price=205.00)
        result = db.execute("SELECT price_7d, spy_price_7d, sector_etf_price_7d FROM tracked_stocks WHERE id = ?", (stock_id,)).fetchone()
        assert result[0] == 185.00
        assert result[1] == 520.00
        assert result[2] == 205.00
