"""Settings API route."""
from fastapi import APIRouter, Request
import config.settings as settings

router = APIRouter()

# Session overrides (not persisted to disk)
_overrides: dict = {}


def _get_value(attr: str):
    """Get a setting value, with session override taking priority."""
    if attr in _overrides:
        return _overrides[attr]
    return getattr(settings, attr, None)


@router.get("/api/settings")
async def get_settings():
    return {
        "scoring": {
            "backend": _get_value("SCORING_BACKEND"),
            "model": _get_value("SCORING_MODEL"),
            "ollama_model": _get_value("OLLAMA_MODEL"),
            "gemini_model": _get_value("GEMINI_MODEL"),
            "batch_size": _get_value("LLM_BATCH_SIZE"),
            "rate_limit_delay": _get_value("LLM_RATE_LIMIT_DELAY"),
        },
        "discovery": {
            "min_mentions": _get_value("MIN_MENTIONS"),
            "min_avg_score": _get_value("MIN_AVG_SCORE"),
            "lookback_days": _get_value("MENTION_LOOKBACK_DAYS"),
            "cooldown_days": _get_value("RETRACK_COOLDOWN_DAYS"),
        },
        "scraping": {
            "subreddits": _get_value("SUBREDDITS"),
            "sort_modes": _get_value("SORT_MODES"),
            "posts_per_sort": _get_value("POSTS_PER_SORT"),
            "min_comment_score": _get_value("MIN_COMMENT_SCORE"),
        },
    }


# Mapping from API field names to settings module attributes
_FIELD_MAP = {
    "scoring": {
        "backend": "SCORING_BACKEND",
        "model": "SCORING_MODEL",
        "ollama_model": "OLLAMA_MODEL",
        "gemini_model": "GEMINI_MODEL",
        "batch_size": "LLM_BATCH_SIZE",
        "rate_limit_delay": "LLM_RATE_LIMIT_DELAY",
    },
    "discovery": {
        "min_mentions": "MIN_MENTIONS",
        "min_avg_score": "MIN_AVG_SCORE",
        "lookback_days": "MENTION_LOOKBACK_DAYS",
        "cooldown_days": "RETRACK_COOLDOWN_DAYS",
    },
    "scraping": {
        "subreddits": "SUBREDDITS",
        "sort_modes": "SORT_MODES",
        "posts_per_sort": "POSTS_PER_SORT",
        "min_comment_score": "MIN_COMMENT_SCORE",
    },
}


@router.put("/api/settings")
async def update_settings(request: Request):
    body = await request.json()
    updated = []
    for section, fields in body.items():
        if section not in _FIELD_MAP:
            continue
        if not isinstance(fields, dict):
            continue
        for field, value in fields.items():
            if field in _FIELD_MAP[section]:
                attr = _FIELD_MAP[section][field]
                _overrides[attr] = value
                updated.append(f"{section}.{field}")
    return {"updated": updated, "note": "Changes are session-only. Edit .env for permanent changes."}
