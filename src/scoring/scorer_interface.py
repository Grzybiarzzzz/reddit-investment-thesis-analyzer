# src/scoring/scorer_interface.py
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


def _clamp(value: int) -> int:
    return max(0, min(100, value))


@dataclass
class ScoreResult:
    reasoning_score: int
    specificity_score: int
    novelty_score: int
    credibility_score: int
    sentiment: str  # "bull", "bear", "neutral"
    reasoning_summary: str
    tickers_mentioned: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.reasoning_score = _clamp(self.reasoning_score)
        self.specificity_score = _clamp(self.specificity_score)
        self.novelty_score = _clamp(self.novelty_score)
        self.credibility_score = _clamp(self.credibility_score)
        # Normalize sentiment - LLMs sometimes return variations
        sentiment_lower = str(self.sentiment).lower().strip()
        if sentiment_lower in ("bullish", "positive", "buy", "long"):
            self.sentiment = "bull"
        elif sentiment_lower in ("bearish", "negative", "sell", "short"):
            self.sentiment = "bear"
        elif sentiment_lower not in ("bull", "bear"):
            self.sentiment = "neutral"

    def calculate_overall(self, weights: dict[str, float]) -> int:
        total = (
            self.reasoning_score * weights["reasoning"]
            + self.specificity_score * weights["specificity"]
            + self.novelty_score * weights["novelty"]
            + self.credibility_score * weights["credibility"]
        )
        return round(total)


@dataclass
class PerTicketScoreResult:
    """One per input text. Contains per-ticker scores from the LLM."""
    ticker_scores: list[ScoreResult] = field(default_factory=list)


class ScorerInterface(ABC):
    @abstractmethod
    def score_batch(self, texts: list[str]) -> list[PerTicketScoreResult]:
        """Score a batch of texts. Returns one PerTicketScoreResult per input text."""
        pass


class MockScorer(ScorerInterface):
    def __init__(self, seed: int | None = None):
        self.rng = random.Random(seed)

    def score_batch(self, texts: list[str]) -> list[PerTicketScoreResult]:
        results = []
        for text in texts:
            score = ScoreResult(
                reasoning_score=self.rng.randint(20, 90),
                specificity_score=self.rng.randint(20, 90),
                novelty_score=self.rng.randint(20, 90),
                credibility_score=self.rng.randint(20, 90),
                sentiment=self.rng.choice(["bull", "bear", "neutral"]),
                reasoning_summary="Mock score for testing",
                tickers_mentioned=["MOCK"],
            )
            results.append(PerTicketScoreResult(ticker_scores=[score]))
        return results
