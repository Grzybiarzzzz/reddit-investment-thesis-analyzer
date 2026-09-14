SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id TEXT PRIMARY KEY,
    subreddit TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    score INTEGER DEFAULT 0,
    url TEXT,
    created_at TEXT NOT NULL,
    scraped_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS comments (
    id TEXT PRIMARY KEY,
    post_id TEXT NOT NULL REFERENCES posts(id),
    body TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    scraped_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analysis (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL CHECK(source_type IN ('post', 'comment')),
    source_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    sentiment TEXT CHECK(sentiment IN ('bull', 'bear', 'neutral')),
    reasoning_score INTEGER DEFAULT 0,
    specificity_score INTEGER DEFAULT 0,
    novelty_score INTEGER DEFAULT 0,
    credibility_score INTEGER DEFAULT 0,
    overall_score INTEGER DEFAULT 0,
    reasoning_summary TEXT,
    passed_heuristic INTEGER DEFAULT 0,
    llm_scored INTEGER DEFAULT 0,
    analyzed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tracked_stocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
    discovery_price REAL NOT NULL,
    sector_etf TEXT,
    mention_count INTEGER DEFAULT 0,
    avg_quality_score REAL DEFAULT 0,
    price_7d REAL,
    price_14d REAL,
    price_30d REAL,
    price_90d REAL,
    spy_price_discovery REAL,
    spy_price_7d REAL,
    spy_price_14d REAL,
    spy_price_30d REAL,
    spy_price_90d REAL,
    sector_etf_price_discovery REAL,
    sector_etf_price_7d REAL,
    sector_etf_price_14d REAL,
    sector_etf_price_30d REAL,
    sector_etf_price_90d REAL,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed'))
);

CREATE TABLE IF NOT EXISTS processed_items (
    source_type TEXT NOT NULL CHECK(source_type IN ('post', 'comment')),
    source_id TEXT NOT NULL,
    processed_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (source_type, source_id)
);

CREATE INDEX IF NOT EXISTS idx_analysis_source ON analysis(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_analysis_ticker ON analysis(ticker);
CREATE INDEX IF NOT EXISTS idx_analysis_analyzed_at ON analysis(analyzed_at);
CREATE INDEX IF NOT EXISTS idx_tracked_stocks_status ON tracked_stocks(status);
CREATE INDEX IF NOT EXISTS idx_tracked_stocks_ticker ON tracked_stocks(ticker);
"""
