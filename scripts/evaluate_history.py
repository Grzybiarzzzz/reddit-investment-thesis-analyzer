"""Evaluate cached daily prices against recorded discovery prices; never write the DB."""
import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.backtesting.historical import evaluate, discovery_date


def rank(values):
    ordered = sorted(set(values))
    return [1 + sum(v < x for v in values) + (values.count(x)-1)/2 for x in values]


def correlation(xs, ys):
    if len(xs) < 3:
        return None
    a, b = rank(xs), rank(ys)
    am, bm = mean(a), mean(b)
    denom = (sum((x-am)**2 for x in a)*sum((y-bm)**2 for y in b))**0.5
    return sum((x-am)*(y-bm) for x,y in zip(a,b))/denom if denom else None


def summarize(rows):
    valid = [r for r in rows if r['excess_spy_pp'] is not None]
    result = {'stocks': len(rows), 'paired_stocks': len(valid), 'statuses': dict(Counter(r['status'] for r in rows))}
    if valid:
        result.update(mean_return_pct=mean(r['return_pct'] for r in valid),
                      median_return_pct=median(r['return_pct'] for r in valid),
                      mean_excess_spy_pp=mean(r['excess_spy_pp'] for r in valid),
                      median_excess_spy_pp=median(r['excess_spy_pp'] for r in valid),
                      beat_spy=sum(r['excess_spy_pp'] > 0 for r in valid),
                      score_excess_spearman=correlation([r['quality_score'] for r in valid], [r['excess_spy_pp'] for r in valid]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT/'reddit_stocks.db')
    parser.add_argument('--price-dir', type=Path, required=True)
    parser.add_argument('--as-of', required=True, type=date.fromisoformat)
    parser.add_argument('--days', nargs='+', type=int, default=[7,14,30,60,90,120,180])
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if any(d < 1 for d in args.days):
        parser.error('--days must be positive')
    cache, hashes = {}, {}
    for path in sorted(args.price_dir.glob('*.json')):
        payload = json.loads(path.read_text())
        if 'rows' in payload:
            cache[payload['symbol']] = payload
            hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    aliases = json.loads((ROOT/'data/symbol-aliases.json').read_text())
    for symbol, alias in aliases.items():
        if alias['provider_symbol'] in cache:
            cache[symbol] = cache[alias['provider_symbol']]
    with sqlite3.connect(args.db.resolve().as_uri()+'?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        stocks = [dict(r) for r in con.execute('SELECT * FROM tracked_stocks ORDER BY discovered_at,id')]
    if not stocks:
        parser.error('No tracked stocks')
    horizons = [*dict.fromkeys(args.days), 'latest']
    cutoff = args.as_of.isoformat()
    rows = [evaluate(s, cache, cutoff, d) for d in horizons for s in stocks]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir/'checkpoints.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    summary = {str(d): summarize([r for r in rows if r['horizon'] == d]) for d in horizons}
    (args.output_dir/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    manifest = dict(as_of=cutoff, generated_at=datetime.now(timezone.utc).isoformat(),
                    database_sha256=hashlib.sha256(args.db.read_bytes()).hexdigest(),
                    price_files_sha256=hashes, aliases=aliases,
                    price_source='Yahoo Finance via yfinance',
                    price_fetch_times=sorted({p.get('fetched_at') for p in cache.values()}),
                    source_files_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'src/backtesting/historical.py']})
    (args.output_dir/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    # Compact rows let the standalone explorer select any elapsed calendar day.
    max_day = max(1, max((args.as_of-discovery_date(s)).days for s in stocks))
    compact = {}
    for d in [*range(1, max_day+1), 'latest']:
        compact[str(d)] = [[r['ticker'],r['quality_score'],r['return_pct'],r['excess_spy_pp'],r['price_date'],r['status'],r['actual_elapsed_days']]
                          for r in (evaluate(s,cache,cutoff,d) for s in stocks)]
    template = (ROOT/'scripts/history-report.html').read_text()
    data = json.dumps(dict(asOf=cutoff,maxDay=max_day,rows=compact), separators=(',',':'), allow_nan=False).replace('<','\\u003c')
    (args.output_dir/'results.html').write_text(template.replace('__REPORT_DATA__',data))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
