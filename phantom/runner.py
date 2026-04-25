"""Multi-step plan runner — execute a sequence of browser actions in one session."""
from __future__ import annotations

import json
import logging
from pathlib import Path

try:
    from patchright.async_api import Page
except ImportError:
    from playwright.async_api import Page

from .actions import (
    human_click,
    human_fill,
    human_set_input_files,
    human_type,
    human_wait,
)

logger = logging.getLogger("phantom")


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------
async def _exec_goto(page: Page, params: dict) -> dict:
    """Navigate to a URL."""
    url = params.get("url", "")
    timeout = params.get("timeout_ms", 30000)
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await page.wait_for_timeout(2000)
        return {
            "ok": True, "action": "goto", "url": page.url,
            "status": resp.status if resp else None,
        }
    except Exception as e:
        return {"ok": False, "action": "goto", "url": url, "error": str(e)}


async def _exec_screenshot(page: Page, params: dict) -> dict:
    """Take a screenshot."""
    path = params.get("path", "/tmp/phantom_screenshot.png")
    try:
        await page.screenshot(path=path, full_page=params.get("full_page", False))
        return {"ok": True, "action": "screenshot", "path": path}
    except Exception as e:
        return {"ok": False, "action": "screenshot", "error": str(e)}


async def _exec_get_text(page: Page, params: dict) -> dict:
    """Get text content from a selector."""
    selector = params.get("selector", "body")
    try:
        text = await page.inner_text(selector)
        if len(text) > 50000:
            text = text[:50000] + "\n... [truncated]"
        return {"ok": True, "action": "get_text", "text": text}
    except Exception as e:
        return {"ok": False, "action": "get_text", "error": str(e)}


async def _exec_evaluate(page: Page, params: dict) -> dict:
    """Execute JavaScript in page context."""
    js = params.get("js", "")
    try:
        result = await page.evaluate(js)
        return {"ok": True, "action": "evaluate", "result": result}
    except Exception as e:
        return {"ok": False, "action": "evaluate", "error": str(e)}


async def _exec_wait_for(page: Page, params: dict) -> dict:
    """Wait for a selector to appear."""
    return await human_wait(page, params["selector"], params.get("timeout_ms", 10000))


async def _exec_click(page: Page, params: dict, step_index: int) -> dict:
    """Click an element."""
    return await human_click(page, params["selector"], index=step_index)


async def _exec_fill(page: Page, params: dict) -> dict:
    """Fill an input field."""
    return await human_fill(page, params["selector"], params["value"])


async def _exec_type(page: Page, params: dict) -> dict:
    """Type into an input."""
    return await human_type(page, params["selector"], params["value"])


async def _exec_set_input_files(page: Page, params: dict) -> dict:
    """Attach files to an `<input type=file>`.

    `files` may be a string path or a list of paths. `path` is also
    accepted as an alias for single-file ergonomics.
    """
    selector = params["selector"]
    files = params.get("files") or params.get("path")
    if files is None:
        return {"ok": False, "action": "set_input_files",
                "error": "Missing 'files' (or 'path') param"}
    return await human_set_input_files(
        page, selector, files, timeout_ms=params.get("timeout_ms", 10000),
    )


async def _exec_select_option(page: Page, params: dict) -> dict:
    """Select a dropdown option."""
    selector = params["selector"]
    try:
        el = page.locator(selector).nth(0)
        if "value" in params:
            await el.select_option(value=params["value"])
        elif "label" in params:
            await el.select_option(label=params["label"])
        elif "index" in params:
            await el.select_option(index=params["index"])
        await page.wait_for_timeout(200)
        return {"ok": True, "action": "select_option", "selector": selector}
    except Exception as e:
        return {"ok": False, "action": "select_option", "error": str(e)}


async def _exec_press_key(page: Page, params: dict) -> dict:
    """Press a keyboard key."""
    key = params["key"]
    selector = params.get("selector")
    try:
        if selector:
            await page.locator(selector).nth(0).press(key)
        else:
            await page.keyboard.press(key)
        return {"ok": True, "action": "press_key", "key": key}
    except Exception as e:
        return {"ok": False, "action": "press_key", "error": str(e)}


async def _exec_wait_for_spa_idle(page: Page, params: dict) -> dict:
    """Wait for SPA to settle (network idle)."""
    timeout = params.get("timeout_ms", 5000)
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
        return {"ok": True, "action": "wait_for_spa_idle"}
    except Exception as e:
        return {"ok": False, "action": "wait_for_spa_idle", "error": str(e)}


async def _exec_assert_visible(page: Page, params: dict) -> dict:
    """Assert an element is visible."""
    selector = params["selector"]
    try:
        el = page.locator(selector).nth(0)
        visible = await el.is_visible()
        count = await page.locator(selector).count()
        return {"ok": visible, "action": "assert_visible", "visible": visible, "count": count,
                "error": None if visible else f"Element not visible: {selector}"}
    except Exception as e:
        return {"ok": False, "action": "assert_visible", "error": str(e)}


async def _exec_assert_text_contains(page: Page, params: dict) -> dict:
    """Assert element text contains expected string."""
    selector = params["selector"]
    expected = params["expected"]
    try:
        text = await page.locator(selector).nth(0).inner_text()
        found = expected in text
        return {"ok": found, "action": "assert_text_contains",
                "expected": expected, "actual": text[:500],
                "error": None if found else f"Expected '{expected}' not found in text"}
    except Exception as e:
        return {"ok": False, "action": "assert_text_contains", "error": str(e)}


async def _exec_assert_url_contains(page: Page, params: dict) -> dict:
    """Assert current URL contains pattern."""
    pattern = params["pattern"]
    url = page.url
    found = pattern in url
    return {"ok": found, "action": "assert_url_contains",
            "pattern": pattern, "url": url,
            "error": None if found else f"URL '{url}' does not contain '{pattern}'"}


async def _exec_get_element_count(page: Page, params: dict) -> dict:
    """Count matching elements."""
    selector = params["selector"]
    try:
        count = await page.locator(selector).count()
        return {"ok": True, "action": "get_element_count", "selector": selector, "count": count}
    except Exception as e:
        return {"ok": False, "action": "get_element_count", "error": str(e)}


async def _exec_get_inner_html(page: Page, params: dict) -> dict:
    """Get inner HTML of an element."""
    selector = params["selector"]
    max_length = params.get("max_length", 10000)
    try:
        html = await page.locator(selector).nth(0).inner_html()
        if len(html) > max_length:
            html = html[:max_length] + "... [truncated]"
        return {"ok": True, "action": "get_inner_html", "html": html}
    except Exception as e:
        return {"ok": False, "action": "get_inner_html", "error": str(e)}


async def _exec_get_table_data(page: Page, params: dict) -> dict:
    """Extract table data as JSON."""
    selector = params.get("table_selector", "table")
    max_rows = params.get("max_rows", 50)
    try:
        data = await page.evaluate("""
            ({selector, maxRows}) => {
                const table = document.querySelector(selector);
                if (!table) return {headers: [], rows: [], error: 'Table not found'};
                const headers = Array.from(table.querySelectorAll('thead th, thead td'))
                    .map(th => th.textContent.trim());
                const rows = Array.from(table.querySelectorAll('tbody tr'))
                    .slice(0, maxRows)
                    .map(tr => Array.from(tr.querySelectorAll('td'))
                        .map(td => td.textContent.trim()));
                return {headers, rows, rowCount: table.querySelectorAll('tbody tr').length};
            }
        """, {"selector": selector, "maxRows": max_rows})
        return {"ok": True, "action": "get_table_data", **data}
    except Exception as e:
        return {"ok": False, "action": "get_table_data", "error": str(e)}


async def _exec_login(page: Page, params: dict) -> dict:
    """Atomic login sequence."""
    try:
        url = params.get("url", "")
        if url:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

        username_field = params.get("username_field", "input[type=email]")
        password_field = params.get("password_field", "input[type=password]")
        submit_selector = params.get("submit_selector", "button[type=submit]")

        await human_fill(page, username_field, params["username"])
        await human_fill(page, password_field, params["password"])
        await human_click(page, submit_selector)

        wait_after = params.get("wait_after_ms", 3000)
        await page.wait_for_timeout(wait_after)

        return {"ok": True, "action": "login", "url": page.url}
    except Exception as e:
        return {"ok": False, "action": "login", "error": str(e)}


# ---------------------------------------------------------------------------
# Step executor
# ---------------------------------------------------------------------------
async def execute_step(page: Page, step: dict, step_index: int) -> dict:
    """Execute a single plan step and return the result."""
    action = step.get("action", "")
    params = step.get("params", {})
    description = step.get("description", action)

    logger.info("Step %d: %s", step_index + 1, description)

    dispatch = {
        "goto": lambda: _exec_goto(page, params),
        "click": lambda: _exec_click(page, params, step_index),
        "fill": lambda: _exec_fill(page, params),
        "type_text": lambda: _exec_type(page, params),
        "type": lambda: _exec_type(page, params),
        "wait_for": lambda: _exec_wait_for(page, params),
        "wait_for_spa_idle": lambda: _exec_wait_for_spa_idle(page, params),
        "screenshot": lambda: _exec_screenshot(page, params),
        "get_text": lambda: _exec_get_text(page, params),
        "evaluate": lambda: _exec_evaluate(page, params),
        "select_option": lambda: _exec_select_option(page, params),
        "set_input_files": lambda: _exec_set_input_files(page, params),
        "press_key": lambda: _exec_press_key(page, params),
        "assert_visible": lambda: _exec_assert_visible(page, params),
        "assert_text_contains": lambda: _exec_assert_text_contains(page, params),
        "assert_url_contains": lambda: _exec_assert_url_contains(page, params),
        "get_element_count": lambda: _exec_get_element_count(page, params),
        "get_inner_html": lambda: _exec_get_inner_html(page, params),
        "get_table_data": lambda: _exec_get_table_data(page, params),
        "login": lambda: _exec_login(page, params),
    }

    handler = dispatch.get(action)
    if not handler:
        return {"ok": False, "action": action, "error": f"Unknown action: {action}"}

    try:
        result = await handler()
    except Exception as e:
        result = {"ok": False, "action": action, "error": str(e)}

    result["description"] = description
    return result


# ---------------------------------------------------------------------------
# Plan runner
# ---------------------------------------------------------------------------
async def run_plan(page: Page, plan: list[dict]) -> dict:
    """Execute a full plan (list of steps) against a page.

    Returns:
        {
            "ok": bool,
            "steps": [{...result for each step...}],
            "aborted_at": int | null,
            "url": str
        }
    """
    results = []
    aborted_at = None

    for i, step in enumerate(plan):
        result = await execute_step(page, step, i)
        results.append(result)

        if not result.get("ok") and step.get("critical", False):
            logger.error("Critical step %d failed — aborting plan", i + 1)
            aborted_at = i + 1
            break

    try:
        final_url = page.url
    except Exception:
        final_url = "unknown"

    all_ok = all(r.get("ok") for r in results)

    return {
        "ok": all_ok,
        "steps": results,
        "aborted_at": aborted_at,
        "url": final_url,
        "steps_total": len(plan),
        "steps_executed": len(results),
        "steps_passed": sum(1 for r in results if r.get("ok")),
    }


def load_plan(path: str) -> list[dict]:
    """Load a plan from a JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Plan file not found: {path}")
    return json.loads(p.read_text())
