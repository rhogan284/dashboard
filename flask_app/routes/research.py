import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
# Response, stream_with_context, jsonify, request are used by route handlers added in later tasks
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

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
