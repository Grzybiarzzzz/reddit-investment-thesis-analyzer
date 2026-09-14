"""Cache daily Yahoo Finance prices and corporate actions for tracked stocks."""
import argparse
import json
import math
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT/'reddit_stocks.db')
    parser.add_argument('--as-of', type=date.fromisoformat, required=True)
    parser.add_argument('--price-dir', type=Path, required=True)
    args = parser.parse_args()
    # Exclude today's potentially incomplete session. The report cutoff can be today.
    end = min(args.as_of + timedelta(days=1), datetime.now(timezone.utc).date())
    with sqlite3.connect(args.db.resolve().as_uri()+'?mode=ro', uri=True) as con:
        records = con.execute('SELECT ticker,sector_etf,discovered_at FROM tracked_stocks').fetchall()
    if not records:
        parser.error('No tracked stocks')
    start = date.fromisoformat(min(r[2] for r in records)[:10])-timedelta(days=7)
    if end <= start:
        parser.error('Cutoff precedes the discovery period')
    aliases = json.loads((ROOT/'data/symbol-aliases.json').read_text())
    symbols = {r[0] for r in records} | {r[1] for r in records if r[1]} | {'SPY'}
    symbols = sorted({aliases.get(s,{}).get('provider_symbol',s) for s in symbols})
    args.price_dir.mkdir(parents=True, exist_ok=True)
    errors = {}
    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            frame = ticker.history(start=start.isoformat(), end=end.isoformat(), auto_adjust=False, actions=True, timeout=20)
            if frame.empty:
                raise ValueError('No historical prices returned')
            meta = ticker.get_history_metadata()
            rows = []
            for stamp, row in frame.iterrows():
                def number(key):
                    value = float(row.get(key, float('nan')))
                    return value if math.isfinite(value) else None
                rows.append(dict(date=stamp.date().isoformat(), close=number('Close'),
                                 adjusted_close=number('Adj Close'), split=number('Stock Splits'), dividend=number('Dividends')))
            payload = dict(symbol=symbol, source='Yahoo Finance via yfinance',
                           fetched_at=datetime.now(timezone.utc).isoformat(), requested_start=start.isoformat(),
                           requested_end_exclusive=end.isoformat(), currency=meta.get('currency'),
                           exchange_timezone=meta.get('exchangeTimezoneName'), rows=rows)
            (args.price_dir/(symbol+'.json')).write_text(json.dumps(payload, indent=2)+'\n')
            print(f'{symbol}: {sum(r["close"] is not None for r in rows)} daily closes')
        except Exception as exc:
            errors[symbol] = str(exc)
            print(f'{symbol}: unavailable ({exc})')
        time.sleep(0.2)
    (args.price_dir/'download-errors.json').write_text(json.dumps(errors, indent=2)+'\n')
    if errors:
        raise SystemExit('Some downloads failed; inspect download-errors.json before evaluating this cache.')


if __name__ == '__main__':
    main()
