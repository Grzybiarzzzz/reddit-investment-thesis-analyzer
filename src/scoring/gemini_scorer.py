# src/scoring/gemini_scorer.py
import json
import logging
import re
import time
from google import genai
from google.genai import types
from src.scoring.scorer_interface import ScorerInterface, ScoreResult, PerTicketScoreResult

logger = logging.getLogger(__name__)

SCORING_PROMPT = """Analyze Reddit posts/comments about stocks. For each text, identify every stock ticker discussed and score the investment thesis FOR EACH TICKER SEPARATELY.

IMPORTANT: Score how strong the argument is for THAT SPECIFIC ticker, not the overall post quality. A high-quality post about NVDA that casually mentions AAPL should give NVDA a high score but AAPL a low score. Only include tickers where the text makes a meaningful claim (buy/sell/hold thesis, price target, earnings analysis, etc.). Skip tickers that are merely name-dropped or listed without analysis.

Return a JSON array, one object per TEXT (not per ticker). Each object has a "tickers" array:
[{"tickers": [{"ticker": "NVDA", "sentiment": "bull", "reasoning_score": 75, "specificity_score": 60, "novelty_score": 40, "credibility_score": 55, "reasoning_summary": "one sentence about THIS ticker's thesis"}]}]

Scoring dimensions (each 0-100):
- reasoning_score: How well-argued is the thesis for THIS ticker? (logic, evidence, cause-effect chains)
- specificity_score: How specific are the claims? (concrete numbers, dates, price targets, catalysts vs vague hype)
- novelty_score: Is this an original insight or echo-chamber repetition? (contrarian views, unique data, non-obvious connections score higher)
- credibility_score: Does the author seem knowledgeable? (domain expertise, acknowledged risks, balanced analysis)

Sentiment: bull/bear/neutral. If a text has no meaningful investment thesis for any ticker, return: {"tickers": []}

Use ONLY standard US uppercase ticker symbols (e.g. AAPL not Apple, NVDA not Nvidia, GOOGL not Google, SBLK not "Star Bulk"). If unsure of the symbol, omit the ticker. Do not return non-US exchange tickers (no .L, .DE, etc.).

Keep reasoning_summary under 20 words.

Score these texts:
"""

OUTPUT_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "tickers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "sentiment": {"type": "string", "enum": ["bull", "bear", "neutral"]},
                        "reasoning_score": {"type": "integer"},
                        "specificity_score": {"type": "integer"},
                        "novelty_score": {"type": "integer"},
                        "credibility_score": {"type": "integer"},
                        "reasoning_summary": {"type": "string"},
                    },
                    "required": ["ticker", "sentiment", "reasoning_score",
                                 "specificity_score", "novelty_score",
                                 "credibility_score", "reasoning_summary"],
                },
            },
        },
        "required": ["tickers"],
    },
}


class GeminiScorer(ScorerInterface):
    def __init__(self, model: str, api_key: str = "", project: str = "", location: str = "",
                 fallback_model: str = ""):
        if project:
            # Vertex AI mode — uses GCloud credentials, no API key needed
            self.client = genai.Client(
                vertexai=True,
                project=project,
                location=location or "us-central1",
            )
        else:
            # AI Studio mode — uses API key
            self.client = genai.Client(api_key=api_key)
        self.model = model
        self.fallback_model = fallback_model

    def _call_model(self, model: str, prompt: str) -> list:
        """Call a Gemini model and return parsed JSON list, or raise on failure."""
        response = self.client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=OUTPUT_SCHEMA,
            ),
        )
        raw_content = response.text

        # Strip markdown code fences if present
        clean = re.sub(r'^```(?:json)?\s*', '', raw_content.strip())
        clean = re.sub(r'\s*```$', '', clean.strip())

        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            parsed = [parsed]
        elif not isinstance(parsed, list):
            parsed = []

        if not parsed:
            raise ValueError(f"Empty response: {raw_content[:500]}")
        return parsed

    def score_batch(self, texts: list[str], max_retries: int = 3) -> list[PerTicketScoreResult]:
        numbered_texts = "\n".join(
            f"[{i+1}] {text}" for i, text in enumerate(texts)
        )
        prompt = SCORING_PROMPT + numbered_texts

        for attempt in range(1, max_retries + 1):
            try:
                parsed = self._call_model(self.model, prompt)
                break
            except Exception as e:
                logger.warning("Gemini scoring failed with %s (attempt %d/%d): %s",
                               self.model, attempt, max_retries, e)
                parsed = []

            if attempt < max_retries:
                time.sleep(2)
        else:
            # Primary model exhausted retries — try fallback once
            if self.fallback_model and self.fallback_model != self.model:
                logger.warning("Primary model %s failed after %d attempts, falling back to %s",
                               self.model, max_retries, self.fallback_model)
                try:
                    parsed = self._call_model(self.fallback_model, prompt)
                except Exception as e:
                    logger.error("Fallback model %s also failed: %s", self.fallback_model, e)
                    return []
            else:
                logger.error("Gemini scoring failed after %d attempts", max_retries)
                return []

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
