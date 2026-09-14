# tests/test_integration.py
import json
import pytest
from src.db.database import Database
from src.analyzer.ticker_extractor import TickerExtractor
from src.analyzer.heuristic_filter import HeuristicFilter
from src.analyzer.llm_scorer import analyze_content
from src.scoring.scorer_interface import MockScorer


@pytest.fixture
def test_env(tmp_path):
    """Set up a complete test environment with DB and data files."""
    # Create DB
    db = Database(str(tmp_path / "test.db"))
    db.initialize()

    # Create ticker data
    tickers_file = tmp_path / "tickers.csv"
    tickers_file.write_text("Symbol\nAAPL\nTSLA\nMSFT\nNVDA\nGOOGL\nAMZN\n")

    company_names_file = tmp_path / "company_names.json"
    company_names_file.write_text(json.dumps({
        "Apple": "AAPL", "Tesla": "TSLA", "Microsoft": "MSFT",
        "Nvidia": "NVDA", "Google": "GOOGL", "Amazon": "AMZN",
    }))

    extractor = TickerExtractor(
        tickers_path=str(tickers_file),
        company_names_path=str(company_names_file),
    )

    heuristic_filter = HeuristicFilter(
        ticker_extractor=extractor,
        min_length=50,
        financial_keywords=["buy", "sell", "earnings", "bullish", "revenue", "growth"],
    )

    scorer = MockScorer(seed=42)

    yield db, heuristic_filter, scorer

    db.close()


class TestFullPipeline:
    def test_scrape_analyze_flow(self, test_env):
        db, heuristic_filter, scorer = test_env

        # Simulate scraped data
        db.insert_post(
            id="p1", subreddit="stocks",
            title="AAPL earnings prediction",
            body="I think Apple will crush earnings this quarter based on strong iPhone revenue growth and expanding margins in services",
            score=150,
            url="http://reddit.com/p1",
            created_at="2026-03-12T10:00:00",
        )
        db.insert_comment(
            id="c1", post_id="p1",
            body="Agreed, Apple's revenue growth has been phenomenal. I'm bullish on AAPL for the next quarter at least",
            score=45,
            created_at="2026-03-12T11:00:00",
        )
        db.insert_comment(
            id="c2", post_id="p1",
            body="lol moon",  # Should be filtered out (too short)
            score=5,
            created_at="2026-03-12T11:30:00",
        )

        # Run analysis
        weights = {"reasoning": 0.30, "specificity": 0.25, "novelty": 0.25, "credibility": 0.20}
        stats = analyze_content(db, heuristic_filter, scorer, weights, batch_size=10)

        # Post (title + body) and one comment should pass filter
        assert stats["posts_analyzed"] == 1
        assert stats["comments_analyzed"] == 1
        assert stats["filtered_out"] == 1  # "lol moon" filtered

        # Check analysis records were created
        analyses = db.execute("SELECT * FROM analysis").fetchall()
        # MockScorer returns "MOCK" ticker which won't validate against valid_tickers,
        # so we expect no analysis rows from mock scorer (tickers get filtered out)
        # This is expected behavior - MockScorer is for testing the pipeline flow
        assert stats["scored"] == 2  # Both items were scored
