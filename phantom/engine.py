"""Stealth browser engine — Playwright with anti-detection patches."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Playwright

try:
    from playwright_stealth import Stealth
except ImportError:
    Stealth = None

logger = logging.getLogger("phantom")

WEBDRIVER_SPOOF = 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Human-like timing constants
TYPE_DELAY_MS = 80
CLICK_BASE_DELAY_MS = 200
CLICK_JITTER_MS = 50


def _find_chromium() -> str | None:
    """Find a Chromium binary from Playwright's cache."""
    cache = Path.home() / ".cache" / "ms-playwright"
    if not cache.exists():
        return None
    for chrome in sorted(cache.glob("chromium-*/chrome-linux64/chrome"), reverse=True):
        if chrome.exists():
            return str(chrome)
    # macOS path
    for chrome in sorted(cache.glob("chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"), reverse=True):
        if chrome.exists():
            return str(chrome)
    return None


def _has_display() -> bool:
    """Check if a display (real or Xvfb) is available."""
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def ensure_chromium() -> None:
    """Install Chromium via Playwright if not found."""
    if _find_chromium():
        return
    logger.info("Chromium not found — installing via Playwright...")
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Chromium installed successfully")
    except subprocess.CalledProcessError as e:
        logger.error("Failed to install Chromium: %s", e.stderr)
        raise RuntimeError(
            "Could not install Chromium. Run manually: python -m playwright install chromium"
        ) from e


async def create_stealth_context(
    pw: Playwright,
    *,
    locale: str = "en-US",
    timezone: str = "America/New_York",
    viewport: tuple[int, int] = (1366, 768),
    user_agent: str = DEFAULT_USER_AGENT,
    headless: bool | None = None,
    storage_state: str | None = None,
) -> tuple[Browser, BrowserContext]:
    """Launch stealth Chromium and return (browser, context).

    Anti-detection stack:
    - playwright-stealth patches (if installed)
    - navigator.webdriver spoofing
    - --disable-blink-features=AutomationControlled
    - Realistic fingerprint (UA, locale, timezone, viewport)
    - Headed mode via Xvfb when display available
    """
    if Stealth is not None:
        stealth = Stealth()
        stealth.hook_playwright_context(pw)
    else:
        logger.warning("playwright-stealth not installed — running without stealth patches")

    if headless is None:
        headless = not _has_display()

    chromium_path = _find_chromium()
    launch_kwargs: dict = {
        "headless": headless,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    }
    if chromium_path:
        launch_kwargs["executable_path"] = chromium_path

    browser = await pw.chromium.launch(**launch_kwargs)

    context = await browser.new_context(
        locale=locale,
        timezone_id=timezone,
        viewport={"width": viewport[0], "height": viewport[1]},
        user_agent=user_agent,
        storage_state=storage_state,
    )
    await context.add_init_script(WEBDRIVER_SPOOF)

    return browser, context
