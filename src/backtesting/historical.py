"""Reconstruct price returns without modifying live tracking observations.

Yahoo daily Close is split-adjusted. Saved spot entry prices are therefore
converted to the same share basis using subsequent split events in the cache.
Dividend adjustments are deliberately not used: these are price returns.
"""
from datetime import date, datetime, timedelta
from math import isfinite, prod
from zoneinfo import ZoneInfo


def valid_price(value):
    return isinstance(value, (int, float)) and isfinite(value) and value > 0


def discovery_date(stock):
    timestamp = datetime.fromisoformat(stock['discovered_at'])
    # SQLite datetime('now') records UTC without an offset.
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo('UTC'))
    return timestamp.astimezone(ZoneInfo('America/New_York')).date()


def split_factor(series, entry_date):
    return prod(r['split'] for r in series.get('rows', [])
                if r.get('split') and date.fromisoformat(r['date']) > entry_date)


def return_at(series, price_date, saved_entry, entry_date):
    if not series or series.get('currency') != 'USD' or not valid_price(saved_entry):
        return None
    if any(r.get('split') and r['date'] == entry_date.isoformat() for r in series['rows']):
        return None
    row = next((r for r in series['rows'] if r['date'] == price_date), None)
    if row is None or not valid_price(row.get('close')):
        return None
    factor = split_factor(series, entry_date)
    if not valid_price(factor):
        return None
    return 100 * (row['close'] / (saved_entry / factor) - 1)


def evaluate(stock, cache, as_of, horizon):
    """Use SPY's session calendar, with an exact stock/benchmark date match.

    An integer horizon is in calendar days after the New York discovery date.
    A weekend/holiday target moves to the next available SPY session, never past
    as_of. 'latest' uses the last SPY session on or before as_of for every stock.
    No stale stock quote is forward-filled and no missing return is imputed.
    """
    cutoff = date.fromisoformat(as_of)
    entry = discovery_date(stock)
    if horizon != 'latest' and (not isinstance(horizon, int) or horizon < 1):
        raise ValueError('Horizon must be a positive integer or latest')
    target = cutoff if horizon == 'latest' else entry + timedelta(days=horizon)
    result = dict(discovery_id=stock['id'], ticker=stock['ticker'],
                  discovery_date=entry.isoformat(), recorded_discovery_price=stock['discovery_price'],
                  quality_score=stock['avg_quality_score'], mention_count=stock['mention_count'],
                  sector_etf=stock.get('sector_etf'), horizon=horizon, target_date=target.isoformat(),
                  price_date=None, actual_elapsed_days=None, status='not_due',
                  split_factor=None, normalized_entry_price=None, historical_close=None,
                  return_pct=None, spy_return_pct=None, excess_spy_pp=None,
                  sector_return_pct=None, excess_sector_pp=None)
    if target > cutoff or cutoff < entry:
        return result
    calendar = sorted(r['date'] for r in cache.get('SPY', {}).get('rows', [])
                      if valid_price(r.get('close')) and r['date'] <= as_of)
    available = calendar if horizon == 'latest' else [d for d in calendar if d >= target.isoformat()]
    if not available:
        result['status'] = 'market_calendar_unavailable'
        return result
    chosen = available[-1] if horizon == 'latest' else available[0]
    if chosen < entry.isoformat():
        return result
    result.update(price_date=chosen, actual_elapsed_days=(date.fromisoformat(chosen)-entry).days)
    series = cache.get(stock['ticker'])
    if not series:
        result['status'] = 'missing_stock_history'
        return result
    if series.get('currency') != 'USD':
        result['status'] = 'unsupported_currency'
        return result
    if any(r.get('split') and r['date'] == entry.isoformat() for r in series['rows']):
        result['status'] = 'split_on_discovery_date'
        return result
    ret = return_at(series, chosen, stock['discovery_price'], entry)
    if ret is None:
        result['status'] = 'missing_stock_price' if valid_price(stock['discovery_price']) else 'invalid_entry_price'
        return result
    factor = split_factor(series, entry)
    close = next(r['close'] for r in series['rows'] if r['date'] == chosen)
    spy = return_at(cache.get('SPY'), chosen, stock.get('spy_price_discovery'), entry)
    sector = return_at(cache.get(stock.get('sector_etf')), chosen,
                       stock.get('sector_etf_price_discovery'), entry)
    result.update(status='ok', split_factor=factor,
                  normalized_entry_price=stock['discovery_price']/factor,
                  historical_close=close, return_pct=ret, spy_return_pct=spy,
                  excess_spy_pp=ret-spy if spy is not None else None,
                  sector_return_pct=sector, excess_sector_pp=ret-sector if sector is not None else None)
    return result
