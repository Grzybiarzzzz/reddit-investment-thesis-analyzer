# tests/test_console_reporter.py
import pytest
from src.reports.console_reporter import ConsoleReporter


class TestConsoleReporter:
    def test_format_discoveries(self):
        reporter = ConsoleReporter()
        discoveries = [
            {"ticker": "AAPL", "price": 178.50, "mentions": 5, "avg_score": 72.5},
            {"ticker": "TSLA", "price": 245.00, "mentions": 3, "avg_score": 65.0},
        ]
        output = reporter.format_discoveries(discoveries)
        assert "AAPL" in output
        assert "TSLA" in output
        assert "178.50" in output

    def test_format_discoveries_empty(self):
        reporter = ConsoleReporter()
        output = reporter.format_discoveries([])
        assert "No new" in output

    def test_format_checkpoints(self):
        reporter = ConsoleReporter()
        updates = [
            {"ticker": "AAPL", "checkpoint": 7, "price": 185.00},
        ]
        output = reporter.format_checkpoints(updates)
        assert "AAPL" in output
        assert "7" in output

    def test_format_performance(self):
        reporter = ConsoleReporter()
        stocks = [
            {
                "ticker": "AAPL",
                "discovery_price": 178.50,
                "price_30d": 195.00,
                "spy_price_discovery": 500.00,
                "spy_price_30d": 510.00,
            },
        ]
        output = reporter.format_performance(stocks, checkpoint=30)
        assert "AAPL" in output
        assert "%" in output
