"""Discovery-time sentiment reconstruction and descriptive directional outcomes."""
from datetime import datetime, timedelta, timezone
from statistics import mean
from math import isclose


def timestamp(value):
    dt=datetime.fromisoformat(value)
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def reconstruct(stock, assessments, lookback_days=7):
    end=timestamp(stock['discovered_at']); start=end-timedelta(days=lookback_days)
    evidence=sorted([a for a in assessments if a['ticker']==stock['ticker'] and start<=timestamp(a['analyzed_at'])<=end],key=lambda a:(a['analyzed_at'],a['id']))
    avg=round(mean(a['overall_score'] for a in evidence),2) if evidence else None
    matched=len(evidence)==stock['mention_count'] and avg is not None and isclose(avg,stock['avg_quality_score'],abs_tol=1e-8)
    audit=dict(discovery_id=stock['id'],ticker=stock['ticker'],discovered_at=stock['discovered_at'],
               window_start=start.isoformat(),lookback_days=lookback_days,
               saved_count=stock['mention_count'],reconstructed_count=len(evidence),
               saved_score=stock['avg_quality_score'],reconstructed_score=avg,
               status='matched' if matched else 'aggregate_mismatch')
    for direction in ['bull','bear','neutral']:
        group=[a for a in evidence if a['sentiment']==direction]
        audit[direction+'_count']=len(group)
        audit[direction+'_score']=mean(a['overall_score'] for a in group) if group else None
    audit['unknown_count']=sum(a['sentiment'] not in ('bull','bear','neutral') for a in evidence)
    if audit['unknown_count']:
        audit['status']='unknown_sentiment'
    return audit,evidence


def direction_rows(audit, outcome):
    if audit['status']!='matched':
        return []
    directions=[d for d in ('bull','bear') if audit[d+'_count']]
    result=[]
    for direction in directions:
        sign=1 if direction=='bull' else -1
        result.append(dict(discovery_id=audit['discovery_id'],ticker=audit['ticker'],
                           direction=direction,quality_score=audit[direction+'_score'],
                           assessment_count=audit[direction+'_count'],stock_weight=1/len(directions),
                           directional_return_pp=sign*outcome['return_pct'] if outcome['return_pct'] is not None else None,
                           directional_excess_pp=sign*outcome['excess_spy_pp'] if outcome['excess_spy_pp'] is not None else None))
    return result


def weighted_ranks(values, weights):
    return [sum(w for v,w in zip(values,weights) if v<x)+sum(w for v,w in zip(values,weights) if v==x)/2 for x in values]


def weighted_median(values,weights):
    pairs=sorted(zip(values,weights)); half=sum(weights)/2; cumulative=0
    for i,(value,weight) in enumerate(pairs):
        cumulative+=weight
        if isclose(cumulative,half,abs_tol=1e-12) and i+1<len(pairs):
            return (value+pairs[i+1][0])/2
        if cumulative>=half:
            return value


def summarize(rows,metric):
    valid=[r for r in rows if r[metric] is not None]
    result=dict(unique_stocks=len({r['discovery_id'] for r in valid}),direction_groups=len(valid),
                mean_pp=None,median_pp=None,positive_pct=None,tie_pct=None,weighted_rank_correlation=None)
    if not valid:return result
    # Recompute weights after filtering to a direction: every represented stock
    # contributes total weight one in both separate and combined summaries.
    counts={i:sum(r['discovery_id']==i for r in valid) for i in {r['discovery_id'] for r in valid}}
    weights=[1/counts[r['discovery_id']] for r in valid];total=sum(weights)
    values=[r[metric] for r in valid];scores=[r['quality_score'] for r in valid]
    result.update(mean_pp=sum(v*w for v,w in zip(values,weights))/total,
                  median_pp=weighted_median(values,weights),
                  positive_pct=100*sum(w for v,w in zip(values,weights) if v>0)/total,
                  tie_pct=100*sum(w for v,w in zip(values,weights) if v==0)/total)
    a=weighted_ranks(scores,weights);b=weighted_ranks(values,weights)
    am=sum(v*w for v,w in zip(a,weights))/total;bm=sum(v*w for v,w in zip(b,weights))/total
    den=(sum(w*(v-am)**2 for v,w in zip(a,weights))*sum(w*(v-bm)**2 for v,w in zip(b,weights)))**.5
    if len(counts)>=3 and den:
        result['weighted_rank_correlation']=sum(w*(x-am)*(y-bm) for x,y,w in zip(a,b,weights))/den
    return result
