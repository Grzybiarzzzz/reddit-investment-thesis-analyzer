# tests/test_heuristic_filter.py
import pytest
from unittest.mock import MagicMock
from src.analyzer.heuristic_filter import HeuristicFilter


@pytest.fixture
def mock_extractor():
    extractor = MagicMock()
    extractor.extract.return_value = ["AAPL"]
    return extractor


@pytest.fixture
def filter_(mock_extractor):
    return HeuristicFilter(
        ticker_extractor=mock_extractor,
        min_length=50,
        financial_keywords=["buy", "sell", "earnings", "bullish", "revenue"],
    )


class TestLengthFilter:
    def test_rejects_short_text(self, filter_):
        result = filter_.apply("Buy AAPL")
        assert result.passed is False
        assert "too short" in result.reason

    def test_accepts_long_enough_text(self, filter_):
        text = "I think AAPL is a great buy because their earnings are going to crush expectations this quarter"
        result = filter_.apply(text)
        assert result.passed is True


class TestTickerPresence:
    def test_rejects_no_ticker(self, filter_, mock_extractor):
        mock_extractor.extract.return_value = []
        text = "The market is looking great today and I think we will see some nice gains in the coming weeks"
        result = filter_.apply(text)
        assert result.passed is False
        assert "no ticker" in result.reason.lower()

    def test_passes_with_ticker(self, filter_):
        text = "I think AAPL is a great buy because their earnings are going to crush expectations this quarter"
        result = filter_.apply(text)
        assert result.passed is True


class TestFinancialKeywords:
    def test_rejects_no_financial_keywords(self, filter_):
        text = "Apple makes really cool phones and I love their new design with the titanium frame on the latest model"
        result = filter_.apply(text)
        assert result.passed is False
        assert "keyword" in result.reason.lower()

    def test_passes_with_financial_keyword(self, filter_):
        text = "I think we should buy AAPL because their earnings are going to crush expectations this quarter wow"
        result = filter_.apply(text)
        assert result.passed is True


class TestFilterResult:
    def test_result_includes_tickers(self, filter_):
        text = "I think AAPL is a great buy because their earnings are going to crush expectations this quarter"
        result = filter_.apply(text)
        assert result.tickers == ["AAPL"]

    def test_result_passed_is_bool(self, filter_):
        text = "short"
        result = filter_.apply(text)
        assert isinstance(result.passed, bool)
