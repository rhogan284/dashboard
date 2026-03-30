# Split Ollama Calls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single large `compose_brief()` Ollama call with two focused sequential calls (`summarise_gmail()` and `summarise_markets()`) plus pure-Python HTML assembly, keeping each prompt under ~1,500 tokens to stay within Qwen3.5's 4,096-token context window.

**Architecture:** Two sequential Ollama calls — one for Gmail summarisation, one for market/holdings data — each returning a small JSON object. Python merges both dicts with calendar data and substitutes into `HTML_TEMPLATE`. No LLM sees the HTML template.

**Tech Stack:** Python 3.12, Ollama (Qwen3.5), httpx, existing `HTML_TEMPLATE` constant

---

## File Modified

- `scripts/morning_brief.py` — only file changed

**Functions removed:**
- `compose_brief()`
- `format_calendar()` (replaced by `format_today_events()` + `format_week_events()`)

**Functions added:**
- `_call_ollama(prompt: str) -> dict`
- `format_today_events(events: list) -> str`
- `format_week_events(events: list) -> str`
- `summarise_gmail(gmail_data: dict) -> dict`
- `summarise_markets(search_results: dict, today_str: str) -> dict`
- `assemble_html(gmail_values: dict, market_values: dict, calendar_data: list, today_str: str) -> str`

**`main()` change:** replace `compose_brief(...)` with three sequential calls.

---

## Task 1: Add `_call_ollama()` shared helper + replace `format_calendar()`

**Files:**
- Modify: `scripts/morning_brief.py`

- [ ] **Step 1: Write the failing tests**

Add to `flask_app/tests/test_brief.py`:

```python
def test_format_today_events_returns_today_only(monkeypatch):
    """format_today_events returns only events starting today."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from morning_brief import format_today_events
    from datetime import date
    today = date.today().isoformat()
    tomorrow = (date.today() + __import__('datetime').timedelta(days=1)).isoformat()
    events = [
        {'summary': 'Today meeting', 'start': {'date': today}},
        {'summary': 'Tomorrow event', 'start': {'date': tomorrow}},
    ]
    result = format_today_events(events)
    assert 'Today meeting' in result
    assert 'Tomorrow event' not in result


def test_format_today_events_empty():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from morning_brief import format_today_events
    assert format_today_events([]) == '(nothing scheduled today)'


def test_format_week_events_excludes_today(monkeypatch):
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from morning_brief import format_week_events
    from datetime import date
    today = date.today().isoformat()
    tomorrow = (date.today() + __import__('datetime').timedelta(days=1)).isoformat()
    events = [
        {'summary': 'Today meeting', 'start': {'date': today}},
        {'summary': 'Tomorrow event', 'start': {'date': tomorrow}},
    ]
    result = format_week_events(events)
    assert 'Tomorrow event' in result
    assert 'Today meeting' not in result


def test_format_week_events_empty():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from morning_brief import format_week_events
    assert format_week_events([]) == '(no events this week)'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "/Users/ryanhogan/Desktop/Coding Work/Dashboard"
flask_app/.venv/bin/python -m pytest flask_app/tests/test_brief.py -k "format_today or format_week" -v
```

Expected: 4 failures — `ImportError` or `cannot import name`

- [ ] **Step 3: Add `_call_ollama()`, `format_today_events()`, `format_week_events()` to the script**

In `scripts/morning_brief.py`, replace the existing `format_calendar()` function (lines ~312-322) and add `_call_ollama()` in the Qwen composition section (around line 438). The full replacements:

**Replace `format_calendar()` with two functions** (find `def format_calendar` and replace the whole function):

```python
def format_today_events(events: list) -> str:
    """Return plain-text list of events starting today."""
    from datetime import date
    today = date.today().isoformat()
    lines = []
    for event in events:
        start = event.get('start', {})
        start_str = start.get('date', start.get('dateTime', ''))
        if not start_str.startswith(today):
            continue
        summary = event.get('summary', '(no title)')[:60]
        time_str = start_str[11:16] if 'T' in start_str else 'all day'
        lines.append(f'- {time_str} {summary}')
    return '\n'.join(lines) if lines else '(nothing scheduled today)'


def format_week_events(events: list) -> str:
    """Return plain-text list of events after today through end of 7-day window."""
    from datetime import date
    today = date.today().isoformat()
    lines = []
    for event in events[:15]:
        start = event.get('start', {})
        start_str = start.get('date', start.get('dateTime', ''))
        if start_str.startswith(today):
            continue  # skip today — handled by format_today_events
        summary = event.get('summary', '(no title)')[:60]
        day_str = start_str[:10]
        lines.append(f'- {day_str} {summary}')
    return '\n'.join(lines) if lines else '(no events this week)'
```

**Add `_call_ollama()` helper** — insert before `compose_brief()` (around line 442, in the Qwen composition section):

```python
def _call_ollama(prompt: str) -> dict:
    """Make a single non-streaming Ollama call and return parsed JSON dict."""
    import httpx

    ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    model = os.getenv('OLLAMA_MODEL', 'qwen3.5:latest')

    response = httpx.post(
        f'{ollama_url}/api/chat',
        json={
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'stream': False,
        },
        timeout=300.0,
    )
    response.raise_for_status()
    raw = response.json()['message']['content'].strip()

    # Strip markdown code fences if model wraps output
    if raw.startswith('```'):
        raw = raw.split('\n', 1)[-1]
        raw = raw.rsplit('```', 1)[0].strip()

    return json.loads(raw)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "/Users/ryanhogan/Desktop/Coding Work/Dashboard"
flask_app/.venv/bin/python -m pytest flask_app/tests/test_brief.py -k "format_today or format_week" -v
```

Expected: 4 passing

- [ ] **Step 5: Run full test suite to check nothing broke**

```bash
flask_app/.venv/bin/python -m pytest flask_app/tests/ -v
```

Expected: all passing

- [ ] **Step 6: Commit**

```bash
git add scripts/morning_brief.py flask_app/tests/test_brief.py
git commit -m "feat: add _call_ollama helper, format_today/week_events, replace format_calendar"
```

---

## Task 2: Add `summarise_gmail()`

**Files:**
- Modify: `scripts/morning_brief.py`
- Modify: `flask_app/tests/test_brief.py`

- [ ] **Step 1: Write the failing test**

Add to `flask_app/tests/test_brief.py`:

```python
def test_summarise_gmail_returns_required_keys():
    """summarise_gmail returns dict with UNREAD_COUNT, ACTION_ITEMS, OTHER_EMAILS_LIST."""
    import sys, os
    from unittest.mock import patch
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from morning_brief import summarise_gmail

    fake_response = {
        'UNREAD_COUNT': '3',
        'ACTION_ITEMS': '<div>Reply to John</div>',
        'OTHER_EMAILS_LIST': '<div>Newsletter</div>',
    }

    with patch('morning_brief._call_ollama', return_value=fake_response):
        result = summarise_gmail({'messages': [], 'unread_count': 3})

    assert result['UNREAD_COUNT'] == '3'
    assert 'ACTION_ITEMS' in result
    assert 'OTHER_EMAILS_LIST' in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "/Users/ryanhogan/Desktop/Coding Work/Dashboard"
flask_app/.venv/bin/python -m pytest flask_app/tests/test_brief.py::test_summarise_gmail_returns_required_keys -v
```

Expected: FAIL — `cannot import name 'summarise_gmail'`

- [ ] **Step 3: Add `summarise_gmail()` to `scripts/morning_brief.py`**

Add after `_call_ollama()`:

```python
def summarise_gmail(gmail_data: dict) -> dict:
    """Call Ollama to summarise Gmail data. Returns dict with email section values."""
    prompt = f"""You are processing emails for Ryan Hogan's morning brief.
Return ONLY a valid JSON object with exactly these three keys:
- UNREAD_COUNT: string, the number of unread emails
- ACTION_ITEMS: HTML string — <div> blocks for emails needing a reply or action. Empty string if none.
- OTHER_EMAILS_LIST: HTML string — one <div> per other notable email, format: <div>📧 <strong>Sender</strong> — one line summary.</div>

=== GMAIL ({gmail_data['unread_count']} unread) ===
{format_messages(gmail_data['messages'])}
"""
    return _call_ollama(prompt)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd "/Users/ryanhogan/Desktop/Coding Work/Dashboard"
flask_app/.venv/bin/python -m pytest flask_app/tests/test_brief.py::test_summarise_gmail_returns_required_keys -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/morning_brief.py flask_app/tests/test_brief.py
git commit -m "feat: add summarise_gmail() with focused Ollama prompt"
```

---

## Task 3: Add `summarise_markets()`

**Files:**
- Modify: `scripts/morning_brief.py`
- Modify: `flask_app/tests/test_brief.py`

- [ ] **Step 1: Write the failing test**

Add to `flask_app/tests/test_brief.py`:

```python
def test_summarise_markets_returns_required_keys():
    """summarise_markets returns dict with all market/holdings keys."""
    import sys, os
    from unittest.mock import patch
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from morning_brief import summarise_markets

    fake_response = {
        'US_CLOSE_DATE': 'Friday 28 Mar',
        'SP500_LEVEL': '5,580', 'SP500_PCT': '-1.1%', 'SP500_COLOUR': '#ef4444',
        'NASDAQ_LEVEL': '17,322', 'NASDAQ_PCT': '-1.6%', 'NASDAQ_COLOUR': '#ef4444',
        'DOW_LEVEL': '41,583', 'DOW_PCT': '-0.7%', 'DOW_COLOUR': '#ef4444',
        'VIX': '21.7', 'VIX_INTERPRETATION': 'Elevated caution',
        'SECTOR_MOVERS': 'Energy +0.4%', 'MARKET_THEMES': 'Tariff fears',
        'AUD_RATE': '0.6281', 'AUD_PCT': '-0.4%', 'AUD_ARROW': '↓',
        'AUD_COLOUR': '#ef4444', 'AUD_CONTEXT': 'Risk-off',
        'ASX_OPEN': '-0.6%', 'ASX_COLOUR': '#ef4444', 'ASX_CONTEXT': 'SPI lower',
        'ASX_WATCH': 'BHP ex-div',
        'HOLDINGS_CONTENT': '<div>AVGO — No news</div>',
        'WEEK_EVENTS_TABLE': '<tr><td>Mon</td><td>PCE</td><td>Inflation</td></tr>',
        'HOLDINGS_EARNINGS': 'AVGO: 11 Jun',
    }

    with patch('morning_brief._call_ollama', return_value=fake_response):
        result = summarise_markets({}, 'Monday, March 30, 2026')

    required_keys = [
        'US_CLOSE_DATE', 'SP500_LEVEL', 'SP500_PCT', 'SP500_COLOUR',
        'NASDAQ_LEVEL', 'NASDAQ_PCT', 'NASDAQ_COLOUR',
        'DOW_LEVEL', 'DOW_PCT', 'DOW_COLOUR',
        'VIX', 'VIX_INTERPRETATION', 'SECTOR_MOVERS', 'MARKET_THEMES',
        'AUD_RATE', 'AUD_PCT', 'AUD_ARROW', 'AUD_COLOUR', 'AUD_CONTEXT',
        'ASX_OPEN', 'ASX_COLOUR', 'ASX_CONTEXT', 'ASX_WATCH',
        'HOLDINGS_CONTENT', 'WEEK_EVENTS_TABLE', 'HOLDINGS_EARNINGS',
    ]
    for key in required_keys:
        assert key in result, f'Missing key: {key}'
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "/Users/ryanhogan/Desktop/Coding Work/Dashboard"
flask_app/.venv/bin/python -m pytest flask_app/tests/test_brief.py::test_summarise_markets_returns_required_keys -v
```

Expected: FAIL — `cannot import name 'summarise_markets'`

- [ ] **Step 3: Add `summarise_markets()` to `scripts/morning_brief.py`**

Add after `summarise_gmail()`:

```python
MARKET_JSON_KEYS = (
    'US_CLOSE_DATE, SP500_LEVEL, SP500_PCT, SP500_COLOUR, '
    'NASDAQ_LEVEL, NASDAQ_PCT, NASDAQ_COLOUR, '
    'DOW_LEVEL, DOW_PCT, DOW_COLOUR, '
    'VIX, VIX_INTERPRETATION, SECTOR_MOVERS, MARKET_THEMES, '
    'AUD_RATE, AUD_PCT, AUD_ARROW, AUD_COLOUR, AUD_CONTEXT, '
    'ASX_OPEN, ASX_COLOUR, ASX_CONTEXT, ASX_WATCH, '
    'HOLDINGS_CONTENT, WEEK_EVENTS_TABLE, HOLDINGS_EARNINGS'
)

ACTIVE_HOLDINGS = 'SHLD, AVGO, CRDO, URA, CIBR, IBIT, AMPX, KRKNF, OSS, ASX:GOLD'


def summarise_markets(search_results: dict, today_str: str) -> dict:
    """Call Ollama to summarise market/holdings data. Returns dict with market section values."""
    prompt = f"""You are processing market and news data for Ryan Hogan's morning brief.
Today is {today_str}. Ryan's active holdings: {ACTIVE_HOLDINGS}.

Return ONLY a valid JSON object with exactly these keys:
{MARKET_JSON_KEYS}

Rules:
- Colour fields: use #22c55e (positive/green) or #ef4444 (negative/red)
- AUD_ARROW: ↑ or ↓
- HOLDINGS_CONTENT: HTML <div> block per holding with ticker + one-line news + signal badge (🟢 Positive / 🔴 Negative / 🟡 Watch / ⚪ No news)
- WEEK_EVENTS_TABLE: HTML <tr> rows only, no <table> wrapper
- HOLDINGS_EARNINGS: plain text, one holding per line

=== MARKET & NEWS DATA ===
{format_search_results(search_results)}
"""
    return _call_ollama(prompt)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd "/Users/ryanhogan/Desktop/Coding Work/Dashboard"
flask_app/.venv/bin/python -m pytest flask_app/tests/test_brief.py::test_summarise_markets_returns_required_keys -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/morning_brief.py flask_app/tests/test_brief.py
git commit -m "feat: add summarise_markets() with focused Ollama prompt"
```

---

## Task 4: Add `assemble_html()` and wire up `main()`

**Files:**
- Modify: `scripts/morning_brief.py`
- Modify: `flask_app/tests/test_brief.py`

- [ ] **Step 1: Write the failing test**

Add to `flask_app/tests/test_brief.py`:

```python
def test_assemble_html_substitutes_all_placeholders():
    """assemble_html fills all {{KEY}} placeholders in a minimal template."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
    from morning_brief import assemble_html

    gmail_values = {
        'UNREAD_COUNT': '5',
        'ACTION_ITEMS': '<div>Reply to boss</div>',
        'OTHER_EMAILS_LIST': '<div>Newsletter</div>',
    }
    market_values = {
        'US_CLOSE_DATE': 'Friday 28 Mar',
        'SP500_LEVEL': '5,580', 'SP500_PCT': '-1.1%', 'SP500_COLOUR': '#ef4444',
        'NASDAQ_LEVEL': '17,322', 'NASDAQ_PCT': '-1.6%', 'NASDAQ_COLOUR': '#ef4444',
        'DOW_LEVEL': '41,583', 'DOW_PCT': '-0.7%', 'DOW_COLOUR': '#ef4444',
        'VIX': '21.7', 'VIX_INTERPRETATION': 'Elevated',
        'SECTOR_MOVERS': 'Tech -2%', 'MARKET_THEMES': 'Tariffs',
        'AUD_RATE': '0.6281', 'AUD_PCT': '-0.4%', 'AUD_ARROW': '↓',
        'AUD_COLOUR': '#ef4444', 'AUD_CONTEXT': 'Risk-off',
        'ASX_OPEN': '-0.6%', 'ASX_COLOUR': '#ef4444', 'ASX_CONTEXT': 'Lower',
        'ASX_WATCH': 'BHP ex-div',
        'HOLDINGS_CONTENT': '<div>AVGO ⚪</div>',
        'WEEK_EVENTS_TABLE': '<tr><td>PCE</td></tr>',
        'HOLDINGS_EARNINGS': 'AVGO: Jun 11',
    }
    calendar_data = []

    html = assemble_html(gmail_values, market_values, calendar_data, 'Monday, March 30, 2026')

    assert '{{' not in html, 'Unfilled placeholders remain in output'
    assert 'Monday, March 30, 2026' in html
    assert '5,580' in html
    assert 'Reply to boss' in html
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "/Users/ryanhogan/Desktop/Coding Work/Dashboard"
flask_app/.venv/bin/python -m pytest flask_app/tests/test_brief.py::test_assemble_html_substitutes_all_placeholders -v
```

Expected: FAIL — `cannot import name 'assemble_html'`

- [ ] **Step 3: Add `assemble_html()` to `scripts/morning_brief.py`**

Add after `summarise_markets()`, replacing the existing `compose_brief()`:

```python
def assemble_html(
    gmail_values: dict,
    market_values: dict,
    calendar_data: list,
    today_str: str,
) -> str:
    """Merge all values and substitute into HTML_TEMPLATE. No Ollama call."""
    short_date = datetime.now().strftime('%d %b')

    calendar_values = {
        'FULL_DATE': today_str,
        'SHORT_DATE': short_date,
        'TODAY_EVENTS': format_today_events(calendar_data),
        'WEEK_EVENTS': format_week_events(calendar_data),
    }

    values = {**gmail_values, **market_values, **calendar_values}

    html = HTML_TEMPLATE
    for key, value in values.items():
        html = html.replace('{{' + key + '}}', str(value))
    return html
```

Then **remove `compose_brief()`** entirely (the old function from line ~442).

- [ ] **Step 4: Update `main()` to use the three new functions**

Find in `main()`:
```python
    # Compose with Qwen via Ollama
    print('Composing brief with Qwen3.5…', flush=True)
    html_content = compose_brief(gmail_data, calendar_data, search_results, today_str)
```

Replace with:
```python
    # Summarise with Qwen via Ollama (two sequential focused calls)
    print('Summarising Gmail with Qwen3.5…', flush=True)
    gmail_values = summarise_gmail(gmail_data)

    print('Summarising markets with Qwen3.5…', flush=True)
    market_values = summarise_markets(search_results, today_str)

    print('Assembling HTML…', flush=True)
    html_content = assemble_html(gmail_values, market_values, calendar_data, today_str)
```

- [ ] **Step 5: Run the new test to verify it passes**

```bash
cd "/Users/ryanhogan/Desktop/Coding Work/Dashboard"
flask_app/.venv/bin/python -m pytest flask_app/tests/test_brief.py::test_assemble_html_substitutes_all_placeholders -v
```

Expected: PASS

- [ ] **Step 6: Run full test suite**

```bash
flask_app/.venv/bin/python -m pytest flask_app/tests/ -v
```

Expected: all passing

- [ ] **Step 7: Commit**

```bash
git add scripts/morning_brief.py flask_app/tests/test_brief.py
git commit -m "feat: add assemble_html(), wire up two-call pipeline in main()"
```

---

## Verification

1. Start the app and open the Morning Brief tab
2. Click **Generate Now**
3. Watch Ollama logs — should see two separate inference calls, each printing a token count well under 4,096
4. Status bar should update to "Draft saved" within ~2–3 minutes
5. Open Gmail drafts — verify the brief has all sections populated with no unfilled `{{PLACEHOLDER}}` tokens
6. Run full tests one final time: `flask_app/.venv/bin/python -m pytest flask_app/tests/ -v`
