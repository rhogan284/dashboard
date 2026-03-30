#!/Users/ryanhogan/Desktop/Coding Work/Dashboard/flask_app/.venv/bin/python
"""Morning brief generation script.

Fetches Gmail, Calendar, and market/news data in parallel, composes an HTML
brief via Ollama (Qwen3.5), creates a Gmail draft, and writes status/preview
files to flask_app/data/.

Run from project root:
    python scripts/morning_brief.py
"""

import base64
import json
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / 'flask_app' / 'data'

# Load .env from project root
load_dotenv(PROJECT_ROOT / '.env')

# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Morning Brief — {{FULL_DATE}}</title>
</head>
<body style="margin:0;padding:0;background:#f4f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1f2937;">

<!-- HEADER -->
<div style="background:linear-gradient(135deg,#1a1a2e 0%,#16213e 60%,#0f3460 100%);padding:36px 32px 28px;text-align:center;">
  <p style="margin:0 0 6px;font-size:12px;letter-spacing:3px;text-transform:uppercase;color:#94a3b8;font-weight:500;">Your Morning Brief</p>
  <h1 style="margin:0 0 8px;font-size:34px;font-weight:700;color:#fff;letter-spacing:-0.5px;">Good morning, Ryan ☀️</h1>
  <p style="margin:0;font-size:15px;color:#93c5fd;">{{FULL_DATE}}</p>
</div>

<!-- STATS BAR -->
<div style="background:#0f172a;padding:12px 24px;display:flex;flex-wrap:wrap;gap:0;">
  <div style="flex:1;min-width:110px;text-align:center;border-right:1px solid #1e293b;padding:4px 12px;">
    <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:3px;">S&amp;P 500</div>
    <div style="font-size:16px;font-weight:700;color:{{SP500_COLOUR}};">{{SP500_LEVEL}} {{SP500_PCT}}</div>
  </div>
  <div style="flex:1;min-width:110px;text-align:center;border-right:1px solid #1e293b;padding:4px 12px;">
    <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:3px;">Nasdaq</div>
    <div style="font-size:16px;font-weight:700;color:{{NASDAQ_COLOUR}};">{{NASDAQ_LEVEL}} {{NASDAQ_PCT}}</div>
  </div>
  <div style="flex:1;min-width:110px;text-align:center;border-right:1px solid #1e293b;padding:4px 12px;">
    <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:3px;">Dow</div>
    <div style="font-size:16px;font-weight:700;color:{{DOW_COLOUR}};">{{DOW_LEVEL}} {{DOW_PCT}}</div>
  </div>
  <div style="flex:1;min-width:110px;text-align:center;border-right:1px solid #1e293b;padding:4px 12px;">
    <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:3px;">VIX</div>
    <div style="font-size:16px;font-weight:700;color:#f59e0b;">{{VIX}}</div>
  </div>
  <div style="flex:1;min-width:110px;text-align:center;border-right:1px solid #1e293b;padding:4px 12px;">
    <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:3px;">AUD/USD</div>
    <div style="font-size:16px;font-weight:700;color:{{AUD_COLOUR}};">{{AUD_RATE}} {{AUD_ARROW}}</div>
  </div>
  <div style="flex:1;min-width:110px;text-align:center;padding:4px 12px;">
    <div style="font-size:10px;color:#64748b;text-transform:uppercase;letter-spacing:1px;margin-bottom:3px;">ASX 200</div>
    <div style="font-size:16px;font-weight:700;color:{{ASX_COLOUR}};">{{ASX_OPEN}}</div>
  </div>
</div>

<div style="max-width:860px;margin:0 auto;padding:24px 20px 40px;">

<!-- EMAIL HIGHLIGHTS -->
<div style="background:#fff;border-radius:12px;padding:28px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
  <div style="display:flex;align-items:center;margin-bottom:20px;">
    <span style="font-size:20px;margin-right:10px;">📧</span>
    <h2 style="margin:0;font-size:18px;font-weight:700;color:#1f2937;">Email Highlights</h2>
    <span style="margin-left:auto;background:#2563eb;color:#fff;font-size:12px;font-weight:600;padding:3px 10px;border-radius:20px;">{{UNREAD_COUNT}} unread</span>
  </div>
  <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:16px;margin-bottom:12px;">
    <div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#dc2626;margin-bottom:12px;">⚠️ Action Required</div>
    {{ACTION_ITEMS}}
  </div>
  <div style="background:#f8fafc;border-radius:8px;padding:14px;">
    <div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#475569;margin-bottom:8px;">📬 Other Notable</div>
    <div style="font-size:13px;color:#374151;line-height:1.8;">{{OTHER_EMAILS_LIST}}</div>
  </div>
</div>

<!-- CALENDAR -->
<div style="background:#fff;border-radius:12px;padding:28px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
  <div style="display:flex;align-items:center;margin-bottom:20px;">
    <span style="font-size:20px;margin-right:10px;">📅</span>
    <h2 style="margin:0;font-size:18px;font-weight:700;color:#1f2937;">Calendar</h2>
  </div>
  <div style="background:#f1f5f9;border-radius:8px;padding:16px;margin-bottom:12px;">
    <div style="font-size:13px;font-weight:700;color:#475569;margin-bottom:8px;">Today — {{SHORT_DATE}}</div>
    {{TODAY_EVENTS}}
  </div>
  <div style="background:#f8fafc;border-radius:8px;padding:14px;">
    <div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#475569;margin-bottom:8px;">This Week</div>
    <div style="font-size:13px;color:#374151;line-height:1.7;">{{WEEK_EVENTS}}</div>
  </div>
</div>

<!-- US MARKETS OVERNIGHT -->
<div style="background:#fff;border-radius:12px;padding:28px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
  <div style="display:flex;align-items:center;margin-bottom:20px;">
    <span style="font-size:20px;margin-right:10px;">🇺🇸</span>
    <h2 style="margin:0;font-size:18px;font-weight:700;color:#1f2937;">US Markets Overnight</h2>
    <span style="margin-left:auto;font-size:12px;color:#6b7280;">{{US_CLOSE_DATE}} close</span>
  </div>
  <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
    <thead>
      <tr style="background:#f8fafc;">
        <th style="text-align:left;padding:8px 12px;font-size:12px;color:#6b7280;font-weight:600;border-bottom:1px solid #e5e7eb;">Index</th>
        <th style="text-align:right;padding:8px 12px;font-size:12px;color:#6b7280;font-weight:600;border-bottom:1px solid #e5e7eb;">Close</th>
        <th style="text-align:right;padding:8px 12px;font-size:12px;color:#6b7280;font-weight:600;border-bottom:1px solid #e5e7eb;">Change</th>
      </tr>
    </thead>
    <tbody>
      <tr style="border-bottom:1px solid #f3f4f6;">
        <td style="padding:10px 12px;font-size:14px;font-weight:600;color:#1f2937;">S&amp;P 500</td>
        <td style="padding:10px 12px;font-size:14px;text-align:right;color:#374151;">{{SP500_LEVEL}}</td>
        <td style="padding:10px 12px;font-size:14px;text-align:right;font-weight:700;color:{{SP500_COLOUR}};">{{SP500_PCT}}</td>
      </tr>
      <tr style="border-bottom:1px solid #f3f4f6;">
        <td style="padding:10px 12px;font-size:14px;font-weight:600;color:#1f2937;">Nasdaq</td>
        <td style="padding:10px 12px;font-size:14px;text-align:right;color:#374151;">{{NASDAQ_LEVEL}}</td>
        <td style="padding:10px 12px;font-size:14px;text-align:right;font-weight:700;color:{{NASDAQ_COLOUR}};">{{NASDAQ_PCT}}</td>
      </tr>
      <tr>
        <td style="padding:10px 12px;font-size:14px;font-weight:600;color:#1f2937;">Dow Jones</td>
        <td style="padding:10px 12px;font-size:14px;text-align:right;color:#374151;">{{DOW_LEVEL}}</td>
        <td style="padding:10px 12px;font-size:14px;text-align:right;font-weight:700;color:{{DOW_COLOUR}};">{{DOW_PCT}}</td>
      </tr>
    </tbody>
  </table>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
    <div style="flex:1;min-width:180px;background:#fef9c3;border:1px solid #fde047;border-radius:8px;padding:12px 16px;">
      <div style="font-size:11px;font-weight:700;color:#854d0e;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">VIX — Fear Index</div>
      <div style="font-size:22px;font-weight:700;color:#78350f;">{{VIX}}</div>
      <div style="font-size:12px;color:#92400e;margin-top:2px;">{{VIX_INTERPRETATION}}</div>
    </div>
    <div style="flex:2;min-width:220px;background:#f8fafc;border-radius:8px;padding:12px 16px;">
      <div style="font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Sector Movers</div>
      <div style="font-size:13px;color:#374151;line-height:1.7;">{{SECTOR_MOVERS}}</div>
    </div>
  </div>
  <div style="background:#eff6ff;border-left:4px solid #2563eb;border-radius:8px;padding:14px 16px;">
    <div style="font-size:11px;font-weight:700;color:#1e40af;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Key Themes</div>
    <div style="font-size:13px;color:#1e3a8a;line-height:1.7;">{{MARKET_THEMES}}</div>
  </div>
</div>

<!-- ASX TODAY -->
<div style="background:#fff;border-radius:12px;padding:28px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
  <div style="display:flex;align-items:center;margin-bottom:20px;">
    <span style="font-size:20px;margin-right:10px;">🇦🇺</span>
    <h2 style="margin:0;font-size:18px;font-weight:700;color:#1f2937;">ASX Today</h2>
  </div>
  <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px;">
    <div style="flex:1;min-width:160px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px 16px;">
      <div style="font-size:11px;font-weight:700;color:#166534;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">AUD/USD</div>
      <div style="font-size:22px;font-weight:700;color:{{AUD_COLOUR}};">{{AUD_RATE}}</div>
      <div style="font-size:12px;color:#166534;margin-top:2px;">{{AUD_CONTEXT}}</div>
    </div>
    <div style="flex:1;min-width:160px;background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:12px 16px;">
      <div style="font-size:11px;font-weight:700;color:#0c4a6e;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;">ASX 200 Open</div>
      <div style="font-size:22px;font-weight:700;color:{{ASX_COLOUR}};">{{ASX_OPEN}}</div>
      <div style="font-size:12px;color:#0c4a6e;margin-top:2px;">{{ASX_CONTEXT}}</div>
    </div>
  </div>
  <div style="background:#f8fafc;border-radius:8px;padding:14px;">
    <div style="font-size:11px;font-weight:700;color:#475569;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">ASX Watch</div>
    <div style="font-size:13px;color:#374151;line-height:1.7;">{{ASX_WATCH}}</div>
  </div>
</div>

<!-- PORTFOLIO — HOLDINGS WATCH -->
<div style="background:#fff;border-radius:12px;padding:28px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
  <div style="display:flex;align-items:center;margin-bottom:20px;">
    <span style="font-size:20px;margin-right:10px;">💼</span>
    <h2 style="margin:0;font-size:18px;font-weight:700;color:#1f2937;">Portfolio — Holdings Watch</h2>
  </div>
  {{HOLDINGS_CONTENT}}
</div>

<!-- WEEK AHEAD -->
<div style="background:#fff;border-radius:12px;padding:28px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
  <div style="display:flex;align-items:center;margin-bottom:20px;">
    <span style="font-size:20px;margin-right:10px;">🗓️</span>
    <h2 style="margin:0;font-size:18px;font-weight:700;color:#1f2937;">Week Ahead</h2>
  </div>
  <div style="margin-bottom:16px;">
    <div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#475569;margin-bottom:10px;">🇺🇸 Key US Events</div>
    <table style="width:100%;border-collapse:collapse;">
      <thead>
        <tr style="background:#f8fafc;">
          <th style="text-align:left;padding:8px 12px;font-size:12px;color:#6b7280;font-weight:600;border-bottom:1px solid #e5e7eb;">Date</th>
          <th style="text-align:left;padding:8px 12px;font-size:12px;color:#6b7280;font-weight:600;border-bottom:1px solid #e5e7eb;">Event</th>
          <th style="text-align:left;padding:8px 12px;font-size:12px;color:#6b7280;font-weight:600;border-bottom:1px solid #e5e7eb;">Why It Matters</th>
        </tr>
      </thead>
      <tbody>{{WEEK_EVENTS_TABLE}}</tbody>
    </table>
  </div>
  <div style="background:#f8fafc;border-radius:8px;padding:14px;">
    <div style="font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;color:#475569;margin-bottom:8px;">📋 Holdings Earnings / Events</div>
    <div style="font-size:13px;color:#374151;line-height:1.8;">{{HOLDINGS_EARNINGS}}</div>
  </div>
</div>

<!-- FOOTER -->
<div style="background:#1a1a2e;border-radius:12px;padding:18px 28px;text-align:center;">
  <p style="margin:0 0 4px;font-size:12px;color:#64748b;">Generated at 7:00 AM · Data sourced from web search · Not financial advice</p>
  <p style="margin:0;font-size:12px;color:#475569;">ryanhogan284@gmail.com</p>
</div>

</div>
</body>
</html>"""

# ---------------------------------------------------------------------------
# Tavily search queries
# ---------------------------------------------------------------------------

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
# Token management
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
        # Write back updated token
        updated = json.loads(token_path.read_text())
        updated['token'] = creds.token
        token_path.write_text(json.dumps(updated))
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
        date = msg.get('date', '')
        snippet = msg.get('snippet', '')
        lines.append(f'{i}. From: {sender}')
        lines.append(f'   Subject: {subject}')
        if date:
            lines.append(f'   Date: {date}')
        if snippet:
            lines.append(f'   Preview: {snippet}')
        lines.append('')
    return '\n'.join(lines).rstrip()


def format_calendar(events: list) -> str:
    """Format calendar events as structured text for the LLM prompt."""
    if not events:
        return '(no upcoming events)'
    lines = []
    for event in events:
        summary = event.get('summary', '(no title)')
        start = event.get('start', {})
        start_str = start.get('dateTime', start.get('date', ''))
        end = event.get('end', {})
        end_str = end.get('dateTime', end.get('date', ''))
        location = event.get('location', '')
        description = event.get('description', '')

        lines.append(f'- {summary}')
        if start_str:
            lines.append(f'  Start: {start_str}')
        if end_str and end_str != start_str:
            lines.append(f'  End: {end_str}')
        if location:
            lines.append(f'  Location: {location}')
        if description:
            # Truncate long descriptions
            desc_short = description[:200].replace('\n', ' ')
            if len(description) > 200:
                desc_short += '...'
            lines.append(f'  Notes: {desc_short}')
    return '\n'.join(lines)


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
                url = item.get('url', '')
                content = item.get('content', '')
                if title:
                    lines.append(f'  • {title}')
                if content:
                    # Truncate long content snippets
                    content_short = content[:300].replace('\n', ' ')
                    if len(content) > 300:
                        content_short += '...'
                    lines.append(f'    {content_short}')
                if url:
                    lines.append(f'    {url}')
        lines.append('')
    return '\n'.join(lines).rstrip()


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------


def fetch_gmail(creds, yesterday_date: str) -> dict:
    """Fetch recent Gmail messages (inbox, unread, starred)."""
    from googleapiclient.discovery import build

    service = build('gmail', 'v1', credentials=creds)
    queries = [
        f'after:{yesterday_date} in:inbox',
        'is:unread newer_than:2d',
        'is:starred newer_than:7d',
    ]

    seen_ids = set()
    message_ids = []
    for query in queries:
        try:
            resp = service.users().messages().list(
                userId='me', q=query, maxResults=10
            ).execute()
            for msg in resp.get('messages', []):
                mid = msg['id']
                if mid not in seen_ids:
                    seen_ids.add(mid)
                    message_ids.append(mid)
        except Exception as e:
            print(f'Gmail query "{query}" failed: {e}', file=sys.stderr)

    messages = []
    unread_count = 0
    for mid in message_ids[:8]:
        try:
            msg = service.users().messages().get(
                userId='me', id=mid, format='full'
            ).execute()

            headers = {
                h['name'].lower(): h['value']
                for h in msg.get('payload', {}).get('headers', [])
            }
            subject = headers.get('subject', '(no subject)')
            sender = headers.get('from', '(unknown)')
            date = headers.get('date', '')
            snippet = msg.get('snippet', '')

            labels = msg.get('labelIds', [])
            if 'UNREAD' in labels:
                unread_count += 1

            messages.append({
                'id': mid,
                'subject': subject,
                'from': sender,
                'date': date,
                'snippet': snippet,
                'labels': labels,
            })
        except Exception as e:
            print(f'Failed to fetch message {mid}: {e}', file=sys.stderr)

    return {'messages': messages, 'unread_count': unread_count}


def fetch_calendar(creds) -> list:
    """Fetch upcoming calendar events for the next 7 days."""
    from googleapiclient.discovery import build

    service = build('calendar', 'v3', credentials=creds)
    now = datetime.utcnow().isoformat() + 'Z'
    end = (datetime.utcnow() + timedelta(days=7)).isoformat() + 'Z'
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
# Qwen composition via Ollama
# ---------------------------------------------------------------------------


def compose_brief(gmail_data: dict, calendar_data: list, search_results: dict, today_str: str) -> str:
    """Send all data to Qwen3.5 via Ollama and return the completed HTML."""
    import httpx

    prompt = f"""You are generating a personalised morning brief email for Ryan Hogan.
Today is {today_str}.

Fill in the HTML template below by replacing EVERY {{{{PLACEHOLDER}}}} with real content from the data provided.
Do NOT change any HTML structure, CSS, inline styles, or class names.
Return ONLY the completed HTML — no markdown, no explanation.

=== GMAIL DATA ===
Unread count: {gmail_data['unread_count']}
Messages:
{format_messages(gmail_data['messages'])}

=== CALENDAR DATA ===
{format_calendar(calendar_data)}

=== MARKET & NEWS DATA ===
{format_search_results(search_results)}

=== HTML TEMPLATE ===
{HTML_TEMPLATE}
"""

    ollama_url = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    model = os.getenv('OLLAMA_MODEL', 'qwen3.5:latest')

    response = httpx.post(
        f'{ollama_url}/api/chat',
        json={
            'model': model,
            'messages': [{'role': 'user', 'content': prompt}],
            'stream': False,
        },
        timeout=300.0,  # 5 minute timeout for large generation
    )
    response.raise_for_status()
    return response.json()['message']['content']


# ---------------------------------------------------------------------------
# Gmail draft creation
# ---------------------------------------------------------------------------


def create_draft(creds, html_content: str, today_str: str) -> str:
    """Create a Gmail draft with the morning brief HTML and return the draft ID."""
    from googleapiclient.discovery import build

    service = build('gmail', 'v1', credentials=creds)
    message = MIMEText(html_content, 'html')
    message['to'] = 'ryanhogan284@gmail.com'
    message['subject'] = f'📊 Morning Brief — {today_str}'
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId='me',
        body={'message': {'raw': raw}},
    ).execute()
    return draft['id']


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
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix='.html')
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
    yesterday_date = (today - timedelta(days=1)).strftime('%Y/%m/%d')

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Write "running" status immediately so the UI can reflect progress
    write_json(DATA_DIR / 'brief_status.json', {
        'status': 'running',
        'generated_at': datetime.utcnow().isoformat(),
        'draft_id': None,
        'error': None,
        'gmail_connected': True,
    })

    creds = load_credentials()
    tavily_client = TavilyClient(api_key=os.getenv('TAVILY_API_KEY', ''))

    # Fetch all data in parallel
    with ThreadPoolExecutor(max_workers=8) as executor:
        gmail_future = executor.submit(fetch_gmail, creds, yesterday_date)
        calendar_future = executor.submit(fetch_calendar, creds)
        search_futures = {
            q: executor.submit(search_tavily, tavily_client, q)
            for q in TAVILY_QUERIES
        }

    gmail_data = gmail_future.result()
    calendar_data = calendar_future.result()
    search_results = {q: f.result() for q, f in search_futures.items()}

    # Compose with Qwen via Ollama
    print('Composing brief with Qwen3.5…', flush=True)
    html_content = compose_brief(gmail_data, calendar_data, search_results, today_str)

    # Create Gmail draft
    draft_id = create_draft(creds, html_content, today_str)

    # Save preview
    write_file(DATA_DIR / 'morning_brief_preview.html', html_content)

    # Write success status
    write_json(DATA_DIR / 'brief_status.json', {
        'status': 'success',
        'generated_at': datetime.utcnow().isoformat(),
        'draft_id': draft_id,
        'error': None,
        'gmail_connected': True,
    })

    print(f'Morning brief generated. Draft ID: {draft_id}')


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        write_json(DATA_DIR / 'brief_status.json', {
            'status': 'error',
            'generated_at': datetime.utcnow().isoformat(),
            'draft_id': None,
            'error': str(e),
            'gmail_connected': True,
        })
        traceback.print_exc()
        sys.exit(1)
