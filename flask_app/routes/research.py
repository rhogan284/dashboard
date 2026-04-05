import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
# Response, stream_with_context, jsonify, request are used by route handlers added in later tasks
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from routes.llm import _search_web

research_bp = Blueprint('research', __name__)

OLLAMA_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
DEFAULT_MODEL = os.getenv('OLLAMA_MODEL', 'qwen3.5:latest')
PORTFOLIO_DB_PATH = os.getenv(
    'PORTFOLIO_DB_PATH',
    '/Users/ryanhogan/Desktop/Coding Work/portfolio_app/portfolio.db',
)

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

@contextmanager
def _get_db():
    db_path = Path(current_app.config['DATA_DIR']) / 'research.db'
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _init_db():
    db_path = Path(current_app.config['DATA_DIR']) / 'research.db'
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS research_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL DEFAULT 'New session',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                auto_summary TEXT
            );
            CREATE TABLE IF NOT EXISTS research_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  INTEGER NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS research_pinboard (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                content     TEXT NOT NULL,
                tags        TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_research_messages_session
                ON research_messages(session_id);
        """)
    finally:
        conn.close()


@research_bp.record_once
def _on_registered(state):
    with state.app.app_context():
        _init_db()


# ---------------------------------------------------------------------------
# Session routes
# ---------------------------------------------------------------------------

@research_bp.route('/api/research/sessions', methods=['GET'])
def list_sessions():
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM research_sessions ORDER BY updated_at DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@research_bp.route('/api/research/sessions', methods=['POST'])
def create_session():
    now = datetime.now(timezone.utc).isoformat()
    with _get_db() as conn:
        cur = conn.execute(
            "INSERT INTO research_sessions (title, created_at, updated_at) VALUES (?, ?, ?)",
            ('New session', now, now),
        )
        conn.commit()
        session_id = cur.lastrowid
    return jsonify({'id': session_id})


@research_bp.route('/api/research/sessions/<int:session_id>', methods=['GET'])
def get_session(session_id: int):
    with _get_db() as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at, auto_summary FROM research_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return jsonify({'error': 'Session not found'}), 404
        messages = conn.execute(
            "SELECT role, content, created_at FROM research_messages WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
    return jsonify({**dict(row), 'messages': [dict(m) for m in messages]})


@research_bp.route('/api/research/sessions/<int:session_id>', methods=['PATCH'])
def update_session(session_id: int):
    data = request.get_json(silent=True) or {}
    title = str(data.get('title', '')).strip()
    if not title:
        return jsonify({'error': 'title required'}), 400
    with _get_db() as conn:
        conn.execute(
            "UPDATE research_sessions SET title = ? WHERE id = ?",
            (title, session_id),
        )
        conn.commit()
    return jsonify({'ok': True})


@research_bp.route('/api/research/sessions/<int:session_id>', methods=['DELETE'])
def delete_session(session_id: int):
    with _get_db() as conn:
        conn.execute("DELETE FROM research_sessions WHERE id = ?", (session_id,))
        conn.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Pinboard routes
# ---------------------------------------------------------------------------

@research_bp.route('/api/research/pinboard', methods=['GET'])
def list_pinboard():
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, content, tags, created_at, updated_at FROM research_pinboard ORDER BY created_at DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@research_bp.route('/api/research/pinboard', methods=['POST'])
def add_pinboard_note():
    data = request.get_json(silent=True) or {}
    title = str(data.get('title', '')).strip()
    content = str(data.get('content', '')).strip()
    tags = str(data.get('tags', '')).strip()
    if not title:
        return jsonify({'error': 'title required'}), 400
    now = datetime.now(timezone.utc).isoformat()
    with _get_db() as conn:
        cur = conn.execute(
            "INSERT INTO research_pinboard (title, content, tags, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (title, content, tags, now, now),
        )
        conn.commit()
    return jsonify({'id': cur.lastrowid})


@research_bp.route('/api/research/pinboard/<int:note_id>', methods=['PATCH'])
def update_pinboard_note(note_id: int):
    data = request.get_json(silent=True) or {}
    now = datetime.now(timezone.utc).isoformat()
    fields = []
    values = []
    for col in ('title', 'content', 'tags'):
        if col in data:
            fields.append(f"{col} = ?")
            values.append(str(data[col]))
    if not fields:
        return jsonify({'error': 'nothing to update'}), 400
    fields.append("updated_at = ?")
    values.append(now)
    values.append(note_id)
    with _get_db() as conn:
        conn.execute(f"UPDATE research_pinboard SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
    return jsonify({'ok': True})


@research_bp.route('/api/research/pinboard/<int:note_id>', methods=['DELETE'])
def delete_pinboard_note(note_id: int):
    with _get_db() as conn:
        conn.execute("DELETE FROM research_pinboard WHERE id = ?", (note_id,))
        conn.commit()
    return jsonify({'ok': True})


def _save_message(session_id: int, role: str, content: str):
    now = datetime.now(timezone.utc).isoformat()
    with _get_db() as conn:
        conn.execute(
            "INSERT INTO research_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, now),
        )
        conn.commit()


def _touch_session(session_id: int):
    now = datetime.now(timezone.utc).isoformat()
    with _get_db() as conn:
        conn.execute(
            "UPDATE research_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

RESEARCH_TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'search_web',
            'description': (
                'Search the web for current information using Tavily. '
                'Use for general research, company news, and macroeconomic data.'
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
            'name': 'get_stock_data',
            'description': 'Get stock price, fundamentals, or price history for a ticker via yfinance.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'ticker': {
                        'type': 'string',
                        'description': 'Ticker symbol, e.g. AAPL or ASX:GOLD',
                    },
                    'info_type': {
                        'type': 'string',
                        'enum': ['price', 'fundamentals', 'history'],
                        'description': 'Type of data: current price, fundamental metrics, or OHLCV history',
                    },
                    'period': {
                        'type': 'string',
                        'description': 'For history only — period string like 1mo, 3mo, 6mo, 1y',
                    },
                },
                'required': ['ticker', 'info_type'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_financial_news',
            'description': 'Search for financial and market news using Tavily, scoped to news sources.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': 'Search query, e.g. "CRDO earnings outlook 2026"',
                    },
                    'tickers': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'Optional list of tickers appended to the query for specificity',
                    },
                },
                'required': ['query'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'query_portfolio',
            'description': "Read-only access to the user's portfolio database.",
            'parameters': {
                'type': 'object',
                'properties': {
                    'operation': {
                        'type': 'string',
                        'enum': ['holdings', 'trades', 'performance'],
                        'description': 'holdings = all positions; trades = last 50 by date; performance = monthly snapshots',
                    },
                },
                'required': ['operation'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'read_local_file',
            'description': 'Read a local PDF, CSV, or XLSX file and return its text content.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'path': {
                        'type': 'string',
                        'description': 'Absolute path to the file on disk',
                    },
                    'sheet': {
                        'type': 'string',
                        'description': 'For .xlsx files: sheet name to read (default: first sheet)',
                    },
                },
                'required': ['path'],
            },
        },
    },
]

_TOOL_STATUS = {
    'search_web':         lambda a: f"Searching: \"{a.get('query', '')}\"",
    'get_stock_data':     lambda a: f"Getting {a.get('info_type', 'data')} for {a.get('ticker', '')}…",
    'get_financial_news': lambda a: f"Finding news: \"{a.get('query', '')}\"",
    'query_portfolio':    lambda a: f"Querying portfolio ({a.get('operation', '')})…",
    'read_local_file':    lambda a: f"Reading {Path(a.get('path', '')).name}…",
}

# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


def _get_stock_data(args: dict) -> str:
    import yfinance as yf
    ticker = args.get('ticker', '')
    info_type = args.get('info_type', 'price')
    period = args.get('period', '1mo')
    try:
        t = yf.Ticker(ticker)
        if info_type == 'price':
            info = t.info
            price = info.get('currentPrice') or info.get('regularMarketPrice', 'N/A')
            currency = info.get('currency', '')
            prev_close = info.get('previousClose', 'N/A')
            day_high = info.get('dayHigh', 'N/A')
            day_low = info.get('dayLow', 'N/A')
            return (
                f"{ticker}: {price} {currency}\n"
                f"Prev Close: {prev_close} | Day High: {day_high} | Day Low: {day_low}"
            )
        elif info_type == 'fundamentals':
            info = t.info
            fields = {
                'Market Cap': info.get('marketCap'),
                'P/E (TTM)': info.get('trailingPE'),
                'P/E (Fwd)': info.get('forwardPE'),
                'EPS (TTM)': info.get('trailingEps'),
                'Revenue': info.get('totalRevenue'),
                'Gross Margin': info.get('grossMargins'),
                'Debt/Equity': info.get('debtToEquity'),
                '52W High': info.get('fiftyTwoWeekHigh'),
                '52W Low': info.get('fiftyTwoWeekLow'),
                'Sector': info.get('sector'),
                'Industry': info.get('industry'),
            }
            lines = [f"{k}: {v}" for k, v in fields.items() if v is not None]
            return '\n'.join(lines) or 'No fundamentals data available.'
        elif info_type == 'history':
            hist = t.history(period=period)
            if hist.empty:
                return 'No history data available.'
            lines = []
            for date, row in hist.tail(20).iterrows():
                lines.append(
                    f"{date.date()}: Open={row['Open']:.2f} "
                    f"Close={row['Close']:.2f} "
                    f"Vol={int(row['Volume'])}"
                )
            return '\n'.join(lines)
        else:
            return f"Unknown info_type: {info_type}"
    except Exception as exc:
        return f"Stock data error for {ticker}: {exc}"


def _get_financial_news(args: dict) -> str:
    from tavily import TavilyClient
    api_key = os.getenv('TAVILY_API_KEY', '')
    if not api_key:
        return 'Error: TAVILY_API_KEY not configured.'
    query = args.get('query', '')
    tickers = args.get('tickers', [])
    if tickers:
        query = query + ' ' + ' '.join(tickers)
    try:
        results = TavilyClient(api_key=api_key).search(query, max_results=5, topic='news')
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
        return '\n'.join(lines).strip() or 'No news found.'
    except Exception as exc:
        return f'News search error: {exc}'


def _query_portfolio(args: dict) -> str:
    operation = args.get('operation', 'holdings')
    try:
        conn = sqlite3.connect(PORTFOLIO_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        try:
            if operation == 'holdings':
                cur.execute(
                    "SELECT ticker, platform, units, avg_cost, sleeve FROM holdings ORDER BY ticker"
                )
                rows = cur.fetchall()
                if not rows:
                    return 'No holdings found.'
                header = 'Ticker | Platform | Units | Avg Cost | Sleeve'
                lines = [header] + [
                    f"{r['ticker']} | {r['platform']} | {r['units']} | {r['avg_cost']} | {r['sleeve']}"
                    for r in rows
                ]
                return '\n'.join(lines)
            elif operation == 'trades':
                cur.execute("SELECT * FROM trades ORDER BY date DESC LIMIT 50")
                rows = cur.fetchall()
                if not rows:
                    return 'No trades found.'
                keys = rows[0].keys()
                lines = [' | '.join(keys)] + [
                    ' | '.join(str(r[k]) for k in keys) for r in rows
                ]
                return '\n'.join(lines)
            elif operation == 'performance':
                cur.execute("SELECT * FROM monthly_tracker ORDER BY date DESC LIMIT 24")
                rows = cur.fetchall()
                if not rows:
                    return 'No performance data found.'
                keys = rows[0].keys()
                lines = [' | '.join(keys)] + [
                    ' | '.join(str(r[k]) for k in keys) for r in rows
                ]
                return '\n'.join(lines)
            else:
                return f"Unknown operation: {operation}"
        finally:
            conn.close()
    except Exception as exc:
        return f'Portfolio query error: {exc}'


_MAX_FILE_CHARS = 24000  # ~6000 tokens


def _read_local_file(args: dict) -> str:
    path = args.get('path', '')
    sheet = args.get('sheet')
    p = Path(path)
    if not p.exists():
        return f"File not found: {path}"
    suffix = p.suffix.lower()
    try:
        if suffix == '.pdf':
            import pdfplumber
            with pdfplumber.open(str(p)) as pdf:
                text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
        elif suffix == '.csv':
            import pandas as pd
            df = pd.read_csv(str(p))
            text = df.to_string(index=False)
        elif suffix == '.xlsx':
            import pandas as pd
            df = pd.read_excel(str(p), sheet_name=sheet or 0)
            text = df.to_string(index=False)
        else:
            return f"Unsupported file type: {suffix}. Supported: .pdf, .csv, .xlsx"
        return text[:_MAX_FILE_CHARS] if len(text) > _MAX_FILE_CHARS else text
    except Exception as exc:
        return f"Error reading {path}: {exc}"


_RESEARCH_TOOL_HANDLERS = {
    'search_web':         _search_web,
    'get_stock_data':     _get_stock_data,
    'get_financial_news': _get_financial_news,
    'query_portfolio':    _query_portfolio,
    'read_local_file':    _read_local_file,
}

# ---------------------------------------------------------------------------
# Market context helper (free yfinance data prepended to review prompt)
# ---------------------------------------------------------------------------

def _build_market_context() -> str:
    import yfinance as yf
    indices = [
        ('S&P 500',         '^GSPC'),
        ('ASX 200',         '^AXJO'),
        ('VIX',             '^VIX'),
        ('USD Index (DXY)', 'DX-Y.NYB'),
    ]
    lines = ['## Market Context (at time of review)', '']
    for label, symbol in indices:
        try:
            info = yf.Ticker(symbol).info
            price = info.get('regularMarketPrice') or info.get('currentPrice', 'N/A')
            change_pct = info.get('regularMarketChangePercent')
            if change_pct is not None:
                lines.append(f'- **{label}**: {price} ({change_pct:+.2f}%)')
            else:
                lines.append(f'- **{label}**: {price}')
        except Exception:
            lines.append(f'- **{label}**: unavailable')
    lines.append('')
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Chat route
# ---------------------------------------------------------------------------

@research_bp.route('/api/research/chat', methods=['POST'])
def chat() -> Response:
    data = request.get_json(silent=True) or {}
    session_id = data.get('session_id')
    messages = data.get('messages')
    if not session_id or not messages or not isinstance(messages, list):
        return Response(
            '{"error": "session_id and messages required"}',
            status=400,
            mimetype='application/json',
        )
    think = bool(data.get('think', False))

    today = datetime.now().strftime('%A, %B %-d, %Y')
    utc_offset = datetime.now().astimezone().strftime('%z')
    offset_str = f"{utc_offset[:3]}:{utc_offset[3:]}"

    # Build memory context
    with _get_db() as conn:
        pinboard_rows = conn.execute(
            "SELECT title, content, tags FROM research_pinboard ORDER BY created_at DESC"
        ).fetchall()
        summary_rows = conn.execute(
            "SELECT auto_summary FROM research_sessions "
            "WHERE auto_summary IS NOT NULL AND auto_summary != '' "
            "AND id != ? "
            "ORDER BY updated_at DESC LIMIT 5",
            (session_id,),
        ).fetchall()

    pinboard_text = '\n\n'.join(
        f"**{r['title']}** [{r['tags']}]\n{r['content']}" for r in pinboard_rows
    ) if pinboard_rows else '(no notes yet)'

    summaries_text = '\n\n'.join(
        f"- {r['auto_summary']}" for r in summary_rows
    ) if summary_rows else '(no past sessions)'

    portfolio_holdings = _query_portfolio({'operation': 'holdings'})

    system_content = (
        f"You are an investment research assistant for Ryan Hogan.\n"
        f"Today is {today}. Your local UTC offset is {offset_str}.\n"
        "You have access to tools for web search, financial data, news, portfolio data, and local files.\n"
        "Be concise, cite your sources, and flag uncertainty clearly.\n\n"
        f"=== Portfolio Holdings ===\n{portfolio_holdings}\n\n"
        f"=== Investment Notes & Theses ===\n{pinboard_text}\n\n"
        f"=== Past Research Summaries ===\n{summaries_text}"
    )
    system_msg = {'role': 'system', 'content': system_content}

    def generate():
        loop_messages = [system_msg] + list(messages)

        # Persist the incoming user message (last item)
        last = messages[-1]
        if last.get('role') == 'user':
            _save_message(session_id, 'user', last['content'])

        try:
            while True:
                resp = httpx.post(
                    f'{OLLAMA_URL}/api/chat',
                    json={
                        'model': DEFAULT_MODEL,
                        'messages': loop_messages,
                        'tools': RESEARCH_TOOLS,
                        'stream': False,
                        'think': think,
                        'options': {
                            'num_ctx': 16384,
                            'num_predict': 4096 if think else -1,
                        },
                    },
                    timeout=300.0 if think else 120.0,
                )
                resp.raise_for_status()

                msg = resp.json()['message']
                tool_calls = msg.get('tool_calls') or []

                if not tool_calls:
                    content = msg.get('content', '')
                    if '<think>' in content:
                        content = content.split('</think>', 1)[-1].strip()
                    _save_message(session_id, 'assistant', content)
                    _touch_session(session_id)
                    yield (json.dumps({'message': {'content': content}}) + '\n').encode()
                    break

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

                    label = _TOOL_STATUS.get(name, lambda a: f'Using {name}…')(args)
                    yield (json.dumps({'status': label}) + '\n').encode()

                    handler = _RESEARCH_TOOL_HANDLERS.get(name)
                    result = handler(args) if handler else f'Unknown tool: {name}'

                    _save_message(session_id, 'tool', result)
                    loop_messages.append({'role': 'tool', 'content': result})

        except httpx.ConnectError:
            yield b'{"error": "Cannot connect to Ollama. Is it running?"}\n'
        except httpx.HTTPStatusError as exc:
            yield (json.dumps({'error': f'Ollama error: {exc.response.status_code}'}) + '\n').encode()
        except Exception as exc:
            yield (json.dumps({'error': str(exc)}) + '\n').encode()

    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')


# ---------------------------------------------------------------------------
# Portfolio review route
# ---------------------------------------------------------------------------

PORTFOLIO_APP_URL = os.getenv('PORTFOLIO_APP_URL', 'http://localhost:8000')


@research_bp.route('/api/research/review', methods=['POST'])
def portfolio_review() -> Response:
    # 1. Fetch review markdown from portfolio app
    try:
        r = httpx.get(f'{PORTFOLIO_APP_URL}/api/review/markdown', timeout=15.0)
        r.raise_for_status()
        review_markdown = r.json()['markdown']
    except Exception as exc:
        return Response(
            json.dumps({'error': f'Portfolio app not reachable — is it running on port 8000? ({exc})'}),
            status=503,
            mimetype='application/json',
        )

    # 2. Prepend free market context (yfinance)
    try:
        market_context = _build_market_context()
    except Exception:
        market_context = ''

    full_prompt = (market_context + '\n' + review_markdown).strip() if market_context else review_markdown

    # 3. Create a new session titled "Portfolio Review"
    now = datetime.now(timezone.utc).isoformat()
    with _get_db() as conn:
        cur = conn.execute(
            "INSERT INTO research_sessions (title, created_at, updated_at) VALUES (?, ?, ?)",
            ('Portfolio Review', now, now),
        )
        conn.commit()
        session_id = cur.lastrowid

    # 4. Persist the full prompt as the user message
    _save_message(session_id, 'user', full_prompt)

    # 5. Build system prompt
    today = datetime.now().strftime('%A, %B %-d, %Y')
    utc_offset = datetime.now().astimezone().strftime('%z')
    offset_str = f"{utc_offset[:3]}:{utc_offset[3:]}"

    with _get_db() as conn:
        pinboard_rows = conn.execute(
            "SELECT title, content, tags FROM research_pinboard ORDER BY created_at DESC"
        ).fetchall()

    pinboard_text = '\n\n'.join(
        f"**{r['title']}** [{r['tags']}]\n{r['content']}" for r in pinboard_rows
    ) if pinboard_rows else '(no notes yet)'

    system_msg = {
        'role': 'system',
        'content': (
            f"You are an investment research assistant for Ryan Hogan.\n"
            f"Today is {today}. Your local UTC offset is {offset_str}.\n"
            "You have access to tools for web search, financial data, news, portfolio data, and local files.\n"
            "Be concise, cite your sources, and flag uncertainty clearly.\n\n"
            f"=== Investment Notes & Theses ===\n{pinboard_text}"
        ),
    }

    def generate():
        loop_messages = [system_msg, {'role': 'user', 'content': full_prompt}]
        try:
            while True:
                resp = httpx.post(
                    f'{OLLAMA_URL}/api/chat',
                    json={
                        'model': DEFAULT_MODEL,
                        'messages': loop_messages,
                        'tools': RESEARCH_TOOLS,
                        'stream': False,
                        'think': True,
                        'options': {'num_ctx': 16384, 'num_predict': 4096},
                    },
                    timeout=300.0,
                )
                resp.raise_for_status()

                msg = resp.json()['message']
                tool_calls = msg.get('tool_calls') or []

                if not tool_calls:
                    content = msg.get('content', '')
                    if '<think>' in content:
                        content = content.split('</think>', 1)[-1].strip()
                    _save_message(session_id, 'assistant', content)
                    _touch_session(session_id)
                    yield (json.dumps({'message': {'content': content}}) + '\n').encode()
                    break

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
                    label = _TOOL_STATUS.get(name, lambda a: f'Using {name}…')(args)
                    yield (json.dumps({'status': label}) + '\n').encode()
                    handler = _RESEARCH_TOOL_HANDLERS.get(name)
                    result = handler(args) if handler else f'Unknown tool: {name}'
                    _save_message(session_id, 'tool', result)
                    loop_messages.append({'role': 'tool', 'content': result})

        except httpx.ConnectError:
            yield b'{"error": "Cannot connect to Ollama. Is it running?"}\n'
        except httpx.HTTPStatusError as exc:
            yield (json.dumps({'error': f'Ollama error: {exc.response.status_code}'}) + '\n').encode()
        except Exception as exc:
            yield (json.dumps({'error': str(exc)}) + '\n').encode()

    def generate_with_session_id():
        yield (json.dumps({'session_id': session_id}) + '\n').encode()
        yield from generate()

    return Response(stream_with_context(generate_with_session_id()), mimetype='application/x-ndjson')


# ---------------------------------------------------------------------------
# Background: summarise + title
# ---------------------------------------------------------------------------

@research_bp.route('/api/research/sessions/<int:session_id>/summarise', methods=['POST'])
def summarise_session(session_id: int) -> Response:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM research_messages WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()

    if not rows:
        return jsonify({'ok': True, 'summary': ''})

    transcript = '\n'.join(f"{r['role'].upper()}: {r['content'][:500]}" for r in rows)
    prompt = (
        "Summarise this investment research conversation in 3-5 sentences. "
        "Focus on key findings, tickers discussed, conclusions, and any open questions.\n\n"
        f"{transcript}"
    )

    try:
        resp = httpx.post(
            f'{OLLAMA_URL}/api/chat',
            json={
                'model': DEFAULT_MODEL,
                'messages': [{'role': 'user', 'content': prompt}],
                'stream': False,
                'options': {'num_ctx': 8192, 'num_predict': 512},
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        summary = resp.json()['message'].get('content', '').strip()
        if '<think>' in summary:
            summary = summary.split('</think>', 1)[-1].strip()
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

    with _get_db() as conn:
        conn.execute(
            "UPDATE research_sessions SET auto_summary = ? WHERE id = ?",
            (summary, session_id),
        )
        conn.commit()

    return jsonify({'ok': True, 'summary': summary})


@research_bp.route('/api/research/sessions/<int:session_id>/title', methods=['GET'])
def get_session_title(session_id: int) -> Response:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM research_messages WHERE session_id = ? ORDER BY created_at LIMIT 4",
            (session_id,),
        ).fetchall()

    if not rows:
        return jsonify({'title': 'New session'})

    exchange = '\n'.join(f"{r['role']}: {r['content'][:200]}" for r in rows)
    prompt = (
        "Generate a short (5-8 word) descriptive title for this investment research conversation. "
        "Return only the title, no quotes, no punctuation at the end.\n\n"
        f"{exchange}"
    )

    try:
        resp = httpx.post(
            f'{OLLAMA_URL}/api/chat',
            json={
                'model': DEFAULT_MODEL,
                'messages': [{'role': 'user', 'content': prompt}],
                'stream': False,
                'options': {'num_ctx': 4096, 'num_predict': 32},
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        title = resp.json()['message'].get('content', '').strip()
        if '<think>' in title:
            title = title.split('</think>', 1)[-1].strip()
        title = title[:100]
    except Exception:
        return jsonify({'title': 'Research session'})

    with _get_db() as conn:
        conn.execute(
            "UPDATE research_sessions SET title = ? WHERE id = ?",
            (title, session_id),
        )
        conn.commit()

    return jsonify({'title': title})
