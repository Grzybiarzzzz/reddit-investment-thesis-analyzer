"""API key authentication with rate limiting."""
import secrets
import time
from collections import defaultdict

AUTH_MAX_ATTEMPTS = 5
AUTH_LOCKOUT_SECONDS = 900  # 15 minutes

# Track failed attempts: ip -> list of timestamps
_failed_attempts: dict[str, list[float]] = defaultdict(list)


def generate_api_key() -> str:
    """Generate a 64-char hex API key."""
    return secrets.token_hex(32)


def check_api_key(provided: str, configured: str) -> bool:
    """Check if the provided API key matches. Empty configured key disables auth."""
    if not configured:
        return True
    return secrets.compare_digest(provided, configured)


def record_failed_attempt(ip: str) -> None:
    """Record a failed auth attempt for an IP."""
    now = time.time()
    _failed_attempts[ip].append(now)
    # Keep only attempts within lockout window
    cutoff = now - AUTH_LOCKOUT_SECONDS
    _failed_attempts[ip] = [t for t in _failed_attempts[ip] if t > cutoff]


def is_locked_out(ip: str) -> bool:
    """Check if an IP is locked out due to too many failed attempts."""
    now = time.time()
    cutoff = now - AUTH_LOCKOUT_SECONDS
    recent = [t for t in _failed_attempts.get(ip, []) if t > cutoff]
    return len(recent) >= AUTH_MAX_ATTEMPTS


def clear_attempts(ip: str) -> None:
    """Clear failed attempts for an IP (on successful auth)."""
    _failed_attempts.pop(ip, None)
