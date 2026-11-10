# src/scoring/factory.py
from src.scoring.scorer_interface import ScorerInterface, MockScorer
from src.scoring.anthropic_scorer import AnthropicScorer
from src.scoring.ollama_scorer import OllamaScorer
from src.scoring.gemini_scorer import GeminiScorer


def create_scorer(backend: str, **kwargs) -> ScorerInterface:
    if backend == "mock":
        return MockScorer(seed=kwargs.get("seed"))
    elif backend == "anthropic":
        return AnthropicScorer(
            api_key=kwargs["api_key"],
            model=kwargs.get("model", "claude-haiku-4-5-20251001"),
        )
    elif backend == "ollama":
        return OllamaScorer(
            model=kwargs.get("model", "llama3.2"),
            base_url=kwargs.get("base_url", "http://localhost:11434"),
        )
    elif backend == "gemini":
        return GeminiScorer(
            api_key=kwargs.get("api_key", ""),
            model=kwargs.get("model", "gemini-2.5-flash"),
            project=kwargs.get("project", ""),
            location=kwargs.get("location", ""),
            fallback_model=kwargs.get("fallback_model", ""),
        )
    else:
        raise ValueError(f"Unknown scoring backend: {backend}")
