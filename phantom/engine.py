"""Stealth browser engine — Patchright with anti-detection patches.

Uses Patchright (patched Playwright fork) to bypass CDP detection used by
Google, LinkedIn, Cloudflare, and other anti-bot systems. Falls back to
standard Playwright if Patchright is not installed.

When no display is available (headless server), automatically starts a
virtual display (Xvfb) and runs in headed mode — this avoids the
"HeadlessChrome" User-Agent leak that triggers bot detection.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

try:
    from patchright.async_api import Browser, BrowserContext, Playwright
    _USING_PATCHRIGHT = True
except ImportError:
    from playwright.async_api import Browser, BrowserContext, Playwright
    _USING_PATCHRIGHT = False

logger = logging.getLogger("phantom")

# Prototype-chain webdriver removal (beats the "new" detection method)
WEBDRIVER_SPOOF = """
(() => {
    const proto = Object.getPrototypeOf(navigator);
    const desc = Object.getOwnPropertyDescriptor(proto, 'webdriver');
    if (desc) {
        Object.defineProperty(proto, 'webdriver', {
            get: () => false, configurable: true, enumerable: true,
        });
    } else {
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined, configurable: true,
        });
    }
})();
"""

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Human-like timing constants
TYPE_DELAY_MS = 80
CLICK_BASE_DELAY_MS = 200
CLICK_JITTER_MS = 50

# Virtual display singleton
_virtual_display = None


def _find_chromium() -> str | None:
    """Find a Chromium binary from Playwright/Patchright cache."""
    cache = Path.home() / ".cache" / "ms-playwright"
    if not cache.exists():
        return None
    for chrome in sorted(cache.glob("chromium-*/chrome-linux64/chrome"), reverse=True):
        if chrome.exists():
            return str(chrome)
    for chrome in sorted(cache.glob("chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"), reverse=True):
        if chrome.exists():
            return str(chrome)
    return None


def _has_display() -> bool:
    """Check if a display (real or Xvfb) is available."""
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _ensure_virtual_display() -> None:
    """Start a virtual display (Xvfb) if no display is available.

    This allows running in headed mode on headless servers, which avoids
    the "HeadlessChrome" UA string that triggers bot detection.
    """
    global _virtual_display
    if _has_display() or _virtual_display is not None:
        return
    try:
        from pyvirtualdisplay import Display
        _virtual_display = Display(visible=False, size=(1366, 768))
        _virtual_display.start()
        logger.info("Virtual display started (Xvfb) — headed mode enabled")
    except ImportError:
        logger.debug("pyvirtualdisplay not installed — using headless mode")
    except Exception as e:
        logger.warning("Failed to start virtual display: %s — using headless mode", e)


def ensure_chromium() -> None:
    """Install Chromium via Patchright/Playwright if not found."""
    if _find_chromium():
        return
    module = "patchright" if _USING_PATCHRIGHT else "playwright"
    logger.info("Chromium not found — installing via %s...", module)
    try:
        subprocess.run(
            [sys.executable, "-m", module, "install", "chromium"],
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Chromium installed successfully")
    except subprocess.CalledProcessError as e:
        logger.error("Failed to install Chromium: %s", e.stderr)
        raise RuntimeError(
            f"Could not install Chromium. Run manually: python -m {module} install chromium"
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

    Anti-detection stack (when using Patchright):
    - CDP leak patching (Runtime.Enable isolated, no console API)
    - navigator.webdriver prototype-chain spoofing
    - --disable-blink-features=AutomationControlled
    - Realistic fingerprint (UA, locale, timezone, viewport)
    - Headed mode via Xvfb on headless servers (avoids HeadlessChrome UA)

    Falls back to playwright-stealth patches if using standard Playwright.
    """
    # Apply playwright-stealth only if NOT using patchright (patchright handles CDP natively)
    if not _USING_PATCHRIGHT:
        try:
            from playwright_stealth import Stealth
            stealth = Stealth()
            stealth.hook_playwright_context(pw)
        except ImportError:
            logger.warning("Neither patchright nor playwright-stealth available — limited stealth")

    # Always prefer headed mode (better stealth) — start virtual display if needed.
    # Even if --headless was passed, we use Xvfb + headed to avoid HeadlessChrome UA.
    _ensure_virtual_display()
    if _has_display():
        headless = False
        logger.debug("Running in headed mode via virtual display (best stealth)")
    elif headless is None or headless is True:
        headless = True
        logger.debug("Running in headless mode (no virtual display available)")

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
