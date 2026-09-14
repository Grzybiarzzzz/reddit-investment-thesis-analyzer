import pytest
from src.backtesting import historical


def prices(rows):
    return {'currency':'USD','rows':[{'date':d,'close':p,'split':s} for d,p,s in rows]}


def stock():
    return dict(id=1,ticker='TEST',discovered_at='2026-03-13 19:00:00',discovery_price=100,
                spy_price_discovery=100,sector_etf='XLK',sector_etf_price_discovery=100,
                avg_quality_score=75,mention_count=5)


def test_split_adjusts_saved_entry_even_for_targets_before_the_split():
    cache={'TEST':prices([('2026-03-20',60,0),('2026-04-01',65,2)]),
           'SPY':prices([('2026-03-20',110,0),('2026-04-01',112,0)]),
           'XLK':prices([('2026-03-20',105,0),('2026-04-01',109,0)])}
    r=historical.evaluate(stock(),cache,'2026-04-01',7)
    assert r['status']=='ok'
    assert r['split_factor']==2
    assert r['return_pct']==pytest.approx(20)
    assert r['excess_spy_pp']==pytest.approx(10)
    assert r['excess_sector_pp']==pytest.approx(15)


def test_weekend_target_uses_first_market_session_on_or_after():
    cache={t:prices([('2026-03-20',110,0),('2026-03-23',120,0)]) for t in ['TEST','SPY','XLK']}
    r=historical.evaluate(stock(),cache,'2026-03-23',8)
    assert r['target_date']=='2026-03-21'
    assert r['price_date']=='2026-03-23'
    assert r['actual_elapsed_days']==10


def test_missing_stock_on_target_session_is_not_filled_from_a_later_date():
    cache={'TEST':prices([('2026-03-23',120,0)]),'SPY':prices([('2026-03-20',110,0),('2026-03-23',112,0)])}
    assert historical.evaluate(stock(),cache,'2026-03-23',7)['status']=='missing_stock_price'


def test_future_checkpoint_does_not_use_latest_available_price():
    cache={t:prices([('2026-03-20',110,0)]) for t in ['TEST','SPY','XLK']}
    assert historical.evaluate(stock(),cache,'2026-03-20',90)['status']=='not_due'


def test_latest_uses_one_common_market_date_and_never_a_future_row():
    cache={t:prices([('2026-03-20',110,0),('2026-03-23',120,0)]) for t in ['TEST','SPY','XLK']}
    r=historical.evaluate(stock(),cache,'2026-03-22','latest')
    assert r['price_date']=='2026-03-20'
    assert r['return_pct']==pytest.approx(10)


def test_missing_saved_benchmark_is_not_zero_return():
    s=stock();s['spy_price_discovery']=0
    cache={t:prices([('2026-03-20',110,0)]) for t in ['TEST','SPY','XLK']}
    r=historical.evaluate(s,cache,'2026-03-20',7)
    assert r['return_pct']==pytest.approx(10)
    assert r['spy_return_pct'] is None and r['excess_spy_pp'] is None


def test_same_day_split_requires_entry_price_review():
    cache={t:prices([('2026-03-13',50,2),('2026-03-20',60,0)]) for t in ['TEST','SPY','XLK']}
    assert historical.evaluate(stock(),cache,'2026-03-20',7)['status']=='split_on_discovery_date'


def test_stale_price_history_cannot_imply_current_or_future_market_coverage():
    cache={t:prices([('2026-03-20',110,0)]) for t in ['TEST','SPY','XLK']}
    assert historical.evaluate(stock(),cache,'2026-09-13',90)['status']=='market_calendar_unavailable'


def test_non_usd_series_is_not_compared_to_saved_dollar_quote():
    cache={t:prices([('2026-03-20',110,0)]) for t in ['TEST','SPY','XLK']}
    cache['TEST']['currency']='GBP'
    assert historical.evaluate(stock(),cache,'2026-03-20',7)['status']=='unsupported_currency'
