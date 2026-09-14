# src/analyzer/heuristic_filter.py
from dataclasses import dataclass
from src.analyzer.ticker_extractor import TickerExtractor


@dataclass
class FilterResult:
    passed: bool
    reason: str
    tickers: list[str]


class HeuristicFilter:
    def __init__(self, ticker_extractor: TickerExtractor, min_length: int,
                 financial_keywords: list[str]):
        self.ticker_extractor = ticker_extractor
        self.min_length = min_length
        self.financial_keywords = [kw.lower() for kw in financial_keywords]

    def apply(self, text: str) -> FilterResult:
        # Check 1: Minimum length
        if len(text.strip()) < self.min_length:
            return FilterResult(passed=False, reason="too short", tickers=[])

        # Check 2: Must contain a recognized ticker
        tickers = self.ticker_extractor.extract(text)
        if not tickers:
            return FilterResult(passed=False, reason="No ticker found", tickers=[])

        # Check 3: Must contain at least one financial keyword
        # Skip this check if text has explicit $TICKER (strong enough signal)
        has_dollar_ticker = "$" in text and any(f"${t}" in text.upper() for t in tickers)
        if not has_dollar_ticker:
            text_lower = text.lower()
            has_keyword = any(kw in text_lower for kw in self.financial_keywords)
            if not has_keyword:
                return FilterResult(passed=False, reason="No financial keyword found", tickers=tickers)

        return FilterResult(passed=True, reason="Passed all checks", tickers=tickers)
