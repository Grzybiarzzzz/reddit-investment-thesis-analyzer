import sqlite3
from datetime import datetime
from src.db.models import SCHEMA


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None

    def initialize(self):
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(SCHEMA)
        # Only analyses prove that an older source was processed. Never mark
        # every scraped item complete when another pipeline stage opens the DB.
        self.conn.execute(
            """INSERT OR IGNORE INTO processed_items (source_type, source_id)
               SELECT DISTINCT source_type, source_id FROM analysis WHERE llm_scored = 1"""
        )
        columns = {r[1] for r in self.conn.execute("PRAGMA table_info(tracked_stocks)")}
        for name in ["discovery_sentiment", "observed_at_7d", "observed_at_14d",
                     "observed_at_30d", "observed_at_90d"]:
            if name not in columns:
                self.conn.execute(f"ALTER TABLE tracked_stocks ADD COLUMN {name} TEXT")
        self.conn.commit()

    def close(self):
        if self.conn:
            self.conn.close()

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.conn.execute(query, params)

    def insert_post(self, id: str, subreddit: str, title: str, body: str,
                    score: int, url: str, created_at: str):
        self.conn.execute(
            """INSERT OR IGNORE INTO posts (id, subreddit, title, body, score, url, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (id, subreddit, title, body, score, url, created_at),
        )
        self.conn.commit()

    def insert_comment(self, id: str, post_id: str, body: str,
                       score: int, created_at: str):
        self.conn.execute(
            """INSERT OR IGNORE INTO comments (id, post_id, body, score, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (id, post_id, body, score, created_at),
        )
        self.conn.commit()

    def insert_analysis(self, source_type: str, source_id: str, ticker: str,
                        sentiment: str, reasoning_score: int, specificity_score: int,
                        novelty_score: int, credibility_score: int, overall_score: int,
                        reasoning_summary: str, passed_heuristic: bool, llm_scored: bool) -> int:
        cursor = self.conn.execute(
            """INSERT INTO analysis (source_type, source_id, ticker, sentiment,
               reasoning_score, specificity_score, novelty_score, credibility_score,
               overall_score, reasoning_summary, passed_heuristic, llm_scored)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (source_type, source_id, ticker, sentiment,
             reasoning_score, specificity_score, novelty_score, credibility_score,
             overall_score, reasoning_summary, int(passed_heuristic), int(llm_scored)),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_unanalyzed_posts(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT p.* FROM posts p
               WHERE p.id NOT IN (SELECT source_id FROM processed_items WHERE source_type = 'post')"""
        ).fetchall()
        return [dict(r) for r in rows]

    def get_unanalyzed_comments(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT c.*, p.title AS post_title FROM comments c
               JOIN posts p ON c.post_id = p.id
               WHERE c.id NOT IN (SELECT source_id FROM processed_items WHERE source_type = 'comment')"""
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_processed(self, source_type: str, source_id: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO processed_items (source_type, source_id) VALUES (?, ?)",
            (source_type, source_id),
        )

    def get_ticker_mentions(self, ticker: str, days: int) -> list[dict]:
        rows = self.conn.execute(
            """SELECT * FROM analysis
               WHERE ticker = ? AND analyzed_at >= datetime('now', ?)""",
            (ticker, f"-{days} days"),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_recent_tickers(self, days: int) -> list[str]:
        rows = self.conn.execute(
            """SELECT DISTINCT ticker FROM analysis
               WHERE analyzed_at >= datetime('now', ?) AND overall_score > 0""",
            (f"-{days} days",),
        ).fetchall()
        return [r[0] for r in rows]

    def is_ticker_tracked_recently(self, ticker: str, days: int) -> bool:
        row = self.conn.execute(
            """SELECT COUNT(*) FROM tracked_stocks
               WHERE ticker = ? AND discovered_at >= datetime('now', ?)""",
            (ticker, f"-{days} days"),
        ).fetchone()
        return row[0] > 0

    def insert_tracked_stock(self, ticker: str, discovery_price: float, sector_etf: str,
                             mention_count: int, avg_quality_score: float,
                             spy_price_discovery: float, sector_etf_price_discovery: float,
                             discovery_sentiment: str | None = None) -> int:
        cursor = self.conn.execute(
            """INSERT INTO tracked_stocks (ticker, discovery_price, sector_etf,
               mention_count, avg_quality_score, spy_price_discovery, sector_etf_price_discovery, discovery_sentiment)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (ticker, discovery_price, sector_etf, mention_count, avg_quality_score,
             spy_price_discovery, sector_etf_price_discovery, discovery_sentiment),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_active_tracked_stocks(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM tracked_stocks WHERE status = 'active'"
        ).fetchall()
        return [dict(r) for r in rows]

    def update_checkpoint(self, stock_id: int, days: int,
                          stock_price: float, spy_price: float | None, sector_etf_price: float | None,
                          observed_at: str | None = None):
        if days not in (7, 14, 30, 90):
            raise ValueError(f"Invalid checkpoint: {days} days")
        self.conn.execute(
            f"""UPDATE tracked_stocks
                SET price_{days}d = ?, spy_price_{days}d = ?, sector_etf_price_{days}d = ?, observed_at_{days}d = ?
                WHERE id = ? AND price_{days}d IS NULL""",
            (stock_price, spy_price, sector_etf_price, observed_at, stock_id),
        )
        self.conn.commit()

    def mark_completed(self, stock_id: int):
        self.conn.execute(
            "UPDATE tracked_stocks SET status = 'completed' WHERE id = ?",
            (stock_id,),
        )
        self.conn.commit()
