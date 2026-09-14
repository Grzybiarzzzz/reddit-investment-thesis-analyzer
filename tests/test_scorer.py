# tests/test_scorer.py
import pytest
from src.scoring.scorer_interface import ScorerInterface, ScoreResult, PerTicketScoreResult, MockScorer


class TestScoreResult:
    def test_overall_score_calculated(self):
        result = ScoreResult(
            reasoning_score=80,
            specificity_score=60,
            novelty_score=40,
            credibility_score=100,
            sentiment="bull",
            reasoning_summary="Good analysis",
            tickers_mentioned=["AAPL"],
        )
        weights = {"reasoning": 0.30, "specificity": 0.25, "novelty": 0.25, "credibility": 0.20}
        overall = result.calculate_overall(weights)
        # 80*0.30 + 60*0.25 + 40*0.25 + 100*0.20 = 24 + 15 + 10 + 20 = 69
        assert overall == 69

    def test_scores_clamped_0_100(self):
        result = ScoreResult(
            reasoning_score=150,
            specificity_score=-10,
            novelty_score=50,
            credibility_score=50,
            sentiment="neutral",
            reasoning_summary="Test",
            tickers_mentioned=[],
        )
        assert result.reasoning_score == 100
        assert result.specificity_score == 0


class TestPerTicketScoreResult:
    def test_empty_tickers(self):
        result = PerTicketScoreResult()
        assert result.ticker_scores == []

    def test_multiple_ticker_scores(self):
        scores = [
            ScoreResult(80, 60, 40, 100, "bull", "Good AAPL analysis", ["AAPL"]),
            ScoreResult(50, 50, 50, 50, "bear", "Weak TSLA thesis", ["TSLA"]),
        ]
        result = PerTicketScoreResult(ticker_scores=scores)
        assert len(result.ticker_scores) == 2
        assert result.ticker_scores[0].tickers_mentioned == ["AAPL"]
        assert result.ticker_scores[1].tickers_mentioned == ["TSLA"]


class TestMockScorer:
    def test_returns_per_ticket_results(self):
        scorer = MockScorer()
        results = scorer.score_batch(["Some text about AAPL earnings being great"])
        assert len(results) == 1
        assert isinstance(results[0], PerTicketScoreResult)
        assert len(results[0].ticker_scores) == 1
        assert isinstance(results[0].ticker_scores[0], ScoreResult)

    def test_scores_in_valid_range(self):
        scorer = MockScorer(seed=42)
        results = scorer.score_batch(["text"] * 5)
        for r in results:
            for s in r.ticker_scores:
                assert 0 <= s.reasoning_score <= 100
                assert 0 <= s.specificity_score <= 100
                assert 0 <= s.novelty_score <= 100
                assert 0 <= s.credibility_score <= 100
                assert s.sentiment in ("bull", "bear", "neutral")

    def test_batch_returns_correct_count(self):
        scorer = MockScorer()
        texts = ["text1", "text2", "text3"]
        results = scorer.score_batch(texts)
        assert len(results) == 3

    def test_deterministic_with_seed(self):
        scorer1 = MockScorer(seed=42)
        scorer2 = MockScorer(seed=42)
        r1 = scorer1.score_batch(["test text"])
        r2 = scorer2.score_batch(["test text"])
        assert r1[0].ticker_scores[0].reasoning_score == r2[0].ticker_scores[0].reasoning_score


class TestScorerInterface:
    def test_cannot_instantiate_base(self):
        with pytest.raises(TypeError):
            ScorerInterface()
