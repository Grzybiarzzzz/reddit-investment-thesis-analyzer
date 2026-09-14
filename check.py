"""Quick CLI to check analysis results."""
import sys
from src.db.database import Database
from config.settings import DB_PATH


def show_top_scores(limit=20):
    db = Database(DB_PATH)
    db.initialize()
    rows = db.execute("""
        SELECT ticker, sentiment, reasoning_score, specificity_score,
               novelty_score, credibility_score, overall_score, reasoning_summary
        FROM analysis
        WHERE llm_scored = 1
        ORDER BY overall_score DESC
        LIMIT ?
    """, (limit,)).fetchall()

    if not rows:
        print("No scored entries yet. Run the pipeline first: python main.py")
        return

    print(f"\n{'Ticker':<8} {'Sent':<8} {'R':>3} {'S':>3} {'N':>3} {'C':>3} {'OVR':>4}  Summary")
    print("-" * 90)
    for r in rows:
        d = dict(r)
        print(f"{d['ticker']:<8} {d['sentiment']:<8} {d['reasoning_score']:3d} {d['specificity_score']:3d} "
              f"{d['novelty_score']:3d} {d['credibility_score']:3d} {d['overall_score']:4d}  "
              f"{d['reasoning_summary'][:45]}")
    db.close()


def show_ticker(ticker):
    db = Database(DB_PATH)
    db.initialize()
    ticker = ticker.upper()

    rows = db.execute("""
        SELECT a.*,
               CASE WHEN a.source_type = 'post' THEN p.title
                    ELSE substr(c.body, 1, 100) END as source_text
        FROM analysis a
        LEFT JOIN posts p ON a.source_type = 'post' AND a.source_id = p.id
        LEFT JOIN comments c ON a.source_type = 'comment' AND a.source_id = c.id
        WHERE a.ticker = ?
        ORDER BY a.overall_score DESC
    """, (ticker,)).fetchall()

    if not rows:
        print(f"No analysis found for {ticker}")
        return

    print(f"\n=== {ticker} - {len(rows)} mention(s) ===\n")
    for r in rows:
        d = dict(r)
        print(f"  [{d['sentiment']:>7}] Score: {d['overall_score']:3d}  (R:{d['reasoning_score']} S:{d['specificity_score']} N:{d['novelty_score']} C:{d['credibility_score']})")
        print(f"           {d['reasoning_summary'][:80]}")
        print(f"           Source: {d['source_text'][:80]}...")
        print()
    db.close()


def show_tracked():
    db = Database(DB_PATH)
    db.initialize()
    rows = db.execute("SELECT * FROM tracked_stocks ORDER BY discovered_at DESC").fetchall()

    if not rows:
        print("No tracked stocks yet. Need more data - run the pipeline daily.")
        return

    print(f"\n{'Ticker':<8} {'Discovered':<12} {'Price':>8} {'Mentions':>8} {'Avg Score':>9} {'Status':<10}")
    print("-" * 65)
    for r in rows:
        d = dict(r)
        print(f"{d['ticker']:<8} {d['discovered_at'][:10]:<12} ${d['discovery_price']:>7.2f} "
              f"{d['mention_count']:>8} {d['avg_quality_score']:>9.1f} {d['status']:<10}")
    db.close()


def show_stats():
    db = Database(DB_PATH)
    db.initialize()

    posts = db.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    comments = db.execute("SELECT COUNT(*) FROM comments").fetchone()[0]
    analyzed = db.execute("SELECT COUNT(*) FROM analysis WHERE llm_scored = 1").fetchone()[0]
    tickers = db.execute("SELECT COUNT(DISTINCT ticker) FROM analysis").fetchone()[0]
    tracked = db.execute("SELECT COUNT(*) FROM tracked_stocks").fetchone()[0]

    print(f"\n=== Database Stats ===")
    print(f"  Posts scraped:     {posts}")
    print(f"  Comments scraped:  {comments}")
    print(f"  LLM-scored items:  {analyzed}")
    print(f"  Unique tickers:    {tickers}")
    print(f"  Tracked stocks:    {tracked}")
    db.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python check.py top [N]      - Top N scored mentions (default 20)")
        print("  python check.py ticker AAPL  - All mentions of a specific ticker")
        print("  python check.py tracked      - Currently tracked stocks")
        print("  python check.py stats        - Database statistics")
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == "top":
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        show_top_scores(limit)
    elif cmd == "ticker":
        if len(sys.argv) < 3:
            print("Usage: python check.py ticker AAPL")
        else:
            show_ticker(sys.argv[2])
    elif cmd == "tracked":
        show_tracked()
    elif cmd == "stats":
        show_stats()
    else:
        print(f"Unknown command: {cmd}")
