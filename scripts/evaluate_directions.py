"""Reconstruct discovery-time arguments and evaluate their directional outcomes."""
import argparse,csv,hashlib,json,re,sqlite3,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.backtesting.directional import reconstruct,direction_rows,summarize


def write_csv(path,rows):
    if not rows:return
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',type=Path,default=ROOT/'reddit_stocks.db')
    p.add_argument('--history-dir',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();args.output_dir.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((args.history_dir/'manifest.json').read_text())
    db_hash=hashlib.sha256(args.db.read_bytes()).hexdigest()
    if manifest['database_sha256']!=db_hash:p.error('Database differs from the historical evaluation snapshot')
    with sqlite3.connect(args.db.resolve().as_uri()+'?mode=ro',uri=True) as con:
        con.row_factory=sqlite3.Row
        stocks=[dict(r) for r in con.execute('SELECT * FROM tracked_stocks ORDER BY id')]
        assessments=[dict(r) for r in con.execute('SELECT * FROM analysis ORDER BY analyzed_at,id')]
    if len({s["ticker"] for s in stocks})!=len(stocks):
        p.error("Repeated discoveries of a ticker require discovery IDs in the historical explorer input")
    audits={};evidence=[]
    for stock in stocks:
        audit,items=reconstruct(stock,assessments)
        audits[stock['ticker']]=audit
        for a in items:
            evidence.append(dict(discovery_id=stock['id'],ticker=stock['ticker'],analysis_id=a['id'],
                                 source_type=a['source_type'],source_id=a['source_id'],analyzed_at=a['analyzed_at'],
                                 sentiment=a['sentiment'],quality_score=a['overall_score']))
    write_csv(args.output_dir/'discovery-audit.csv',list(audits.values()))
    write_csv(args.output_dir/'discovery-evidence.csv',evidence)
    rows=[]
    for raw in csv.DictReader((args.history_dir/'checkpoints.csv').open()):
        outcome={k:float(raw[k]) if raw[k] else None for k in ('return_pct','excess_spy_pp')}
        for r in direction_rows(audits[raw['ticker']],outcome):
            rows.append(dict(**r,horizon=raw['horizon'],price_date=raw['price_date'],price_status=raw['status']))
    write_csv(args.output_dir/'directional-checkpoints.csv',rows)
    summary={}
    for d in dict.fromkeys(r['horizon'] for r in rows):
        summary[d]={}
        for group in ('bull','bear','combined'):
            selected=[r for r in rows if r['horizon']==d and (group=='combined' or r['direction']==group)]
            summary[d][group]={metric:summarize(selected,metric) for metric in ('directional_return_pp','directional_excess_pp')}
    (args.output_dir/'directional-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    history=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',(args.history_dir/'results.html').read_text(),re.S).group(1))
    compact={}
    for d,items in history['rows'].items():
        compact[d]=[]
        for item in items:
            for r in direction_rows(audits[item[0]],dict(return_pct=item[2],excess_spy_pp=item[3])):
                compact[d].append([r['ticker'],r['quality_score'],r['assessment_count'],r['direction'],r['directional_return_pp'],r['directional_excess_pp'],item[4],item[5],r['discovery_id']])
    payload=dict(asOf=history['asOf'],maxDay=history['maxDay'],rows=compact,audit=list(audits.values()))
    text=(ROOT/'scripts/directional-report.html').read_text()
    (args.output_dir/'directional.html').write_text(text.replace('__REPORT_DATA__',json.dumps(payload,separators=(',',':')).replace('<','\\u003c')))
    provenance=dict(as_of=manifest['as_of'],generated_at=datetime.now(timezone.utc).isoformat(),database_sha256=db_hash,
                    lookback_days=7,matched_discoveries=sum(a['status']=='matched' for a in audits.values()),
                    total_discoveries=len(audits),reconstructed_assessments=len(evidence),
                    historical_manifest=manifest,
                    input_files_sha256={name:hashlib.sha256((args.history_dir/name).read_bytes()).hexdigest() for name in ('checkpoints.csv','results.html')},
                    source_files_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__),ROOT/'src/backtesting/directional.py',ROOT/'scripts/directional-report.html']})
    (args.output_dir/'directional-manifest.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(json.dumps(summary.get('90',summary),indent=2))


if __name__=='__main__':main()
