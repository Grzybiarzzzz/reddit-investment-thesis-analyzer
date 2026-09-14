# scripts/download_tickers.py
"""Download the full NASDAQ/NYSE ticker list and save to data/tickers.csv."""
import os
import requests
import csv

NASDAQ_URL = "https://api.nasdaq.com/api/screener/stocks?tableType=traded&limit=10000&offset=0"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "tickers.csv")


def download_tickers():
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    print("Downloading ticker list from NASDAQ...")
    response = requests.get(NASDAQ_URL, headers=headers)
    response.raise_for_status()
    data = response.json()

    rows = data.get("data", {}).get("rows", [])
    if not rows:
        print("No data received. Using fallback method.")
        _write_fallback()
        return

    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Symbol"])
        for row in rows:
            symbol = row.get("symbol", "").strip()
            if symbol and symbol.isalpha() and len(symbol) <= 5:
                writer.writerow([symbol])

    print(f"Saved {len(rows)} tickers to {OUTPUT_PATH}")


def _write_fallback():
    """Write a minimal ticker list if API fails."""
    # Top ~200 most commonly discussed tickers
    tickers = [
        "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA",
        "BRK.B", "JPM", "JNJ", "V", "WMT", "MA", "PG", "UNH", "HD", "CVX",
        "KO", "PEP", "PFE", "MRK", "ABBV", "COST", "NFLX", "AMD", "INTC",
        "DIS", "CRM", "ADBE", "PYPL", "QCOM", "CMCSA", "NKE", "SBUX", "MCD",
        "GS", "MS", "BA", "CAT", "MMM", "IBM", "GE", "F", "GM", "T", "VZ",
        "TMUS", "PLTR", "SNOW", "CRWD", "UBER", "ABNB", "COIN", "RIVN",
        "LCID", "SOFI", "HOOD", "GME", "AMC", "AVGO", "TXN", "AMAT", "LRCX",
        "MU", "ARM", "LLY", "NVO", "MRNA", "REGN", "AMGN", "GILD", "TGT",
        "LOW", "CVS", "WBA", "XOM", "COP", "SHEL", "BP", "SQ", "SPOT",
        "SNAP", "PINS", "RDDT", "U", "RBLX", "DKNG", "SHOP", "NET", "DDOG",
        "MELI", "SE", "NIO", "BYDDY", "LI", "BIDU", "BABA", "JD", "TCEHY",
        "SPY", "QQQ", "DIA", "IWM", "XLK", "XLV", "XLF", "XLY", "XLP",
        "XLE", "XLU", "XLI", "XLB", "XLRE", "XLC",
    ]
    with open(OUTPUT_PATH, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Symbol"])
        for t in tickers:
            writer.writerow([t])
    print(f"Wrote fallback list with {len(tickers)} tickers to {OUTPUT_PATH}")


if __name__ == "__main__":
    download_tickers()
