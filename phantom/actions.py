"""Human-like browser interaction helpers."""
from __future__ import annotations

try:
    from patchright.async_api import Page
except ImportError:
    from playwright.async_api import Page

from .engine import CLICK_BASE_DELAY_MS, CLICK_JITTER_MS, TYPE_DELAY_MS


async def human_click(page: Page, selector: str, index: int = 0) -> dict:
    """Click an element using bounding-box coordinates with variable timing."""
    try:
        el = page.locator(selector).nth(0)
        await el.wait_for(state="visible", timeout=10000)
        box = await el.bounding_box()
        if box:
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            await page.mouse.click(x, y)
        else:
            await el.click()
        delay = CLICK_BASE_DELAY_MS + (index % 3) * CLICK_JITTER_MS
        await page.wait_for_timeout(delay)
        return {"ok": True, "action": "click", "selector": selector}
    except Exception as e:
        return {"ok": False, "action": "click", "selector": selector, "error": str(e)}


async def human_fill(page: Page, selector: str, value: str) -> dict:
    """Fill an input field (instant, like paste)."""
    try:
        el = page.locator(selector).nth(0)
        await el.wait_for(state="visible", timeout=10000)
        await el.fill(value)
        await page.wait_for_timeout(CLICK_BASE_DELAY_MS)
        return {"ok": True, "action": "fill", "selector": selector}
    except Exception as e:
        return {"ok": False, "action": "fill", "selector": selector, "error": str(e)}


async def human_type(page: Page, selector: str, value: str) -> dict:
    """Type into an input with human-like per-character delay."""
    try:
        el = page.locator(selector).nth(0)
        await el.wait_for(state="visible", timeout=10000)
        await el.click()
        await page.wait_for_timeout(200)
        await el.type(value, delay=TYPE_DELAY_MS)
        await page.wait_for_timeout(300)
        return {"ok": True, "action": "type", "selector": selector}
    except Exception as e:
        return {"ok": False, "action": "type", "selector": selector, "error": str(e)}


async def human_wait(page: Page, selector: str, timeout_ms: int = 10000) -> dict:
    """Wait for an element to appear."""
    try:
        el = page.locator(selector).nth(0)
        await el.wait_for(state="visible", timeout=timeout_ms)
        return {"ok": True, "action": "wait", "selector": selector}
    except Exception as e:
        return {"ok": False, "action": "wait", "selector": selector, "error": str(e)}
