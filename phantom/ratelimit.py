"""Per-domain rate limiting — prevents hammering a single site."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger("phantom")

RATE_FILE = Path.home() / ".phantom" / "rate_limits.json"
DEFAULT_MIN_DELAY_S = 2.0


def _get_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return parsed.netloc or parsed.path


def _load_state() -> dict[str, float]:
    """Load last-request timestamps per domain."""
    if RATE_FILE.exists():
        try:
            return json.loads(RATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_state(state: dict[str, float]) -> None:
    """Persist last-request timestamps."""
    RATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Prune entries older than 1 hour to keep file small
    cutoff = time.time() - 3600
    state = {k: v for k, v in state.items() if v > cutoff}
    RATE_FILE.write_text(json.dumps(state))


def enforce_rate_limit(url: str, min_delay_s: float = DEFAULT_MIN_DELAY_S) -> float:
    """Enforce per-domain rate limit. Returns seconds waited (0 if no wait needed).

    If min_delay_s is 0, rate limiting is disabled.
    """
    if min_delay_s <= 0:
        return 0.0

    domain = _get_domain(url)
    state = _load_state()
    last_request = state.get(domain, 0.0)
    elapsed = time.time() - last_request
    waited = 0.0

    if elapsed < min_delay_s:
        wait_time = min_delay_s - elapsed
        logger.info(
            "Rate limit: waiting %.1fs before requesting %s",
            wait_time, domain,
        )
        time.sleep(wait_time)
        waited = wait_time

    # Record this request
    state[domain] = time.time()
    _save_state(state)

    return waited
