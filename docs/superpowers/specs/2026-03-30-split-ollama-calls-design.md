# Split Ollama Calls Design

**Date:** 2026-03-30
**Status:** Approved

## Problem

The current `compose_brief()` function sends a single large prompt to Qwen3.5 (~6,850 tokens) that exceeds Ollama's default 4,096-token context window, causing silent truncation and incomplete briefs.

## Solution

Replace the single `compose_brief()` call with two focused sequential Ollama calls plus pure-Python HTML assembly. The HTML template is never sent to Qwen — only data goes in, structured JSON comes out.

---

## Architecture

```
fetch data (parallel, unchanged)
        │
        ▼
summarise_gmail(gmail_data)              ~800 token prompt → gmail_values: dict
        │
        ▼
summarise_markets(search_results, today_str)  ~1,200 token prompt → market_values: dict
        │
        ▼
assemble_html(gmail_values, market_values, calendar_data, today_str)  → html: str
        │
        ▼
create_draft(...)  (unchanged)
```

---

## Components

### `_call_ollama(prompt: str) -> dict`

Shared helper extracted from the current `compose_brief()`. Makes a single non-streaming Ollama call, strips markdown code fences from the response, parses and returns the JSON dict. Raises on HTTP error or invalid JSON.

```python
def _call_ollama(prompt: str) -> dict:
    # POST to OLLAMA_BASE_URL/api/chat with stream=False, timeout=300s
    # Strip ```json ... ``` fences if present
    # Return json.loads(raw)
```

---

### `summarise_gmail(gmail_data: dict) -> dict`

**Prompt target:** ~800 tokens

**Input:** formatted Gmail messages + unread count

**Prompt:**
```
You are processing emails for Ryan Hogan's morning brief.
Return ONLY a valid JSON object with keys: UNREAD_COUNT, ACTION_ITEMS, OTHER_EMAILS_LIST.
ACTION_ITEMS: HTML <div> blocks for emails needing reply/action. Empty string if none.
OTHER_EMAILS_LIST: HTML <div> lines for other notable emails, one per email.

=== GMAIL (N unread) ===
{format_messages(gmail_data['messages'])}
```

**Output keys:**
- `UNREAD_COUNT` — string, e.g. `"12"`
- `ACTION_ITEMS` — HTML string (the red action block content), empty string if none
- `OTHER_EMAILS_LIST` — HTML string (one `<div>` per email)

---

### `summarise_markets(search_results: dict, today_str: str) -> dict`

**Prompt target:** ~1,200 tokens

**Input:** all Tavily search results + today's date

**Prompt:**
```
You are processing market and news data for Ryan Hogan's morning brief.
Today is {today_str}. Ryan's active holdings: SHLD, AVGO, CRDO, URA, CIBR, IBIT, AMPX, KRKNF, OSS, ASX:GOLD.
Return ONLY a valid JSON object with these keys: [all market keys listed].
For colour fields use #22c55e (green/positive) or #ef4444 (red/negative).
HOLDINGS_CONTENT: HTML div blocks per holding with ticker badge + signal badge.
WEEK_EVENTS_TABLE: HTML <tr> rows only (no <table> wrapper).

=== MARKET & NEWS DATA ===
{format_search_results(search_results)}
```

**Output keys:**
- `US_CLOSE_DATE` — e.g. `"Friday 28 Mar"`
- `SP500_LEVEL`, `SP500_PCT`, `SP500_COLOUR`
- `NASDAQ_LEVEL`, `NASDAQ_PCT`, `NASDAQ_COLOUR`
- `DOW_LEVEL`, `DOW_PCT`, `DOW_COLOUR`
- `VIX`, `VIX_INTERPRETATION`
- `SECTOR_MOVERS` — plain text, 2-3 lines
- `MARKET_THEMES` — plain text, 2-3 themes
- `AUD_RATE`, `AUD_PCT`, `AUD_ARROW`, `AUD_COLOUR`, `AUD_CONTEXT`
- `ASX_OPEN`, `ASX_COLOUR`, `ASX_CONTEXT`
- `ASX_WATCH` — plain text, 2-3 lines
- `HOLDINGS_CONTENT` — HTML div blocks
- `WEEK_EVENTS_TABLE` — HTML `<tr>` rows only
- `HOLDINGS_EARNINGS` — plain text

---

### `format_today_events(events: list) -> str`

Splits the existing `format_calendar()` — returns only events where `start.date` or `start.dateTime` falls on today. Returns plain text (one line per event). Used in `assemble_html()`.

### `format_week_events(events: list) -> str`

Returns events from tomorrow through end of the 7-day window. Returns plain text (one line per event). Used in `assemble_html()`.

---

### `assemble_html(gmail_values, market_values, calendar_data, today_str) -> str`

Pure Python — no Ollama call. Merges the two JSON dicts with Python-computed date/calendar fields, then substitutes into `HTML_TEMPLATE`.

```python
calendar_values = {
    'FULL_DATE': today_str,
    'SHORT_DATE': datetime.now().strftime('%d %b'),
    'TODAY_EVENTS': format_today_events(calendar_data),
    'WEEK_EVENTS': format_week_events(calendar_data),
}
values = {**gmail_values, **market_values, **calendar_values}
html = HTML_TEMPLATE
for key, value in values.items():
    html = html.replace('{{' + key + '}}', str(value))
return html
```

---

## Changes to `main()`

Replace:
```python
html_content = compose_brief(gmail_data, calendar_data, search_results, today_str)
```

With:
```python
gmail_values = summarise_gmail(gmail_data)
market_values = summarise_markets(search_results, today_str)
html_content = assemble_html(gmail_values, market_values, calendar_data, today_str)
```

Remove `compose_brief()` entirely.

---

## File Modified

- `scripts/morning_brief.py` — only file changed

## Functions Removed
- `compose_brief()`
- `format_calendar()` (replaced by `format_today_events()` + `format_week_events()`)

## Functions Added
- `_call_ollama(prompt)`
- `summarise_gmail(gmail_data)`
- `summarise_markets(search_results, today_str)`
- `format_today_events(events)`
- `format_week_events(events)`
- `assemble_html(gmail_values, market_values, calendar_data, today_str)`

---

## Error Handling

If either Qwen call returns invalid JSON or times out, the exception propagates to `main()`'s existing `try/except` which writes `{"status": "error", ...}` to `brief_status.json` and exits with code 1. No change needed.

## Testing

- Run `Generate Now` in the dashboard — Ollama logs should show two separate calls each well under 4,096 tokens
- Check `flask_app/data/brief_status.json` shows `"status": "success"` after completion
- Open Gmail drafts to verify the brief was created with all sections populated
