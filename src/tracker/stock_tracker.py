# src/tracker/stock_tracker.py
from datetime import datetime, timezone
from collections import Counter
from src.db.database import Database
from src.tracker.benchmark import get_current_price, get_sector_etf
from src.analyzer.llm_scorer import EXCLUDED_TICKERS


def _utcnow() -> datetime:
    """Naive UTC, matching SQLite's datetime('now') values stored in the DB."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StockTracker:
    def __init__(self, db: Database, min_mentions: int, min_avg_score: float,
                 mention_lookback_days: int, retrack_cooldown_days: int,
                 checkpoints: list[int], sector_etf_map: dict[str, str]):
        self.db = db
        self.min_mentions = min_mentions
        self.min_avg_score = min_avg_score
        self.mention_lookback_days = mention_lookback_days
        self.retrack_cooldown_days = retrack_cooldown_days
        self.checkpoints = checkpoints
        self.sector_etf_map = sector_etf_map

    def discover(self) -> list[dict]:
        """Find new stocks worth tracking based on recent quality mentions."""
        discoveries = []
        tickers = self.db.get_all_recent_tickers(self.mention_lookback_days)

        for ticker in tickers:
            if ticker in EXCLUDED_TICKERS:
                continue
            if self.db.is_ticker_tracked_recently(ticker, self.retrack_cooldown_days):
                continue

            mentions = self.db.get_ticker_mentions(ticker, self.mention_lookback_days)
            if len(mentions) < self.min_mentions:
                continue

            avg_score = sum(m["overall_score"] for m in mentions) / len(mentions)
            if avg_score < self.min_avg_score:
                continue

            # Get prices
            stock_price = get_current_price(ticker)
            if stock_price is None:
                continue

            sector_etf = get_sector_etf(ticker, self.sector_etf_map)
            spy_price = get_current_price("SPY")
            sector_etf_price = get_current_price(sector_etf)

            counts = Counter(m.get("sentiment", "neutral") for m in mentions)
            leaders = [key for key, count in counts.items() if count == max(counts.values())]
            discovery_sentiment = leaders[0] if len(leaders) == 1 else "neutral"
            stock_id = self.db.insert_tracked_stock(
                ticker=ticker,
                discovery_price=stock_price,
                sector_etf=sector_etf,
                mention_count=len(mentions),
                avg_quality_score=round(avg_score, 2),
                spy_price_discovery=spy_price,
                sector_etf_price_discovery=sector_etf_price,
                discovery_sentiment=discovery_sentiment,
            )

            discoveries.append({
                "id": stock_id,
                "ticker": ticker,
                "price": stock_price,
                "mentions": len(mentions),
                "avg_score": round(avg_score, 2),
            })

        return discoveries

    def update_checkpoints(self) -> list[dict]:
        """Check and update price checkpoints for all active tracked stocks."""
        updates = []
        active = self.db.get_active_tracked_stocks()
        now = _utcnow()

        for stock in active:
            discovered = datetime.fromisoformat(stock["discovered_at"])
            days_since = (now - discovered).days

            for checkpoint in self.checkpoints:
                field_name = f"price_{checkpoint}d"
                if stock[field_name] is not None:
                    continue
                if days_since < checkpoint:
                    continue

                # Time to fill this checkpoint
                stock_price = get_current_price(stock["ticker"])
                spy_price = get_current_price("SPY")
                sector_etf_price = get_current_price(stock["sector_etf"])

                if stock_price is None:
                    continue

                self.db.update_checkpoint(
                    stock["id"], checkpoint,
                    stock_price=stock_price,
                    spy_price=spy_price,
                    sector_etf_price=sector_etf_price,
                    observed_at=_utcnow().isoformat(),
                )

                stock[field_name] = stock_price
                updates.append({
                    "ticker": stock["ticker"],
                    "checkpoint": checkpoint,
                    "price": stock_price,
                })

            # Mark completed if 90d checkpoint is filled
            if stock["price_90d"] is not None:
                self.db.mark_completed(stock["id"])

        return updates
