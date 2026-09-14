# src/tracker/benchmark.py
import yfinance as yf


def get_current_price(ticker: str) -> float | None:
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        return float(price) if price else None
    except Exception:
        return None


# Approximate sector mapping for common stocks (via yfinance sector data)
_SECTOR_CACHE: dict[str, str] = {}


def get_sector_etf(ticker: str, sector_etf_map: dict[str, str]) -> str:
    if ticker in _SECTOR_CACHE:
        sector = _SECTOR_CACHE[ticker]
        return sector_etf_map.get(sector, "SPY")

    try:
        stock = yf.Ticker(ticker)
        sector = stock.info.get("sector", "")
        _SECTOR_CACHE[ticker] = sector
        return sector_etf_map.get(sector, "SPY")
    except Exception:
        return "SPY"
