"""Phantom CLI — stealth browser for humans and AI agents."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys

from playwright.async_api import async_playwright

from .actions import human_click, human_fill, human_type, human_wait
from .engine import create_stealth_context, ensure_chromium
from .session import load_session, save_session

logger = logging.getLogger("phantom")


# ---------------------------------------------------------------------------
# Action parser (preserves CLI flag ordering)
# ---------------------------------------------------------------------------
class OrderedAction(argparse.Action):
    """Custom argparse action that preserves flag ordering."""

    def __call__(self, parser, namespace, values, option_string=None):
        if not hasattr(namespace, "_ordered_actions"):
            namespace._ordered_actions = []

        action_type = self.dest
        if action_type in ("fill", "type_text"):
            if "=" in values:
                selector, value = values.split("=", 1)
                namespace._ordered_actions.append(
                    {"action": "fill" if action_type == "fill" else "type",
                     "selector": selector, "value": value}
                )
            else:
                print(json.dumps({"ok": False, "error": f"--{action_type} requires selector=value format"}))
                sys.exit(1)
        else:
            namespace._ordered_actions.append({"action": action_type, "selector": values})


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
async def run(args: argparse.Namespace) -> dict:
    """Execute a stealth browse session."""
    ensure_chromium()

    async with async_playwright() as pw:
        storage_state = None
        if args.session:
            storage_state = load_session(args.session)

        browser, context = await create_stealth_context(
            pw,
            locale=args.locale,
            timezone=args.timezone,
            viewport=tuple(args.viewport),
            headless=args.headless if args.headless is not None else None,
            storage_state=storage_state,
        )

        page = await context.new_page()

        # Capture console errors
        console_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # Navigate
        try:
            await page.goto(args.url, wait_until="domcontentloaded", timeout=args.timeout)
            await page.wait_for_timeout(2000)
        except Exception as e:
            await browser.close()
            return {"ok": False, "url": args.url, "error": f"Navigation failed: {e}"}

        # Execute ordered actions
        actions = getattr(args, "_ordered_actions", [])
        action_results = []
        for i, act in enumerate(actions):
            if act["action"] == "click":
                r = await human_click(page, act["selector"], index=i)
            elif act["action"] == "fill":
                r = await human_fill(page, act["selector"], act["value"])
            elif act["action"] == "type":
                r = await human_type(page, act["selector"], act["value"])
            elif act["action"] == "wait":
                r = await human_wait(page, act["selector"])
            else:
                r = {"ok": False, "error": f"Unknown action: {act['action']}"}
            action_results.append(r)
            if not r["ok"]:
                logger.warning("Action failed: %s", r)

        # Capture page state
        try:
            url = page.url
        except Exception:
            url = "unknown"

        try:
            title = await page.title()
        except Exception:
            title = ""

        try:
            text = await page.inner_text("body")
            if len(text) > 50000:
                text = text[:50000] + "\n... [truncated]"
        except Exception as e:
            text = f"[error extracting text: {e}]"

        if args.screenshot:
            try:
                await page.screenshot(path=args.screenshot, full_page=True)
            except Exception as e:
                logger.warning("Screenshot failed: %s", e)

        result = {
            "ok": True,
            "url": url,
            "title": title,
            "text": text,
            "screenshot": args.screenshot,
            "console_errors": console_errors,
        }
        if action_results:
            result["actions"] = action_results

        # Save session
        if args.session:
            await save_session(context, args.session)
            result["session_restored"] = storage_state is not None

        await browser.close()
        return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        prog="phantom",
        description="Phantom — stealth browser CLI that bypasses WAFs and bot detection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""examples:
  phantom https://example.com                          # get page text
  phantom https://example.com --json                   # structured output
  phantom https://example.com --screenshot shot.png    # take screenshot
  phantom https://app.com --session myapp --json       # with session persistence
  phantom https://app.com --fill "input=val" --click "button" --json
""",
    )
    parser.add_argument("url", help="URL to navigate to")
    parser.add_argument("--json", dest="json_output", action="store_true",
                        help="output as structured JSON (recommended for agents)")
    parser.add_argument("--screenshot", metavar="PATH",
                        help="save full-page screenshot to file")
    parser.add_argument("--session", metavar="NAME",
                        help="named session for cookie persistence")
    parser.add_argument("--timeout", type=int, default=30000,
                        help="navigation timeout in ms (default: 30000)")
    parser.add_argument("--headless", action="store_true", default=None,
                        help="force headless mode")
    parser.add_argument("--headed", action="store_true",
                        help="force headed mode (requires display)")
    parser.add_argument("--locale", default="en-US",
                        help="browser locale (default: en-US)")
    parser.add_argument("--timezone", default="America/New_York",
                        help="browser timezone (default: America/New_York)")
    parser.add_argument("--viewport", nargs=2, type=int, default=[1366, 768],
                        metavar=("W", "H"), help="viewport size (default: 1366 768)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="enable debug logging")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {_get_version()}")

    # Interaction actions (order-preserving)
    parser.add_argument("--click", action=OrderedAction, metavar="SELECTOR",
                        help="click an element")
    parser.add_argument("--fill", action=OrderedAction, metavar="SEL=VAL",
                        help="fill input (instant)")
    parser.add_argument("--type", dest="type_text", action=OrderedAction,
                        metavar="SEL=VAL", help="type into input (human-like delay)")
    parser.add_argument("--wait", action=OrderedAction, metavar="SELECTOR",
                        help="wait for element to appear")

    args = parser.parse_args()

    if args.headed:
        args.headless = False

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    result = asyncio.run(run(args))

    if args.json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["ok"]:
            print(result.get("text", ""))
        else:
            print(f"ERROR: {result.get('error', 'unknown')}", file=sys.stderr)
            sys.exit(1)


def _get_version() -> str:
    try:
        from . import __version__
        return __version__
    except ImportError:
        return "0.1.0"


if __name__ == "__main__":
    main()
