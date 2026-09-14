import os
from dotenv import load_dotenv

load_dotenv(override=True)

# Reddit scraping
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "RedditStockAnalyzer/1.0")
SCRAPER_DELAY = 5.0  # seconds between requests (avoid 429 rate limits)

# Anthropic API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_VERTEX_PROJECT = os.getenv("GEMINI_VERTEX_PROJECT", "")
GEMINI_VERTEX_LOCATION = os.getenv("GEMINI_VERTEX_LOCATION", "us-central1")

# Subreddits to scrape
SUBREDDITS = [
    "wallstreetbets",
    "stocks",
    "investing",
    "ValueInvesting",
    "StockMarket",
    "SecurityAnalysis",
    "smallstreetbets",
    "pennystocks",
    "Undervalued",
]

# Scraping settings
LOOKBACK_HOURS = 24
MIN_COMMENT_SCORE = 3
SORT_MODES = ["hot", "new"]
POSTS_PER_SORT = 50

# Heuristic filter settings
MIN_COMMENT_LENGTH = 20
FINANCIAL_KEYWORDS = [
    "buy", "sell", "hold", "calls", "puts", "bullish", "bearish",
    "earnings", "revenue", "profit", "loss", "PE", "P/E", "EPS",
    "dividend", "market cap", "valuation", "growth", "undervalued",
    "overvalued", "short", "long", "squeeze", "volume", "support",
    "resistance", "breakout", "momentum", "fundamentals", "technical",
    "analyst", "target price", "guidance", "forecast", "sector",
    "portfolio", "position", "entry", "exit", "risk", "return",
    "yield", "cash flow", "debt", "balance sheet", "income statement",
]

# LLM scoring settings
SCORING_BACKEND = "gemini"  # "anthropic", "ollama", "gemini", "mock"
SCORING_MODEL = "claude-haiku-4-5-20251001"
OLLAMA_MODEL = "qwen3.5:4b"
OLLAMA_BASE_URL = "http://localhost:11434"
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_FALLBACK_MODEL = "gemini-2.0-flash"
LLM_BATCH_SIZE = 10
LLM_RATE_LIMIT_DELAY = 0  # seconds between batches (0 to disable)

# Score weights (must sum to 1.0)
SCORE_WEIGHTS = {
    "reasoning": 0.30,
    "specificity": 0.25,
    "novelty": 0.25,
    "credibility": 0.20,
}

# Discovery thresholds
MIN_MENTIONS = 5
MIN_AVG_SCORE = 65
MENTION_LOOKBACK_DAYS = 7
RETRACK_COOLDOWN_DAYS = 90

# Tracking checkpoints (days after discovery)
CHECKPOINTS = [7, 14, 30, 90]

# Benchmark
MARKET_BENCHMARK = "SPY"

# Sector ETF mapping
SECTOR_ETF_MAP = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Industrials": "XLI",
    "Materials": "XLB",
    "Real Estate": "XLRE",
    "Communication Services": "XLC",
}

# Database
DB_PATH = os.getenv("DB_PATH", "reddit_stocks.db")

# Dashboard
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8050"))
DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY", "")
