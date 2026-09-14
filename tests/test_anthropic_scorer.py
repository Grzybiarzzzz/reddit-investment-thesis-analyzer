# tests/test_anthropic_scorer.py
import json
import pytest
from unittest.mock import MagicMock, patch
from src.scoring.anthropic_scorer import AnthropicScorer
from src.scoring.scorer_interface import ScoreResult, PerTicketScoreResult


@pytest.fixture
def mock_response():
    """Simulates what the Anthropic API returns with per-ticker format."""
    scores = [
        {
            "tickers": [
                {
                    "ticker": "AAPL",
                    "reasoning_score": 75,
                    "specificity_score": 60,
                    "novelty_score": 45,
                    "credibility_score": 80,
                    "sentiment": "bull",
                    "reasoning_summary": "Well-argued earnings thesis for Apple",
                }
            ]
        }
    ]
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(scores))]
    return mock_msg


class TestAnthropicScorer:
    @patch("src.scoring.anthropic_scorer.anthropic.Anthropic")
    def test_returns_per_ticker_results(self, mock_client_cls, mock_response):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_client_cls.return_value = mock_client

        scorer = AnthropicScorer(api_key="test-key", model="claude-haiku-4-5-20251001")
        results = scorer.score_batch(["AAPL earnings look great because of iPhone sales growth"])

        assert len(results) == 1
        assert isinstance(results[0], PerTicketScoreResult)
        assert len(results[0].ticker_scores) == 1
        assert results[0].ticker_scores[0].reasoning_score == 75
        assert results[0].ticker_scores[0].sentiment == "bull"
        assert results[0].ticker_scores[0].tickers_mentioned == ["AAPL"]

    @patch("src.scoring.anthropic_scorer.anthropic.Anthropic")
    def test_multiple_tickers_per_text(self, mock_client_cls):
        scores = [
            {
                "tickers": [
                    {
                        "ticker": "NVDA",
                        "reasoning_score": 85,
                        "specificity_score": 80,
                        "novelty_score": 70,
                        "credibility_score": 90,
                        "sentiment": "bull",
                        "reasoning_summary": "Strong NVDA thesis",
                    },
                    {
                        "ticker": "NBIS",
                        "reasoning_score": 40,
                        "specificity_score": 30,
                        "novelty_score": 20,
                        "credibility_score": 50,
                        "sentiment": "neutral",
                        "reasoning_summary": "Weak mention of NBIS",
                    },
                ]
            }
        ]
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(scores))]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        mock_client_cls.return_value = mock_client

        scorer = AnthropicScorer(api_key="test-key", model="claude-haiku-4-5-20251001")
        results = scorer.score_batch(["NVDA invested $2B in NBIS"])

        assert len(results) == 1
        assert len(results[0].ticker_scores) == 2
        assert results[0].ticker_scores[0].reasoning_score == 85
        assert results[0].ticker_scores[1].reasoning_score == 40

    @patch("src.scoring.anthropic_scorer.anthropic.Anthropic")
    def test_empty_tickers_for_no_thesis(self, mock_client_cls):
        scores = [{"tickers": []}]
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=json.dumps(scores))]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        mock_client_cls.return_value = mock_client

        scorer = AnthropicScorer(api_key="test-key", model="claude-haiku-4-5-20251001")
        results = scorer.score_batch(["just a random comment with no thesis"])

        assert len(results) == 1
        assert results[0].ticker_scores == []

    @patch("src.scoring.anthropic_scorer.anthropic.Anthropic")
    def test_handles_api_error_gracefully(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")
        mock_client_cls.return_value = mock_client

        scorer = AnthropicScorer(api_key="test-key", model="claude-haiku-4-5-20251001")
        results = scorer.score_batch(["some text"])
        # Should return empty results on error, not crash
        assert results == []
