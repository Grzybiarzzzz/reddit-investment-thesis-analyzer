# src/scoring/anthropic_scorer.py
import json
import logging
import anthropic
from src.scoring.scorer_interface import ScorerInterface, ScoreResult, PerTicketScoreResult

logger = logging.getLogger(__name__)


SCORING_PROMPT = """Analyze Reddit posts/comments about stocks. For each text, identify every stock ticker discussed and score the investment thesis FOR EACH TICKER SEPARATELY.

IMPORTANT: Score how strong the argument is for THAT SPECIFIC ticker, not the overall post quality. A high-quality post about NVDA that casually mentions AAPL should give NVDA a high score but AAPL a low score.

Only include tickers where the text makes a meaningful claim (buy/sell/hold thesis, price target, earnings analysis, etc.). Skip tickers that are merely name-dropped or listed without analysis.

Return ONLY a JSON array (no markdown), one object per TEXT (not per ticker). Each object has a "tickers" array with per-ticker scores:

{"tickers": [{"ticker": "AAPL", "sentiment": "bull|bear|neutral", "reasoning_score": 0-100, "specificity_score": 0-100, "novelty_score": 0-100, "credibility_score": 0-100, "reasoning_summary": "one sentence about THIS ticker's thesis"}]}

Scoring guide:
- reasoning_score: How well-argued is the thesis for THIS ticker? (logic, evidence, cause-effect)
- specificity_score: How specific are the claims about THIS ticker? (numbers, dates, catalysts vs vague hype)
- novelty_score: Is this an original insight about THIS ticker or echo-chamber repetition?
- credibility_score: Does the author seem knowledgeable about THIS ticker? (domain expertise signals)

Use ONLY standard US uppercase ticker symbols (e.g. AAPL not Apple, NVDA not Nvidia, GOOGL not Google, SBLK not "Star Bulk"). If unsure of the symbol, omit the ticker. Do not return non-US exchange tickers (no .L, .DE, etc.).

If a text has no meaningful investment thesis for any ticker, return: {"tickers": []}

Texts:
"""


class AnthropicScorer(ScorerInterface):
    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def score_batch(self, texts: list[str]) -> list[PerTicketScoreResult]:
        try:
            numbered_texts = "\n".join(
                f"[{i+1}] {text}" for i, text in enumerate(texts)
            )
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": SCORING_PROMPT + numbered_texts}
                ],
            )
            raw_json = response.content[0].text
            parsed = json.loads(raw_json)
            if isinstance(parsed, dict):
                parsed = [parsed]

            results = []
            for item in parsed:
                ticker_scores = []
                for t in item.get("tickers", []):
                    ticker_scores.append(ScoreResult(
                        reasoning_score=t.get("reasoning_score", 0),
                        specificity_score=t.get("specificity_score", 0),
                        novelty_score=t.get("novelty_score", 0),
                        credibility_score=t.get("credibility_score", 0),
                        sentiment=t.get("sentiment", "neutral"),
                        reasoning_summary=t.get("reasoning_summary", ""),
                        tickers_mentioned=[t.get("ticker", "")],
                    ))
                results.append(PerTicketScoreResult(ticker_scores=ticker_scores))
            return results
        except Exception as e:
            logger.error("Anthropic scoring failed: %s", e)
            return []
