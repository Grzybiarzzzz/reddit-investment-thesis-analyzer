import csv
import json
import re


# Common English words that are also ticker symbols
AMBIGUOUS_TICKERS = {
    "A", "I", "IT", "ALL", "ARE", "FOR", "HAS", "HE", "BE", "SO",
    "OR", "ON", "AN", "AM", "AT", "BY", "DO", "GO", "IF", "IN",
    "IS", "ME", "MY", "NO", "OF", "OK", "TO", "UP", "US", "WE",
    "NOW", "OUT", "CAN", "MAN", "NEW", "OLD", "ONE", "OUR", "OWN",
    "RUN", "SEE", "TWO", "WAR", "WAY", "WHO", "ANY", "BIG", "DAY",
    "DID", "GET", "GOT", "HIM", "HIS", "HOW", "ITS", "LET", "MAY",
    "SAY", "SHE", "TOO", "USE", "HER", "WAS", "NOT", "BUT", "HAD",
    "LOW", "KEY", "FUN", "TRUE", "WELL", "REAL", "GOOD",
    "BEST", "FAST", "HUGE", "VERY", "OPEN", "LAND", "PLAY", "TURN",
}

FINANCIAL_CONTEXT_WORDS = {
    "buy", "sell", "hold", "calls", "puts", "bullish", "bearish",
    "earnings", "revenue", "profit", "long", "short", "squeeze",
    "undervalued", "overvalued", "target", "price", "shares",
    "stock", "ticker", "position", "entry", "exit", "dividend",
    "valuation", "growth", "momentum", "breakout", "support",
}


class TickerExtractor:
    def __init__(self, tickers_path: str, company_names_path: str):
        self.valid_tickers = self._load_tickers(tickers_path)
        self.company_map = self._load_company_names(company_names_path)
        # Lowercase company name -> ticker for case-insensitive matching
        self.company_map_lower = {k.lower(): v for k, v in self.company_map.items()}

    def _load_tickers(self, path: str) -> set[str]:
        tickers = set()
        with open(path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tickers.add(row["Symbol"].strip().upper())
        return tickers

    def _load_company_names(self, path: str) -> dict[str, str]:
        with open(path, "r") as f:
            return json.load(f)

    def extract(self, text: str) -> list[str]:
        if not text:
            return []

        found = set()

        # Layer 1: $TICKER format (high confidence, accept all including ambiguous)
        dollar_pattern = re.findall(r'\$([A-Z]{1,5})\b', text.upper())
        for match in dollar_pattern:
            if match in self.valid_tickers:
                found.add(match)

        # Layer 2: Company name matching (case-insensitive)
        text_lower = text.lower()
        for company_lower, ticker in self.company_map_lower.items():
            if re.search(r'\b' + re.escape(company_lower) + r'\b', text_lower):
                found.add(ticker)

        # Layer 3: Bare uppercase tickers (only non-ambiguous, or ambiguous with financial context)
        has_financial_context = any(
            w in text_lower for w in FINANCIAL_CONTEXT_WORDS
        )
        bare_pattern = re.findall(r'\b([A-Z]{1,5})\b', text)
        for match in bare_pattern:
            if match in self.valid_tickers:
                if match in AMBIGUOUS_TICKERS:
                    if has_financial_context:
                        found.add(match)
                else:
                    found.add(match)

        return sorted(found)
