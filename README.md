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

## Options

```
--json              Structured JSON output
--screenshot PATH   Save full-page screenshot
--session NAME      Cookie persistence (~/.phantom/sessions/)
--timeout MS        Navigation timeout (default: 30000)
--headless          Force headless mode
--headed            Force headed mode (requires display/Xvfb)
--locale LOCALE     Browser locale (default: en-US)
--timezone TZ       Browser timezone (default: America/New_York)
--viewport W H      Viewport size (default: 1366 768)
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

## License

MIT
