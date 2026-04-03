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
