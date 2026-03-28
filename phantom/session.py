"""Session persistence — save/load browser cookies by name."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from playwright.async_api import BrowserContext

logger = logging.getLogger("phantom")

SESSIONS_DIR = Path.home() / ".phantom" / "sessions"


def load_session(name: str) -> str | None:
    """Load a saved session state file path, or None if not found."""
    path = SESSIONS_DIR / f"{name}.json"
    if path.exists():
        logger.info("Restoring session '%s'", name)
        return str(path)
    return None


async def save_session(context: BrowserContext, name: str) -> None:
    """Persist cookies and storage state for reuse."""
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"{name}.json"
    try:
        state = await context.storage_state()
        path.write_text(json.dumps(state, indent=2))
        logger.info("Session '%s' saved to %s", name, path)
    except Exception as e:
        logger.warning("Failed to save session: %s", e)
