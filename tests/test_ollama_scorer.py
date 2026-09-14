# tests/test_ollama_scorer.py
import json
import pytest
from unittest.mock import MagicMock, patch
from src.scoring.ollama_scorer import OllamaScorer
from src.scoring.scorer_interface import ScoreResult, PerTicketScoreResult


@pytest.fixture
def mock_ollama_response():
    return {
        "message": {
            "content": json.dumps([
                {
                    "tickers": [
                        {
                            "ticker": "TSLA",
                            "reasoning_score": 65,
                            "specificity_score": 55,
                            "novelty_score": 70,
                            "credibility_score": 60,
                            "sentiment": "bear",
                            "reasoning_summary": "Reasonable short thesis for Tesla",
                        }
                    ]
                }
            ])
        }
    }


class TestOllamaScorer:
    @patch("src.scoring.ollama_scorer.requests.post")
    def test_returns_per_ticker_results(self, mock_post, mock_ollama_response):
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_ollama_response
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        scorer = OllamaScorer(model="llama3.2", base_url="http://localhost:11434")
        results = scorer.score_batch(["TSLA is overvalued given their delivery numbers"])

        assert len(results) == 1
        assert isinstance(results[0], PerTicketScoreResult)
        assert len(results[0].ticker_scores) == 1
        assert results[0].ticker_scores[0].reasoning_score == 65
        assert results[0].ticker_scores[0].sentiment == "bear"

    @patch("src.scoring.ollama_scorer.requests.post")
    def test_handles_markdown_fences(self, mock_post):
        content = '```json\n[{"tickers": [{"ticker": "AAPL", "reasoning_score": 50, "specificity_score": 50, "novelty_score": 50, "credibility_score": 50, "sentiment": "bull", "reasoning_summary": "test"}]}]\n```'
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"message": {"content": content}}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        scorer = OllamaScorer(model="llama3.2", base_url="http://localhost:11434")
        results = scorer.score_batch(["some text"])
        assert len(results) == 1
        assert len(results[0].ticker_scores) == 1

    @patch("src.scoring.ollama_scorer.requests.post")
    def test_handles_connection_error(self, mock_post):
        mock_post.side_effect = Exception("Connection refused")

        scorer = OllamaScorer(model="llama3.2", base_url="http://localhost:11434")
        results = scorer.score_batch(["some text"])
        assert results == []
