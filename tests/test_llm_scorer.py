# tests/test_llm_scorer.py
import json
import pytest
from unittest.mock import MagicMock
from src.analyzer.llm_scorer import analyze_content, EXCLUDED_TICKERS, MAX_TICKERS_PER_POST, _validate_and_filter_tickers
from src.scoring.scorer_interface import ScoreResult, PerTicketScoreResult


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.get_unanalyzed_posts.return_value = [
        {"id": "p1", "title": "AAPL earnings are great", "body": "I think Apple will crush earnings based on strong iPhone revenue growth this quarter"},
    ]
    db.get_unanalyzed_comments.return_value = [
        {"id": "c1", "body": "I agree, AAPL fundamentals are solid with great revenue growth and expanding margins lately"},
    ]
    return db


@pytest.fixture
def mock_filter():
    f = MagicMock()
    f.ticker_extractor = MagicMock()
    f.ticker_extractor.valid_tickers = {"AAPL", "TSLA", "MSFT", "NVDA", "GOOGL", "AMZN"}
    f.ticker_extractor.company_map_lower = {
        "apple": "AAPL", "tesla": "TSLA", "microsoft": "MSFT",
        "nvidia": "NVDA", "google": "GOOGL", "amazon": "AMZN",
    }
    result_pass = MagicMock()
    result_pass.passed = True
    result_pass.tickers = ["AAPL"]
    f.apply.return_value = result_pass
    return f


@pytest.fixture
def mock_scorer():
    scorer = MagicMock()

    def _score_batch(texts):
        return [
            PerTicketScoreResult(ticker_scores=[
                ScoreResult(
                    reasoning_score=75, specificity_score=60, novelty_score=50,
                    credibility_score=80, sentiment="bull",
                    reasoning_summary="Good AAPL analysis", tickers_mentioned=["AAPL"],
                )
            ])
            for _ in texts
        ]

    scorer.score_batch.side_effect = _score_batch
    return scorer


class TestAnalyzeContent:
    def test_analyzes_posts_and_comments(self, mock_db, mock_filter, mock_scorer):
        weights = {"reasoning": 0.30, "specificity": 0.25, "novelty": 0.25, "credibility": 0.20}
        results = analyze_content(mock_db, mock_filter, mock_scorer, weights, batch_size=10)
        assert results["posts_analyzed"] == 1
        assert results["comments_analyzed"] == 1
        assert mock_db.insert_analysis.call_count == 2

    def test_skips_filtered_content(self, mock_db, mock_filter, mock_scorer):
        fail_result = MagicMock()
        fail_result.passed = False
        fail_result.tickers = []
        mock_filter.apply.return_value = fail_result

        weights = {"reasoning": 0.30, "specificity": 0.25, "novelty": 0.25, "credibility": 0.20}
        results = analyze_content(mock_db, mock_filter, mock_scorer, weights, batch_size=10)
        assert mock_scorer.score_batch.call_count == 0

    def test_per_ticker_scoring_different_scores(self, mock_db, mock_filter):
        """Each ticker from the same post gets its own score."""
        scorer = MagicMock()

        def _score_batch(texts):
            return [
                PerTicketScoreResult(ticker_scores=[
                    ScoreResult(85, 80, 70, 90, "bull", "Strong NVDA thesis", ["NVDA"]),
                    ScoreResult(30, 20, 10, 40, "neutral", "Casual AAPL mention", ["AAPL"]),
                ])
                for _ in texts
            ]

        scorer.score_batch.side_effect = _score_batch

        mock_db.get_unanalyzed_posts.return_value = [
            {"id": "p1", "title": "NVDA investment", "body": "NVDA invested in something, also AAPL exists"},
        ]
        mock_db.get_unanalyzed_comments.return_value = []

        weights = {"reasoning": 0.30, "specificity": 0.25, "novelty": 0.25, "credibility": 0.20}
        results = analyze_content(mock_db, mock_filter, scorer, weights, batch_size=10)

        # Should have 2 insert_analysis calls with different scores
        assert mock_db.insert_analysis.call_count == 2
        calls = mock_db.insert_analysis.call_args_list

        # Find the NVDA and AAPL calls
        nvda_call = [c for c in calls if c.kwargs.get("ticker") == "NVDA"]
        aapl_call = [c for c in calls if c.kwargs.get("ticker") == "AAPL"]
        assert len(nvda_call) == 1
        assert len(aapl_call) == 1
        assert nvda_call[0].kwargs["reasoning_score"] == 85
        assert aapl_call[0].kwargs["reasoning_score"] == 30

    def test_excludes_etf_tickers(self, mock_db, mock_filter):
        """ETFs like SPY should not be inserted into analysis."""
        scorer = MagicMock()

        def _score_batch(texts):
            return [
                PerTicketScoreResult(ticker_scores=[
                    ScoreResult(80, 80, 80, 80, "bull", "AAPL thesis", ["AAPL"]),
                    ScoreResult(80, 80, 80, 80, "bull", "SPY thesis", ["SPY"]),
                ])
                for _ in texts
            ]

        scorer.score_batch.side_effect = _score_batch

        mock_db.get_unanalyzed_posts.return_value = [
            {"id": "p1", "title": "AAPL vs SPY", "body": "comparing AAPL to SPY benchmark performance over time"},
        ]
        mock_db.get_unanalyzed_comments.return_value = []

        weights = {"reasoning": 0.30, "specificity": 0.25, "novelty": 0.25, "credibility": 0.20}
        analyze_content(mock_db, mock_filter, scorer, weights, batch_size=10)

        # Only AAPL should be inserted, not SPY
        assert mock_db.insert_analysis.call_count == 1
        assert mock_db.insert_analysis.call_args.kwargs["ticker"] == "AAPL"

    def test_caps_tickers_per_post(self, mock_db, mock_filter):
        """Posts with too many tickers (portfolio dumps) should be capped."""
        scorer = MagicMock()
        mock_filter.ticker_extractor.valid_tickers = {
            "AAPL", "TSLA", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "NFLX"
        }

        # Create a portfolio dump with 8 tickers
        ticker_scores = [
            ScoreResult(90 - i * 5, 80, 70, 80, "bull", f"Thesis for ticker {i}", [t])
            for i, t in enumerate(["AAPL", "TSLA", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "NFLX"])
        ]

        def _score_batch(texts):
            return [PerTicketScoreResult(ticker_scores=ticker_scores) for _ in texts]

        scorer.score_batch.side_effect = _score_batch

        mock_db.get_unanalyzed_posts.return_value = [
            {"id": "p1", "title": "My portfolio", "body": "Here are my holdings: AAPL TSLA MSFT NVDA GOOGL AMZN META NFLX all looking good for growth"},
        ]
        mock_db.get_unanalyzed_comments.return_value = []

        weights = {"reasoning": 0.30, "specificity": 0.25, "novelty": 0.25, "credibility": 0.20}
        analyze_content(mock_db, mock_filter, scorer, weights, batch_size=10)

        assert mock_db.insert_analysis.call_count == MAX_TICKERS_PER_POST


class TestValidateAndFilterTickers:
    def test_valid_ticker_passes(self):
        result = _validate_and_filter_tickers(["AAPL"], {"AAPL", "TSLA"}, {})
        assert result == ["AAPL"]

    def test_company_name_normalized(self):
        result = _validate_and_filter_tickers(
            ["Nvidia"], {"NVDA"}, {"nvidia": "NVDA"}
        )
        assert result == ["NVDA"]

    def test_unknown_ticker_dropped(self):
        result = _validate_and_filter_tickers(
            ["Star Bulk", "Wiz", "6547"], {"AAPL"}, {}
        )
        assert result == []

    def test_deduplication(self):
        result = _validate_and_filter_tickers(
            ["GOOGL", "Google"], {"GOOGL"}, {"google": "GOOGL"}
        )
        assert result == ["GOOGL"]

    def test_case_insensitive_company_names(self):
        result = _validate_and_filter_tickers(
            ["APPLE", "apple"], {"AAPL"}, {"apple": "AAPL"}
        )
        assert result == ["AAPL"]
