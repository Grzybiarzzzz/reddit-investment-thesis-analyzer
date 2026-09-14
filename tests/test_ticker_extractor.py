import pytest
from src.analyzer.ticker_extractor import TickerExtractor


@pytest.fixture
def extractor(tmp_path):
    # Create minimal test data files
    import json
    tickers_file = tmp_path / "tickers.csv"
    tickers_file.write_text("Symbol\nAAPL\nTSLA\nMSFT\nA\nIT\nALL\nGOOGL\nAMZN\nNVDA\n")

    company_names_file = tmp_path / "company_names.json"
    company_names = {
        "Apple": "AAPL",
        "Tesla": "TSLA",
        "Microsoft": "MSFT",
        "Google": "GOOGL",
        "Alphabet": "GOOGL",
        "Amazon": "AMZN",
        "Nvidia": "NVDA",
    }
    company_names_file.write_text(json.dumps(company_names))

    return TickerExtractor(
        tickers_path=str(tickers_file),
        company_names_path=str(company_names_file),
    )


class TestDollarSignTickers:
    def test_extracts_dollar_sign_ticker(self, extractor):
        assert "AAPL" in extractor.extract("I'm buying $AAPL today")

    def test_extracts_multiple_dollar_tickers(self, extractor):
        result = extractor.extract("$AAPL and $TSLA are both good")
        assert "AAPL" in result
        assert "TSLA" in result

    def test_accepts_ambiguous_ticker_with_dollar_sign(self, extractor):
        assert "A" in extractor.extract("$A is undervalued")


class TestCompanyNames:
    def test_extracts_company_name(self, extractor):
        assert "AAPL" in extractor.extract("Apple is going to crush earnings")

    def test_extracts_multiple_company_names(self, extractor):
        result = extractor.extract("I like Tesla and Microsoft")
        assert "TSLA" in result
        assert "MSFT" in result

    def test_case_insensitive_company_match(self, extractor):
        assert "TSLA" in extractor.extract("tesla is the future")


class TestBareTickerMatching:
    def test_extracts_bare_ticker_with_financial_context(self, extractor):
        assert "AAPL" in extractor.extract("AAPL earnings are great buy now")

    def test_rejects_ambiguous_bare_ticker_without_context(self, extractor):
        result = extractor.extract("A good day for all investors")
        assert "A" not in result
        assert "ALL" not in result

    def test_accepts_non_ambiguous_bare_ticker(self, extractor):
        assert "NVDA" in extractor.extract("NVDA just reported")


class TestEdgeCases:
    def test_empty_string(self, extractor):
        assert extractor.extract("") == []

    def test_no_tickers(self, extractor):
        assert extractor.extract("What a beautiful day") == []

    def test_deduplicates(self, extractor):
        result = extractor.extract("$AAPL Apple $AAPL AAPL")
        assert result.count("AAPL") == 1

    def test_returns_list(self, extractor):
        result = extractor.extract("$AAPL")
        assert isinstance(result, list)
