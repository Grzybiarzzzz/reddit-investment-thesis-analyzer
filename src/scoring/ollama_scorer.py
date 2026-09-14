# src/scoring/ollama_scorer.py
import json
import logging
import re
import time
import requests
from src.scoring.scorer_interface import ScorerInterface, ScoreResult, PerTicketScoreResult

logger = logging.getLogger(__name__)

OLLAMA_SYSTEM_PROMPT = """Analyze Reddit posts/comments about stocks. Identify stock tickers with investment theses and score each ticker INDEPENDENTLY.

Score how strong the argument is for THAT SPECIFIC ticker, not the overall post quality. Only include tickers where the text makes a meaningful claim (buy/sell/hold thesis, price target, earnings analysis). Skip tickers merely name-dropped without analysis.

Output format: {"tickers": [{"ticker": "NVDA", "sentiment": "bull", "reasoning_score": 75, "specificity_score": 60, "novelty_score": 40, "credibility_score": 55, "reasoning_summary": "short summary"}]}

Scoring (each 0-100):
- reasoning_score: How well-argued is the thesis? (logic, evidence, cause-effect)
- specificity_score: How specific? (numbers, dates, catalysts vs vague hype)
- novelty_score: Original insight or echo-chamber repetition?
- credibility_score: Author knowledgeable? (expertise, balanced analysis)

Sentiment: bull/bear/neutral. No thesis: {"tickers": []}
Use ONLY standard US uppercase ticker symbols (AAPL not Apple, NVDA not Nvidia). Keep reasoning_summary under 20 words."""

# JSON schema to force structured output from Ollama
OUTPUT_SCHEMA = {
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
}


class OllamaScorer(ScorerInterface):
    def __init__(self, model: str, base_url: str):
        self.model = model
        self.base_url = base_url.rstrip("/")

    def _call_ollama(self, numbered_texts: str) -> tuple[list[dict], str]:
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": OLLAMA_SYSTEM_PROMPT},
                    {"role": "user", "content": "Score these texts:\n" + numbered_texts},
                ],
                "stream": False,
                "format": OUTPUT_SCHEMA,
                "options": {
                    "num_ctx": 4096,
                    "num_predict": 512,
                },
                "think": False,
            },
            timeout=300,
        )
        response.raise_for_status()
        raw_content = response.json()["message"]["content"]

        # Strip markdown code fences if present
        clean = re.sub(r'^```(?:json)?\s*', '', raw_content.strip())
        clean = re.sub(r'\s*```$', '', clean.strip())

        try:
            parsed = json.loads(clean)
            if isinstance(parsed, dict):
                parsed = [parsed]
            elif not isinstance(parsed, list):
                parsed = []
        except json.JSONDecodeError:
            parsed = []

        return parsed, raw_content

    def score_batch(self, texts: list[str], max_retries: int = 3) -> list[PerTicketScoreResult]:
        numbered_texts = "\n".join(
            f"[{i+1}] {text}" for i, text in enumerate(texts)
        )
        raw_content = ""

        for attempt in range(1, max_retries + 1):
            try:
                parsed, raw_content = self._call_ollama(numbered_texts)
                if parsed:
                    break
                logger.warning("Ollama returned no parseable JSON (attempt %d/%d): %.500s", attempt, max_retries, raw_content)
            except Exception as e:
                logger.warning("Ollama scoring failed (attempt %d/%d): %s", attempt, max_retries, e)
                parsed = []

            if attempt < max_retries:
                time.sleep(2)
        else:
            logger.error("Ollama scoring failed after %d attempts", max_retries)
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
