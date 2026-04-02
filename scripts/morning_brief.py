#!/usr/bin/env python3
"""Morning brief generation script.

Fetches Gmail, Calendar, and market/news data in parallel, composes a markdown
brief via Ollama (Qwen3.5), and writes status/preview files to flask_app/data/.

Run from project root:
    python scripts/morning_brief.py
"""

import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'flask_app' / 'data'

# Load .env from project root
load_dotenv(PROJECT_ROOT / '.env')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum number of Gmail messages to fetch; balances LLM prompt size vs coverage
MAX_MESSAGES = 16

ACTIVE_HOLDINGS = 'SHLD, AVGO, CRDO, URA, CIBR, IBIT, AMPX, KRKNF, OSS, ASX:GOLD'

TAVILY_QUERIES = [
    'S&P 500 Nasdaq Dow close today',
    'VIX today',
    'US market sector performance today',
    'US market news today',
    'AUD USD exchange rate today',
    'ASX 200 SPI futures today',
    'ASX market news today',
    'SHLD stock news today',
    'AVGO stock news today',
    'CRDO stock news today',
    'URA stock news today',
    'CIBR stock news today',
    'IBIT stock news today',
    'AMPX stock news today',
    'KRKNF stock news today',
    'OSS stock news today',
    'ASX:GOLD stock news today',
    'US economic calendar this week',
    'ASX earnings calendar this week',
    'AVGO CRDO AMPX OSS earnings date 2026',
]

# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def load_credentials():
    """Load and refresh Google OAuth credentials from brief_token.json."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_path = DATA_DIR / 'brief_token.json'
    data = json.loads(token_path.read_text())
    creds = Credentials(
        token=data.get('token'),
        refresh_token=data.get('refresh_token'),
        token_uri=data.get('token_uri', 'https://oauth2.googleapis.com/token'),
        client_id=data.get('client_id'),
        client_secret=data.get('client_secret'),
        scopes=data.get('scopes'),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        data['token'] = creds.token
        write_json(token_path, data)
    return creds


# ---------------------------------------------------------------------------
# Data formatters (for LLM prompt)
# ---------------------------------------------------------------------------


def format_messages(messages: list) -> str:
    """Format Gmail messages as structured text for the LLM prompt."""
    if not messages:
        return '(no messages)'
    lines = []
    for i, msg in enumerate(messages, 1):
        subject = msg.get('subject', '(no subject)')
        sender = msg.get('from', '(unknown sender)')
        date_str = msg.get('date', '')
        snippet = msg.get('snippet', '')
        lines.append(f'{i}. From: {sender}')
        lines.append(f'   Subject: {subject}')
        if date_str:
            lines.append(f'   Date: {date_str}')
        if snippet:
            lines.append(f'   Preview: {snippet}')
        lines.append('')
    return '\n'.join(lines).rstrip()


def format_today_events(events: list) -> str:
    """Return plain-text list of events starting today."""
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
    today = date.today().isoformat()
    lines = []
    for event in events:
        start = event.get('start', {})
        start_str = start.get('date', start.get('dateTime', ''))
        if start_str.startswith(today):
            continue  # skip today — handled by format_today_events
        summary = event.get('summary', '(no title)')[:60]
        day_str = start_str[:10]
        lines.append(f'- {day_str} {summary}')
        if len(lines) >= 15:
            break
    return '\n'.join(lines) if lines else '(no events this week)'


def format_search_results(search_results: dict) -> str:
    """Format Tavily search results as structured text for the LLM prompt."""
    if not search_results:
        return '(no search results)'
    lines = []
    for query, result in search_results.items():
        lines.append(f'Query: {query}')
        if result.get('error'):
            lines.append(f'  Error: {result["error"]}')
        else:
            for item in result.get('results', []):
                title = item.get('title', '')
                content = item.get('content', '')
                if title:
                    lines.append(f'  • {title}')
                if content:
                    content_short = content[:300].replace('\n', ' ')
                    if len(content) > 300:
                        content_short += '...'
                    lines.append(f'    {content_short}')
        lines.append('')
    return '\n'.join(lines).rstrip()


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


_EXCLUDED_LABELS = {'CATEGORY_SOCIAL', 'CATEGORY_PROMOTIONS'}
_CATEGORY_EXCLUSION = '-category:social -category:promotions'


def fetch_gmail(creds) -> dict:
    """Fetch inbox emails since 9pm last night, excluding social/promotions/updates."""
    from googleapiclient.discovery import build

    # 9pm local time the previous evening as a Unix timestamp (Gmail accepts this)
    cutoff = datetime.combine(date.today() - timedelta(days=1), datetime.min.time().replace(hour=21))
    cutoff_ts = int(cutoff.timestamp())

    service = build('gmail', 'v1', credentials=creds)
    queries = [
        f'after:{cutoff_ts} in:inbox is:unread',
        'is:starred is:unread newer_than:7d',
    ]

    print(f'  Cutoff timestamp: {cutoff_ts} ({cutoff})', flush=True)

    # Sanity check: bare inbox fetch with no filters
    try:
        bare = service.users().messages().list(userId='me', q='in:inbox', maxResults=5).execute()
        bare_count = len(bare.get('messages', []))
        profile = service.users().getProfile(userId='me').execute()
        print(f'  Authenticated as: {profile.get("emailAddress")}', flush=True)
        print(f'  Bare "in:inbox" → {bare_count} results', flush=True)
        after_only = service.users().messages().list(userId='me', q=f'after:{cutoff_ts} in:inbox', maxResults=10).execute()
        print(f'  "after:{cutoff_ts} in:inbox" (no category filter) → {len(after_only.get("messages", []))} results', flush=True)
        cat_only = service.users().messages().list(userId='me', q=f'in:inbox {_CATEGORY_EXCLUSION}', maxResults=10).execute()
        print(f'  "in:inbox {_CATEGORY_EXCLUSION}" (no after filter) → {len(cat_only.get("messages", []))} results', flush=True)
    except Exception as e:
        print(f'  Bare inbox query failed: {e}', file=sys.stderr)

    seen_ids = set()
    message_ids = []
    for query in queries:
        try:
            resp = service.users().messages().list(
                userId='me', q=query, maxResults=50
            ).execute()
            count = len(resp.get('messages', []))
            print(f'  Query "{query}" → {count} results', flush=True)
            for msg in resp.get('messages', []):
                mid = msg['id']
                if mid not in seen_ids:
                    seen_ids.add(mid)
                    message_ids.append(mid)
        except Exception as e:
            print(f'  Gmail query "{query}" failed: {e}', file=sys.stderr)

    messages = []
    unread_count = 0
    for mid in message_ids:
        if len(messages) >= MAX_MESSAGES:
            break
        try:
            msg = service.users().messages().get(
                userId='me', id=mid, format='full'
            ).execute()

            labels = msg.get('labelIds', [])

            # Skip if any excluded category label is present
            if _EXCLUDED_LABELS.intersection(labels):
                print(f'  Skipped {mid} due to labels: {labels}', flush=True)
                continue

            headers = {
                h['name'].lower(): h['value']
                for h in msg.get('payload', {}).get('headers', [])
            }
            if 'UNREAD' in labels:
                unread_count += 1

            messages.append({
                'id': mid,
                'subject': headers.get('subject', '(no subject)'),
                'from': headers.get('from', '(unknown)'),
                'date': headers.get('date', ''),
                'snippet': msg.get('snippet', ''),
                'labels': labels,
            })
        except Exception as e:
            print(f'Failed to fetch message {mid}: {e}', file=sys.stderr)

    return {'messages': messages, 'unread_count': unread_count}


def fetch_calendar(creds) -> list:
    """Fetch upcoming calendar events for the next 7 days."""
    from googleapiclient.discovery import build

    service = build('calendar', 'v3', credentials=creds)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + 'Z'
    end = (datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)).isoformat() + 'Z'
    result = service.events().list(
        calendarId='primary',
        timeMin=now,
        timeMax=end,
        singleEvents=True,
        orderBy='startTime',
        maxResults=50,
    ).execute()
    return result.get('items', [])


def search_tavily(client, query: str) -> dict:
    """Run a single Tavily search query, returning results or an error."""
    try:
        result = client.search(query, max_results=3)
        return {'query': query, 'results': result.get('results', [])}
    except Exception as e:
        return {'query': query, 'results': [], 'error': str(e)}


# ---------------------------------------------------------------------------
# Ollama composition
# ---------------------------------------------------------------------------


def _call_ollama(prompt: str) -> str:
    """Make a single non-streaming Ollama call and return the response text."""
    ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    model = os.getenv('OLLAMA_MODEL', 'qwen3.5:latest')

    response = httpx.post(
        f'{ollama_url}/api/chat',
        json={
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'stream': False,
            'think': False,
            'options': {'num_ctx': 8192},
        },
        timeout=300.0,
    )
    response.raise_for_status()
    raw = response.json()['message']['content'].strip()

    # Strip <think>...</think> reasoning blocks (Qwen3 thinking mode)
    if '<think>' in raw:
        raw = raw.split('</think>', 1)[-1].strip()

    return raw


def summarise_gmail(gmail_data: dict) -> str:
    """Call Ollama to summarise Gmail data. Returns a markdown section string."""
    prompt = f"""Write the Email Highlights section of Ryan Hogan's morning brief in markdown.

        Use this structure:
        ## 📧 Email Highlights
        **{gmail_data.get('unread_count', 0)} unread**
        
        ### ⚠️ Action Required
        - (bullet list of emails needing a reply or action, or "Nothing urgent")
        
        ### 📬 Other Notable
        - (bullet list of other notable emails, one line each: Sender — summary)
        
        Be concise. Only include genuinely notable emails.
        
        === EMAILS ===
        {format_messages(gmail_data.get('messages', []))}
        """
    return _call_ollama(prompt)


def summarise_markets(search_results: dict, today_str: str) -> str:
    """Call Ollama to summarise market/holdings data. Returns a markdown section string."""
    prompt = f"""Write the markets and holdings sections of Ryan Hogan's morning brief in markdown.
Today is {today_str}. Ryan's active holdings: {ACTIVE_HOLDINGS}.

Use this structure:
## 🇺🇸 US Markets Overnight
(Table or bullet list: S&P 500, Nasdaq, Dow — level and % change. VIX. Key sector movers. 1-2 sentence market theme.)

## 🇦🇺 ASX Today
(AUD/USD rate with direction. ASX 200 open estimate. 2-3 bullet points on what to watch.)

## 💼 Portfolio — Holdings Watch
(One bullet per holding: **TICKER** — one-line news summary + signal: 🟢 Positive / 🔴 Negative / 🟡 Watch / ⚪ No news)

## 🗓️ Week Ahead
(Key US economic events this week as a short list. Any earnings dates for holdings.)

Be concise and scannable. Use data from the search results below.

=== MARKET & NEWS DATA ===
{format_search_results(search_results)}
"""
    return _call_ollama(prompt)


def build_calendar_md(calendar_data: list) -> str:
    """Build the calendar section directly from structured data — no LLM needed."""
    today_events = format_today_events(calendar_data)
    week_events = format_week_events(calendar_data)
    return f"""## 📅 Calendar

**Today**
{today_events}

**This Week**
{week_events}
"""


def assemble_brief(gmail_md: str, markets_md: str, calendar_md: str, today_str: str) -> str:
    """Combine all markdown sections into the full brief."""
    return f"""# Morning Brief — {today_str}

{gmail_md}

{calendar_md}

{markets_md}
"""


# ---------------------------------------------------------------------------
# Atomic file writes
# ---------------------------------------------------------------------------


def write_json(path: Path, data: dict):
    """Write a JSON file atomically using a temp file + os.replace."""
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise


def write_file(path: Path, content: str):
    """Write a text file atomically using a temp file + os.replace."""
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    from tavily import TavilyClient

    today = datetime.now()
    today_str = today.strftime('%A, %B %-d, %Y')

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    write_json(DATA_DIR / 'brief_status.json', {
        'status': 'running',
        'generated_at': datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        'error': None,
        'gmail_connected': True,
    })

    creds = load_credentials()
    tavily_client = TavilyClient(api_key=os.getenv('TAVILY_API_KEY', ''))

    # Fetch all data in parallel
    with ThreadPoolExecutor(max_workers=len(TAVILY_QUERIES) + 2) as executor:
        gmail_future = executor.submit(fetch_gmail, creds)
        calendar_future = executor.submit(fetch_calendar, creds)
        search_futures = {
            q: executor.submit(search_tavily, tavily_client, q)
            for q in TAVILY_QUERIES
        }

    gmail_data = gmail_future.result()
    calendar_data = calendar_future.result()
    search_results = {q: f.result() for q, f in search_futures.items()}

    print(f'\n=== Gmail debug: {gmail_data["unread_count"]} unread, {len(gmail_data["messages"])} messages fetched ===', flush=True)
    for i, msg in enumerate(gmail_data['messages'], 1):
        print(f'  {i}. [{", ".join(msg.get("labels", []))}] {msg.get("from", "")} — {msg.get("subject", "")}', flush=True)
    print('', flush=True)

    print('Summarising Gmail…', flush=True)
    gmail_md = summarise_gmail(gmail_data)

    print('Summarising markets…', flush=True)
    markets_md = summarise_markets(search_results, today_str)

    print('Assembling brief…', flush=True)
    calendar_md = build_calendar_md(calendar_data)
    brief_md = assemble_brief(gmail_md, markets_md, calendar_md, today_str)

    write_file(DATA_DIR / 'morning_brief.md', brief_md)

    write_json(DATA_DIR / 'brief_status.json', {
        'status': 'success',
        'generated_at': datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        'error': None,
        'gmail_connected': True,
    })

    print('Morning brief generated.')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        write_json(DATA_DIR / 'brief_status.json', {
            'status': 'error',
            'generated_at': datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            'error': str(e),
            'gmail_connected': True,
        })
        traceback.print_exc()
        sys.exit(1)
