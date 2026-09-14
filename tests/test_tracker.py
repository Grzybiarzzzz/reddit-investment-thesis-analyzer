# tests/test_tracker.py
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from src.tracker.benchmark import get_current_price, get_sector_etf
from src.tracker.stock_tracker import StockTracker


class TestBenchmark:
    @patch("src.tracker.benchmark.yf.Ticker")
    def test_get_current_price(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": 178.50}
        mock_ticker_cls.return_value = mock_ticker

        price = get_current_price("AAPL")
        assert price == 178.50

    @patch("src.tracker.benchmark.yf.Ticker")
    def test_get_current_price_fallback(self, mock_ticker_cls):
        mock_ticker = MagicMock()
        mock_ticker.info = {"regularMarketPrice": 178.50}
        mock_ticker_cls.return_value = mock_ticker

        price = get_current_price("AAPL")
        assert price == 178.50

    @patch("src.tracker.benchmark.yf.Ticker")
    def test_get_current_price_returns_none_on_error(self, mock_ticker_cls):
        mock_ticker_cls.side_effect = Exception("Network error")

        price = get_current_price("INVALID")
        assert price is None

    @patch("src.tracker.benchmark.yf.Ticker")
    def test_get_sector_etf_known(self, mock_ticker):
        mock_ticker.return_value.info = {"sector": "Technology"}
        etf = get_sector_etf("AAPL", {"Technology": "XLK"})
        assert etf == "XLK"

    @patch("src.tracker.benchmark.yf.Ticker")
    def test_get_sector_etf_unknown_returns_spy(self, mock_ticker):
        mock_ticker.return_value.info = {}
        etf = get_sector_etf("UNKNOWN_TICKER", {})
        assert etf == "SPY"


class TestStockTracker:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.get_all_recent_tickers.return_value = ["AAPL", "TSLA"]
        db.get_ticker_mentions.return_value = [
            {"overall_score": 75},
            {"overall_score": 80},
            {"overall_score": 70},
        ]
        db.is_ticker_tracked_recently.return_value = False
        return db

    @patch("src.tracker.stock_tracker.get_current_price")
    @patch("src.tracker.stock_tracker.get_sector_etf")
    def test_discovers_new_stocks(self, mock_etf, mock_price, mock_db):
        mock_price.return_value = 178.50
        mock_etf.return_value = "XLK"

        tracker = StockTracker(
            db=mock_db,
            min_mentions=3,
            min_avg_score=60,
            mention_lookback_days=7,
            retrack_cooldown_days=90,
            checkpoints=[7, 14, 30, 90],
            sector_etf_map={"Technology": "XLK"},
        )
        discoveries = tracker.discover()

        assert len(discoveries) == 2
        assert mock_db.insert_tracked_stock.call_count == 2

    @patch("src.tracker.stock_tracker.get_current_price")
    @patch("src.tracker.stock_tracker.get_sector_etf")
    def test_skips_already_tracked(self, mock_etf, mock_price, mock_db):
        mock_db.is_ticker_tracked_recently.return_value = True
        mock_price.return_value = 178.50
        mock_etf.return_value = "XLK"

        tracker = StockTracker(
            db=mock_db, min_mentions=3, min_avg_score=60,
            mention_lookback_days=7, retrack_cooldown_days=90,
            checkpoints=[7, 14, 30, 90], sector_etf_map={},
        )
        discoveries = tracker.discover()
        assert len(discoveries) == 0

    @patch("src.tracker.stock_tracker.get_current_price")
    def test_skips_low_quality(self, mock_price, mock_db):
        mock_db.get_ticker_mentions.return_value = [
            {"overall_score": 30},
            {"overall_score": 20},
            {"overall_score": 40},
        ]

        tracker = StockTracker(
            db=mock_db, min_mentions=3, min_avg_score=60,
            mention_lookback_days=7, retrack_cooldown_days=90,
            checkpoints=[7, 14, 30, 90], sector_etf_map={},
        )
        discoveries = tracker.discover()
        assert len(discoveries) == 0

    @patch("src.tracker.stock_tracker.get_current_price")
    def test_update_checkpoints(self, mock_price, mock_db):
        mock_price.return_value = 185.00
        now = datetime.utcnow()
        mock_db.get_active_tracked_stocks.return_value = [
            {
                "id": 1,
                "ticker": "AAPL",
                "discovered_at": (now - timedelta(days=7)).isoformat(),
                "sector_etf": "XLK",
                "price_7d": None,
                "price_14d": None,
                "price_30d": None,
                "price_90d": None,
            }
        ]

        tracker = StockTracker(
            db=mock_db, min_mentions=3, min_avg_score=60,
            mention_lookback_days=7, retrack_cooldown_days=90,
            checkpoints=[7, 14, 30, 90], sector_etf_map={},
        )
        updates = tracker.update_checkpoints()
        assert len(updates) > 0
        mock_db.update_checkpoint.assert_called()
