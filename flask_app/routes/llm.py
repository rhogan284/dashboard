import base64
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path

import httpx
from flask import Blueprint, Response, current_app, request, stream_with_context

llm_bp = Blueprint('llm', __name__)

OLLAMA_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
DEFAULT_MODEL = os.getenv('OLLAMA_MODEL', 'gemma4:26b')


def _strip_thinking(content: str) -> str:
    """Strip model thinking/reasoning blocks from response content.

    Handles both Qwen3-style <think>...</think> and Gemma 4-style
    <|channel>thought\\n...<channel|> blocks.
    """
    # Gemma 4: <|channel>thought\n...<channel|>
    content = re.sub(r'<\|channel>thought\n.*?<channel\|>', '', content, flags=re.DOTALL)
    # Qwen3 / legacy: <think>...</think>
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    return content.strip()

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'search_web',
            'description': (
                'Search the web for current information using Tavily. '
                'Use this when asked to look something up, find news, or get live data.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {'type': 'string', 'description': 'The search query'},
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'list_calendar_events',
            'description': "List the user's upcoming Google Calendar events.",
            'parameters': {
                'type': 'object',
                'properties': {
                    'days_ahead': {
                        'type': 'integer',
                        'description': 'Number of days ahead to fetch (default 7)',
                    },
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'create_calendar_event',
            'description': "Create a new event in the user's Google Calendar.",
            'parameters': {
                'type': 'object',
                'properties': {
                    'summary': {'type': 'string', 'description': 'Event title'},
                    'start_datetime': {
                        'type': 'string',
                        'description': (
                            'Start date/time in ISO 8601 with UTC offset '
                            '(e.g. 2026-04-01T10:00:00+10:00)'
                        ),
                    },
                    'end_datetime': {
                        'type': 'string',
                        'description': 'End date/time in ISO 8601 with UTC offset',
                    },
                    'description': {
                        'type': 'string',
                        'description': 'Optional event description',
                    },
                },
                'required': ['summary', 'start_datetime', 'end_datetime'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'delete_calendar_event',
            'description': (
                "Delete an event from the user's Google Calendar. "
                'Use list_calendar_events first to find the event ID.'
            ),
            'parameters': {
                'type': 'object',
                'properties': {
                    'event_id': {'type': 'string', 'description': 'The Google Calendar event ID'},
                },
                'required': ['event_id'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'create_gmail_draft',
            'description': "Save a draft email to the user's Gmail drafts folder.",
            'parameters': {
                'type': 'object',
                'properties': {
                    'to': {'type': 'string', 'description': 'Recipient email address'},
                    'subject': {'type': 'string', 'description': 'Email subject line'},
                    'body': {'type': 'string', 'description': 'Email body (plain text)'},
                },
                'required': ['to', 'subject', 'body'],
            },
        },
    },
]

# Human-readable status labels shown in the UI while a tool runs
_TOOL_STATUS = {
    'search_web':            lambda a: f"Searching: \"{a.get('query', '')}\"",
    'list_calendar_events':  lambda a: 'Checking calendar…',
    'create_calendar_event': lambda a: f"Creating event: \"{a.get('summary', '')}\"",
    'delete_calendar_event': lambda a: 'Deleting event…',
    'create_gmail_draft':    lambda a: f"Drafting email to {a.get('to', '')}…",
}

# ---------------------------------------------------------------------------
# Google credentials helper
# ---------------------------------------------------------------------------


_CALENDAR_WRITE_SCOPE = 'https://www.googleapis.com/auth/calendar'


def _load_google_creds(require_calendar_write: bool = False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_path = Path(current_app.config['DATA_DIR']) / 'brief_token.json'
    if not token_path.exists():
        raise FileNotFoundError(
            'Google credentials not found — connect Gmail in the Morning Brief tab first.'
        )

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
        fd, tmp = tempfile.mkstemp(dir=token_path.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f)
            os.replace(tmp, token_path)
        except Exception:
            os.unlink(tmp)
            raise

    if require_calendar_write:
        scopes = creds.scopes or []
        has_write = any(_CALENDAR_WRITE_SCOPE in s for s in scopes)
        if not has_write:
            raise PermissionError(
                'Calendar write access not granted. '
            )

    return creds

# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def _search_web(args: dict) -> str:
    from tavily import TavilyClient
    api_key = os.getenv('TAVILY_API_KEY', '')
    if not api_key:
        return 'Error: TAVILY_API_KEY not configured.'
    try:
        results = TavilyClient(api_key=api_key).search(args.get('query', ''), max_results=5)
        lines = []
        for item in results.get('results', []):
            lines.append(f"• {item.get('title', '')}")
            content = item.get('content', '')[:300]
            if content:
                lines.append(f"  {content}")
            url = item.get('url', '')
            if url:
                lines.append(f"  {url}")
            lines.append('')
        return '\n'.join(lines).strip() or 'No results found.'
    except Exception as exc:
        return f'Search error: {exc}'


def _list_calendar_events(args: dict) -> str:
    try:
        from googleapiclient.discovery import build
        creds = _load_google_creds()
        service = build('calendar', 'v3', credentials=creds)
        days_ahead = int(args.get('days_ahead', 7))
        now = datetime.now(timezone.utc)
        result = service.events().list(
            calendarId='primary',
            timeMin=now.isoformat(),
            timeMax=(now + timedelta(days=days_ahead)).isoformat(),
            singleEvents=True,
            orderBy='startTime',
            maxResults=20,
        ).execute()
        events = result.get('items', [])
        if not events:
            return 'No upcoming events.'
        lines = []
        for e in events:
            start = e.get('start', {})
            start_str = start.get('dateTime', start.get('date', ''))
            lines.append(f"ID: {e['id']}")
            lines.append(f"  {e.get('summary', '(no title)')} — {start_str}")
        return '\n'.join(lines)
    except Exception as exc:
        return f'Error listing events: {exc}'


def _create_calendar_event(args: dict) -> str:
    try:
        from googleapiclient.discovery import build
        creds = _load_google_creds(require_calendar_write=True)
        service = build('calendar', 'v3', credentials=creds)
        body = {
            'summary': args['summary'],
            'start': {'dateTime': args['start_datetime']},
            'end': {'dateTime': args['end_datetime']},
        }
        if args.get('description'):
            body['description'] = args['description']
        event = service.events().insert(calendarId='primary', body=body).execute()
        return f"Created: \"{event['summary']}\" (ID: {event['id']})"
    except Exception as exc:
        return f'Error creating event: {exc}'


def _delete_calendar_event(args: dict) -> str:
    try:
        from googleapiclient.discovery import build
        creds = _load_google_creds(require_calendar_write=True)
        service = build('calendar', 'v3', credentials=creds)
        service.events().delete(calendarId='primary', eventId=args['event_id']).execute()
        return f"Deleted event {args['event_id']}."
    except Exception as exc:
        return f'Error deleting event: {exc}'


def _create_gmail_draft(args: dict) -> str:
    try:
        from googleapiclient.discovery import build
        creds = _load_google_creds()
        service = build('gmail', 'v1', credentials=creds)
        msg = MIMEText(args['body'])
        msg['to'] = args['to']
        msg['subject'] = args['subject']
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        draft = service.users().drafts().create(
            userId='me', body={'message': {'raw': raw}}
        ).execute()
        return f"Draft saved (ID: {draft['id']}) — To: {args['to']}, Subject: \"{args['subject']}\""
    except Exception as exc:
        return f'Error creating draft: {exc}'


_TOOL_HANDLERS = {
    'search_web':            _search_web,
    'list_calendar_events':  _list_calendar_events,
    'create_calendar_event': _create_calendar_event,
    'delete_calendar_event': _delete_calendar_event,
    'create_gmail_draft':    _create_gmail_draft,
}

# ---------------------------------------------------------------------------
# Chat route
# ---------------------------------------------------------------------------


@llm_bp.route('/api/chat', methods=['POST'])
def chat() -> Response:
    data = request.get_json(silent=True) or {}
    messages = data.get('messages')
    if not messages or not isinstance(messages, list):
        return Response('{"error": "messages required"}', status=400, mimetype='application/json')
    think = bool(data.get('think', False))

    today = datetime.now().strftime('%A, %B %-d, %Y')
    # Include local UTC offset so the model can use it for calendar datetimes
    utc_offset = datetime.now().astimezone().strftime('%z')
    offset_str = f"{utc_offset[:3]}:{utc_offset[3:]}"  # e.g. +10:00

    system_msg = {
        'role': 'system',
        'content': (
            f"You are a helpful personal assistant. Today is {today}. "
            f"The user's local UTC offset is {offset_str} — use this when creating calendar events. "
            "You have access to the user's Google Calendar and Gmail via tools. "
            "Use tools whenever the user asks you to search the web, check/create/delete calendar events, "
            "or draft an email. Be concise and always confirm what action was taken."
        ),
    }

    def generate():
        loop_messages = [system_msg] + list(messages)
        try:
            while True:
                resp = httpx.post(
                    f'{OLLAMA_URL}/api/chat',
                    json={
                        'model': DEFAULT_MODEL,
                        'messages': loop_messages,
                        'tools': TOOLS,
                        'stream': False,
                        'think': think,
                        'options': {
                            'num_ctx': 8192,
                            'num_predict': 4096 if think else -1,
                        },
                    },
                    timeout=300.0 if think else 120.0,
                )
                resp.raise_for_status()

                msg = resp.json()['message']
                tool_calls = msg.get('tool_calls') or []

                if not tool_calls:
                    content = _strip_thinking(msg.get('content', ''))
                    yield (json.dumps({'message': {'content': content}}) + '\n').encode()
                    break

                # Append the assistant's tool-call message to history
                loop_messages.append(msg)

                for tc in tool_calls:
                    fn = tc.get('function', {})
                    name = fn.get('name', '')
                    args = fn.get('arguments', {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}

                    # Stream status so the UI can show what's happening
                    label = _TOOL_STATUS.get(name, lambda a: f'Using {name}…')(args)
                    yield (json.dumps({'status': label}) + '\n').encode()

                    handler = _TOOL_HANDLERS.get(name)
                    result = handler(args) if handler else f'Unknown tool: {name}'

                    loop_messages.append({'role': 'tool', 'content': result})

        except httpx.ConnectError:
            yield b'{"error": "Cannot connect to Ollama. Is it running?"}\n'
        except httpx.HTTPStatusError as exc:
            yield (json.dumps({'error': f'Ollama error: {exc.response.status_code}'}) + '\n').encode()
        except Exception as exc:
            yield (json.dumps({'error': str(exc)}) + '\n').encode()

    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')
