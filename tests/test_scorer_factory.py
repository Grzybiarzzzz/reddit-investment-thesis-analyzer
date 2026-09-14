# tests/test_scorer_factory.py
import pytest
from src.scoring.factory import create_scorer
from src.scoring.scorer_interface import MockScorer
from src.scoring.anthropic_scorer import AnthropicScorer
from src.scoring.ollama_scorer import OllamaScorer
from src.scoring.gemini_scorer import GeminiScorer
from unittest.mock import patch


class TestScorerFactory:
    def test_creates_mock_scorer(self):
        scorer = create_scorer("mock")
        assert isinstance(scorer, MockScorer)

    @patch("src.scoring.factory.anthropic.Anthropic")
    def test_creates_anthropic_scorer(self, mock_cls):
        scorer = create_scorer("anthropic", api_key="test", model="claude-haiku-4-5-20251001")
        assert isinstance(scorer, AnthropicScorer)

    def test_creates_ollama_scorer(self):
        scorer = create_scorer("ollama", model="llama3.2", base_url="http://localhost:11434")
        assert isinstance(scorer, OllamaScorer)

    @patch("src.scoring.gemini_scorer.genai.Client")
    def test_creates_gemini_scorer(self, mock_cls):
        scorer = create_scorer("gemini", api_key="test", model="gemini-2.5-flash")
        assert isinstance(scorer, GeminiScorer)

    def test_raises_on_unknown_backend(self):
        with pytest.raises(ValueError, match="Unknown scoring backend"):
            create_scorer("unknown_backend")
