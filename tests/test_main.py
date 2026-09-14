# tests/test_main.py
import pytest
from unittest.mock import MagicMock, patch


class TestMainPipeline:
    @patch("main.ConsoleReporter")
    @patch("main.StockTracker")
    @patch("main.analyze_content")
    @patch("main.RedditScraper")
    @patch("main.create_scorer")
    @patch("main.Database")
    @patch("main.TickerExtractor")
    def test_pipeline_runs_all_stages(
        self, mock_extractor_cls, mock_db_cls, mock_scorer_factory,
        mock_scraper_cls, mock_analyze, mock_tracker_cls, mock_reporter_cls
    ):
        from main import run_pipeline

        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db

        mock_scraper = MagicMock()
        mock_scraper.scrape.return_value = ([], [])
        mock_scraper_cls.return_value = mock_scraper

        mock_analyze.return_value = {"posts_analyzed": 0, "comments_analyzed": 0, "filtered_out": 0, "scored": 0}

        mock_tracker = MagicMock()
        mock_tracker.discover.return_value = []
        mock_tracker.update_checkpoints.return_value = []
        mock_tracker_cls.return_value = mock_tracker

        mock_db.get_active_tracked_stocks.return_value = []

        run_pipeline(["scrape", "analyze", "track"])

        # Verify all stages were called
        mock_db.initialize.assert_called_once()
        mock_scraper.scrape.assert_called_once()
        mock_analyze.assert_called_once()
        mock_tracker.discover.assert_called_once()
        mock_tracker.update_checkpoints.assert_called_once()
