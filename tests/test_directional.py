import pytest
from src.backtesting.directional import reconstruct, direction_rows, summarize


def stock():
    return dict(id=1,ticker='TEST',discovered_at='2026-03-20 12:00:00',mention_count=3,avg_quality_score=70)


def assessments():
    return [dict(id=i,ticker='TEST',analyzed_at=t,sentiment=d,overall_score=q) for i,t,d,q in [
        (1,'2026-03-13 12:00:00','bull',60),(2,'2026-03-19 12:00:00','bear',90),
        (3,'2026-03-20 12:00:00','neutral',60),(4,'2026-03-20 12:00:01','bull',100),
        (5,'2026-03-13 11:59:59','bear',100)]]


def test_reconstruction_excludes_future_and_old_assessments_and_matches_saved_aggregate():
    audit, evidence = reconstruct(stock(), assessments())
    assert audit['status']=='matched'
    assert [r['id'] for r in evidence]==[1,2,3]
    assert audit['bull_score']==60 and audit['bear_score']==90
    assert audit['neutral_count']==1


def test_mismatch_cannot_enter_directional_results():
    s=stock();s['avg_quality_score']=99
    audit,_=reconstruct(s,assessments())
    assert audit['status']=='aggregate_mismatch'
    assert direction_rows(audit,dict(return_pct=10,excess_spy_pp=5))==[]


def test_bearish_decline_is_positive_directional_outcome_and_neutral_is_excluded():
    audit,_=reconstruct(stock(),assessments())
    rows=direction_rows(audit,dict(return_pct=-20,excess_spy_pp=-30))
    assert len(rows)==2
    bear=next(r for r in rows if r['direction']=='bear')
    assert bear['directional_return_pp']==20 and bear['directional_excess_pp']==30
    assert sum(r['stock_weight'] for r in rows)==1


def test_missing_benchmark_does_not_remove_absolute_direction_or_impute_zero():
    audit,_=reconstruct(stock(),assessments())
    rows=direction_rows(audit,dict(return_pct=10,excess_spy_pp=None))
    assert all(r['directional_excess_pp'] is None for r in rows)
    assert summarize(rows,'directional_return_pp')['unique_stocks']==1
    assert summarize(rows,'directional_excess_pp')['unique_stocks']==0


def test_combined_summary_weights_stocks_equally_not_comments_or_sides():
    rows=[dict(discovery_id=1,quality_score=50,stock_weight=1,directional_return_pp=10),
          dict(discovery_id=2,quality_score=60,stock_weight=.5,directional_return_pp=-20),
          dict(discovery_id=2,quality_score=80,stock_weight=.5,directional_return_pp=20)]
    s=summarize(rows,'directional_return_pp')
    assert s['unique_stocks']==2 and s['direction_groups']==3
    assert s['mean_pp']==5
    assert s['positive_pct']==75


def test_zero_is_a_tie_and_constant_quality_has_no_correlation():
    rows=[dict(discovery_id=i,quality_score=70,stock_weight=1,directional_return_pp=r) for i,r in enumerate([0,1,-1])]
    s=summarize(rows,'directional_return_pp')
    assert s['positive_pct']==pytest.approx(100/3)
    assert s['tie_pct']==pytest.approx(100/3)
    assert s['weighted_rank_correlation'] is None
