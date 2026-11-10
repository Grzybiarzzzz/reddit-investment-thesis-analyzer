from datetime import datetime, timedelta, timezone

from src.db.database import Database


def test_pending_sources_survive_reopening(tmp_path):
    path = str(tmp_path / 'pending.db')
    db = Database(path)
    db.initialize()
    db.insert_post('p', 'stocks', 'AAPL', 'buy AAPL', 3, '', '2026-01-01')
    db.insert_comment('c', 'p', 'buy AAPL', 3, '2026-01-01')
    db.close()
    db = Database(path)
    db.initialize()
    assert [r['id'] for r in db.get_unanalyzed_posts()] == ['p']
    assert [r['id'] for r in db.get_unanalyzed_comments()] == ['c']
    db.mark_processed('post', 'p')
    db.conn.commit()
    db.close()
    db = Database(path)
    db.initialize()
    assert db.get_unanalyzed_posts() == []
    assert len(db.get_unanalyzed_comments()) == 1
    db.close()


def test_delayed_checkpoint_records_actual_fetch_time_and_preserves_history(tmp_path, monkeypatch):
    from src.tracker.stock_tracker import StockTracker
    db = Database(str(tmp_path / 'tracking.db'))
    db.initialize()
    stock_id = db.insert_tracked_stock('AAPL', 100, 'XLK', 5, 75, 100, 100)
    db.execute('UPDATE tracked_stocks SET discovered_at=? WHERE id=?',
               ((datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=16)).isoformat(), stock_id))
    db.update_checkpoint(stock_id, 7, 110, 102, 103)
    monkeypatch.setattr('src.tracker.stock_tracker.get_current_price', lambda t: {'AAPL':120,'SPY':105,'XLK':106}[t])
    tracker = StockTracker(db, 5, 65, 7, 90, [7,14,30,90], {})
    tracker.update_checkpoints()
    row = dict(db.execute('SELECT * FROM tracked_stocks').fetchone())
    assert row['price_7d'] == 110
    assert row.get('observed_at_7d') is None
    assert row.get('observed_at_14d') is not None
    elapsed = (datetime.fromisoformat(row['observed_at_14d']) - datetime.fromisoformat(row['discovered_at'])).days
    assert elapsed == 16
    assert row['price_14d'] == 120
    assert row['price_30d'] is None
    db.close()


def test_failed_final_checkpoint_does_not_complete_stock(tmp_path, monkeypatch):
    from src.tracker.stock_tracker import StockTracker
    db = Database(str(tmp_path / 'incomplete.db')); db.initialize()
    sid = db.insert_tracked_stock('AAPL',100,'XLK',5,75,100,100)
    db.execute('UPDATE tracked_stocks SET discovered_at=? WHERE id=?',
               ((datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(days=100)).isoformat(),sid))
    for day in [7,14,30]: db.update_checkpoint(sid,day,101,101,101)
    monkeypatch.setattr('src.tracker.stock_tracker.get_current_price',lambda t:None)
    StockTracker(db,5,65,7,90,[7,14,30,90],{}).update_checkpoints()
    assert db.execute('SELECT status FROM tracked_stocks').fetchone()[0]=='active'
    db.close()


def test_sentiment_is_frozen_at_discovery(tmp_path, monkeypatch):
    from src.tracker.stock_tracker import StockTracker
    db=Database(str(tmp_path/'snapshot.db'));db.initialize()
    for i in range(5):
        db.insert_analysis('post',str(i),'AAPL','bear',80,80,80,80,80,'',True,True)
    monkeypatch.setattr('src.tracker.stock_tracker.get_current_price',lambda t:100)
    monkeypatch.setattr('src.tracker.stock_tracker.get_sector_etf',lambda *a:'XLK')
    StockTracker(db,5,65,7,90,[7,14,30,90],{}).discover()
    for i in range(5,20):
        db.insert_analysis('post',str(i),'AAPL','bull',90,90,90,90,90,'',True,True)
    row=dict(db.execute('SELECT * FROM tracked_stocks').fetchone())
    assert row.get('discovery_sentiment')=='bear'
    assert row['avg_quality_score']==80
    db.close()


def test_already_filled_final_checkpoint_completes_without_fetch(tmp_path, monkeypatch):
    from src.tracker.stock_tracker import StockTracker
    db=Database(str(tmp_path/'complete.db'));db.initialize()
    sid=db.insert_tracked_stock('AAPL',100,'XLK',5,75,100,100)
    db.execute('UPDATE tracked_stocks SET discovered_at=? WHERE id=?',
               ((datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(days=100)).isoformat(),sid))
    # A custom checkpoint list must not rely on a price variable from a loop iteration.
    db.update_checkpoint(sid,90,110,105,104)
    def forbidden(t): raise AssertionError('No fetch should be needed')
    monkeypatch.setattr('src.tracker.stock_tracker.get_current_price',forbidden)
    StockTracker(db,5,65,7,90,[],{}).update_checkpoints()
    assert db.execute('SELECT status FROM tracked_stocks').fetchone()[0]=='completed'
    db.close()


def research_client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from src.api.app import create_app
    path=str(tmp_path/'api.db')
    monkeypatch.setattr('config.settings.DB_PATH',path)
    monkeypatch.setattr('config.settings.DASHBOARD_API_KEY','')
    db=Database(path);db.initialize()
    return db,TestClient(create_app())


def test_score_groups_count_discoveries_once_at_one_horizon(tmp_path,monkeypatch):
    db,client=research_client(tmp_path,monkeypatch)
    a=db.insert_tracked_stock('AAPL',100,'XLK',5,80,100,100)
    b=db.insert_tracked_stock('MSFT',100,'XLK',5,80,100,100)
    db.update_checkpoint(a,7,110,100,100)
    db.update_checkpoint(a,14,150,100,100)
    db.update_checkpoint(b,7,90,100,100)
    for i in range(20):
        db.insert_analysis('post',str(i),'AAPL','bull',20,20,20,20,20,'',True,True)
    result=client.get('/api/analytics?checkpoint=7').json()
    bucket=next(r for r in result['accuracy_by_score'] if r['score_range']=='70-100')
    assert bucket['count']==2
    assert bucket['avg_return']==0
    db.close()


def test_portfolio_excludes_missing_benchmark_from_comparison(tmp_path,monkeypatch):
    db,client=research_client(tmp_path,monkeypatch)
    sid=db.insert_tracked_stock('AAPL',100,'XLK',5,80,0,100)
    db.update_checkpoint(sid,7,110,0,100)
    result=client.get('/api/portfolio').json()
    assert result['checkpoints']['7'] is None
    db.close()


def test_portfolio_descriptive_statistics_use_requested_horizon(tmp_path,monkeypatch):
    db,client=research_client(tmp_path,monkeypatch)
    for ticker,price in [('AAPL',110),('MSFT',130)]:
        sid=db.insert_tracked_stock(ticker,100,'XLK',5,80,100,100)
        db.update_checkpoint(sid,7,price,100,100)
        db.update_checkpoint(sid,14,200,100,100)
    result=client.get('/api/portfolio?checkpoint=7').json()
    stats=result['insights']['statistics']
    assert stats['median_return']==20
    assert stats.get('p_value') is None
    assert stats.get('significant') is None
    assert result['insights']['sentiment_accuracy'].get('neutral',{}).get('accuracy') is None
    db.close()


def test_portfolio_does_not_infer_legacy_sentiment_from_future_posts(tmp_path,monkeypatch):
    db,client=research_client(tmp_path,monkeypatch)
    db.insert_tracked_stock('AAPL',100,'XLK',5,80,100,100)
    for i in range(5):
        db.insert_analysis('post',str(i),'AAPL','bull',80,80,80,80,80,'',True,True)
    result=client.get('/api/portfolio?sentiment=bull').json()
    assert result['filtered_count']==0
    db.close()


def test_dashboard_uses_seven_day_complete_pairs(tmp_path,monkeypatch):
    db,client=research_client(tmp_path,monkeypatch)
    a=db.insert_tracked_stock('AAPL',100,'XLK',5,80,100,100)
    b=db.insert_tracked_stock('MSFT',100,'XLK',5,80,0,100)
    db.update_checkpoint(a,7,110,100,100)
    db.update_checkpoint(a,14,150,100,100)
    db.update_checkpoint(b,7,200,0,100)
    k=client.get('/api/dashboard').json()['kpis']
    assert k['avg_alpha_30d']==10  # Existing key retained for API compatibility.
    assert k['portfolio']['7']['count']==1
    db.close()
