# Phantom

Stealth browser CLI that bypasses WAFs and bot detection. Built on Playwright with anti-detection patches so you can fetch pages that block headless browsers, `curl`, and `wget`.

Works as a CLI tool for humans and outputs structured JSON for AI agents.

## Install

```bash
pip install phantom-browse
```

Chromium is installed automatically on first run. To install it manually:

```bash
python -m playwright install chromium
```

## Usage

```bash
# Get page text
phantom https://example.com

# Structured JSON output (for agents)
phantom https://example.com --json

# Screenshot
phantom https://example.com --screenshot page.png

# Login flow
phantom https://app.com/login \
  --fill "input[name=email]=user@example.com" \
  --fill "input[name=password]=secret" \
  --click "button[type=submit]" \
  --session myapp \
  --json

# Reuse session (skip login next time)
phantom https://app.com/dashboard --session myapp --json
```

## JSON Output

When using `--json`, Phantom returns:

```json
{
  "ok": true,
  "url": "https://example.com",
  "title": "Example Domain",
  "text": "...",
  "screenshot": null,
  "console_errors": []
}
```

On failure:

```json
{
  "ok": false,
  "url": "https://example.com",
  "error": "Navigation failed: net::ERR_NAME_NOT_RESOLVED"
}
```

## Interaction Flags

Actions execute in order, before the final page capture.

```bash
--click SELECTOR        # Click element (coordinate-based, human-like timing)
--fill SEL=VAL          # Fill input field (instant)
--type SEL=VAL          # Type into input (80ms per-character delay)
--wait SELECTOR         # Wait for element to appear
```

Chain them:

```bash
phantom https://app.com \
  --wait "form" \
  --fill "input[name=q]=test" \
  --click "button[type=submit]" \
  --json
```

## Multi-Step Plans

For complex flows (login, navigate, interact, capture), use `--actions` with a JSON plan file:

```bash
phantom --actions plan.json --json
phantom https://app.com --actions plan.json --session myapp --json
```

Plan format — array of steps, each with `action`, `params`, and optional `description`/`critical`:

```json
[
  {"action": "goto", "params": {"url": "https://app.com/login"}, "description": "Open login page"},
  {"action": "fill", "params": {"selector": "input[name=email]", "value": "me@x.com"}},
  {"action": "fill", "params": {"selector": "input[name=password]", "value": "secret"}},
  {"action": "click", "params": {"selector": "button[type=submit]"}, "critical": true},
  {"action": "wait_for", "params": {"selector": ".dashboard"}, "critical": true},
  {"action": "screenshot", "params": {"path": "/tmp/dashboard.png"}},
  {"action": "goto", "params": {"url": "https://app.com/profile"}},
  {"action": "get_text", "params": {"selector": ".profile-info"}}
]
```

If a step marked `critical: true` fails, remaining steps are skipped.

**Supported actions:** `goto`, `click`, `fill`, `type_text`, `wait_for`, `wait_for_spa_idle`, `screenshot`, `get_text`, `evaluate`, `select_option`, `press_key`, `login`, `assert_visible`, `assert_text_contains`, `assert_url_contains`, `get_element_count`, `get_inner_html`, `get_table_data`

Multi-step output:

```json
{
  "ok": true,
  "steps_total": 8,
  "steps_executed": 8,
  "steps_passed": 8,
  "aborted_at": null,
  "url": "https://app.com/profile",
  "steps": [
    {"ok": true, "action": "goto", "description": "Open login page", "url": "https://app.com/login"},
    {"ok": true, "action": "fill", "description": "fill"},
    ...
  ]
}
```

## Options

```
--json              Structured JSON output
--actions FILE      JSON file with multi-step action plan
--screenshot PATH   Save full-page screenshot
--session NAME      Cookie persistence (~/.phantom/sessions/)
--timeout MS        Navigation timeout (default: 30000)
--headless          Force headless mode
--headed            Force headed mode (requires display/Xvfb)
--locale LOCALE     Browser locale (default: en-US)
--timezone TZ       Browser timezone (default: America/New_York)
--viewport W H      Viewport size (default: 1366 768)
--min-delay SECS    Min seconds between requests to same domain (default: 2.0, 0 to disable)
--verbose           Debug logging
```

## What It Bypasses

Phantom bundles these anti-detection techniques:

- **playwright-stealth** — masks automation fingerprints
- **WebDriver spoofing** — hides `navigator.webdriver`
- **Blink feature flags** — disables `AutomationControlled`
- **Realistic fingerprint** — Chrome 131 User-Agent, configurable locale/timezone/viewport
- **Headed mode** — uses real GUI via Xvfb when available (harder to detect than headless)
- **Human-like input** — variable click timing, coordinate-based clicks, realistic type delays

## Using With AI Agents

Phantom is designed to be called by AI agents via subprocess. The `--json` flag gives structured output any agent can parse:

```python
import subprocess, json

result = subprocess.run(
    ["phantom", "https://example.com", "--json"],
    capture_output=True, text=True
)
data = json.loads(result.stdout)
if data["ok"]:
    page_text = data["text"]
```

## Rate Limiting

Phantom enforces a **2-second per-domain cooldown** by default to prevent abuse. If you call Phantom twice against the same domain in quick succession, the second call waits automatically.

```bash
phantom https://example.com --json         # goes through immediately
phantom https://example.com --json         # waits ~2s before requesting

phantom https://other-site.com --json      # different domain, no wait
```

Adjust with `--min-delay`:

```bash
phantom https://example.com --min-delay 5   # 5s between requests (be polite)
phantom https://localhost:3000 --min-delay 0 # disable for local/owned apps
```

## Responsible Use

Phantom is built for legitimate purposes: testing your own apps, accessing data you're authorized to retrieve, and building AI agents that browse the web respectfully.

**Do:**
- Test your own web applications
- Access sites and data you have permission to use
- Build agents that respect `robots.txt` and rate limits
- Use the default rate limiting

**Don't:**
- Scrape sites that prohibit it in their ToS
- Bypass authentication you're not authorized to use
- Use Phantom to overwhelm or degrade services
- Disable rate limiting against sites you don't own

The built-in rate limiter exists for a reason. If you find yourself setting `--min-delay 0` against someone else's site, reconsider.

## License

MIT
