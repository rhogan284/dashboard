import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from routes.llm import _search_web, _strip_thinking, OMLX_API_KEY
from routes.research import _read_local_file

canvas_bp = Blueprint('canvas', __name__)

OMLX_URL = os.getenv('OMLX_BASE_URL', 'http://localhost:8002')
OMLX_MODEL = os.getenv('OMLX_MODEL', 'gemma-4-26b-a4b-it-4bit')
OMLX_TEMPERATURE = float(os.getenv('OMLX_TEMPERATURE', '0.7'))
CANVAS_BASE_URL = os.getenv('CANVAS_BASE_URL', '').rstrip('/')
CANVAS_KEY = os.getenv('CANVAS_KEY', '')

CALENDAR_API = 'https://www.googleapis.com/calendar/v3'
CACHE_TTL_COURSES = 3600      # 1 hour
CACHE_TTL_ASSIGNMENTS = 1800  # 30 minutes

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

@contextmanager
def _get_db():
    db_path = Path(current_app.config['DATA_DIR']) / 'canvas.db'
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def _init_db():
    db_path = Path(current_app.config['DATA_DIR']) / 'canvas.db'
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        # Create base tables (without course_id index — added after migration)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS canvas_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL DEFAULT 'New session',
                course_id   INTEGER,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL,
                auto_summary TEXT
            );
            CREATE TABLE IF NOT EXISTS canvas_messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id  INTEGER NOT NULL REFERENCES canvas_sessions(id) ON DELETE CASCADE,
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS canvas_cache (
                key         TEXT PRIMARY KEY,
                value       TEXT NOT NULL,
                cached_at   TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_canvas_messages_session
                ON canvas_messages(session_id);
        """)
        # Migration: add course_id to existing DBs that predate this column.
        # Must run before creating the index on course_id.
        try:
            conn.execute("ALTER TABLE canvas_sessions ADD COLUMN course_id INTEGER")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
        # Create course_id index now that the column is guaranteed to exist
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_canvas_sessions_course ON canvas_sessions(course_id)"
        )
        conn.commit()
    finally:
        conn.close()


@canvas_bp.record_once
def _on_registered(state):
    with state.app.app_context():
        _init_db()


# ---------------------------------------------------------------------------
# Canvas API client
# ---------------------------------------------------------------------------

def _canvas_headers() -> dict:
    return {'Authorization': f'Bearer {CANVAS_KEY}'}


def _canvas_get(path: str, params: dict | None = None) -> list | dict:
    """Fetch from Canvas REST API, handling pagination via Link header."""
    if not CANVAS_BASE_URL:
        raise RuntimeError('CANVAS_BASE_URL not configured in .env')
    url = f'{CANVAS_BASE_URL}/api/v1{path}'
    results = []
    while url:
        resp = httpx.get(url, headers=_canvas_headers(), params=params, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            results.extend(data)
        else:
            return data
        # Follow pagination
        link = resp.headers.get('Link', '')
        url = None
        params = None  # params already encoded in next URL
        for part in link.split(','):
            part = part.strip()
            if 'rel="next"' in part:
                url = part.split(';')[0].strip().strip('<>')
                break
    return results


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_get(key: str, ttl: int) -> list | None:
    """Return cached value if present and not expired, else None."""
    with _get_db() as conn:
        row = conn.execute(
            "SELECT value, cached_at FROM canvas_cache WHERE key = ?", (key,)
        ).fetchone()
    if not row:
        return None
    cached_at = datetime.fromisoformat(row['cached_at'])
    if (datetime.now(timezone.utc) - cached_at).total_seconds() > ttl:
        return None
    return json.loads(row['value'])


def _cache_set(key: str, value: list | dict):
    now = datetime.now(timezone.utc).isoformat()
    with _get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO canvas_cache (key, value, cached_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), now),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Canvas data fetchers
# ---------------------------------------------------------------------------

def _get_courses() -> list:
    cached = _cache_get('courses', CACHE_TTL_COURSES)
    if cached is not None:
        return cached
    data = _canvas_get('/courses', {'enrollment_state': 'active', 'per_page': 50})
    courses = [
        {
            'id': c['id'],
            'name': c.get('name', ''),
            'course_code': c.get('course_code', ''),
        }
        for c in data
        if isinstance(c, dict) and c.get('name')
    ]
    _cache_set('courses', courses)
    return courses


def _get_modules(course_id: int) -> list:
    cache_key = f'modules:{course_id}'
    cached = _cache_get(cache_key, CACHE_TTL_ASSIGNMENTS)
    if cached is not None:
        return cached
    data = _canvas_get(
        f'/courses/{course_id}/modules',
        {'per_page': 50},
    )
    modules = [
        {
            'id': m['id'],
            'name': m.get('name', ''),
            'position': m.get('position'),
            'state': m.get('state'),
            'items_count': m.get('items_count', 0),
            'unlock_at': m.get('unlock_at'),
            'completed': m.get('completed_at') is not None,
        }
        for m in data
        if isinstance(m, dict)
    ]
    _cache_set(cache_key, modules)
    return modules


def _get_module_items(course_id: int, module_id: int) -> list:
    cache_key = f'module_items:{course_id}:{module_id}'
    cached = _cache_get(cache_key, CACHE_TTL_ASSIGNMENTS)
    if cached is not None:
        return cached
    data = _canvas_get(
        f'/courses/{course_id}/modules/{module_id}/items',
        {'per_page': 100, 'include[]': 'content_details'},
    )
    items = [
        {
            'id': item['id'],
            'title': item.get('title', ''),
            'type': item.get('type', ''),
            'position': item.get('position'),
            'indent': item.get('indent', 0),
            'completion_requirement': item.get('completion_requirement'),
            'content_id': item.get('content_id'),
            'html_url': item.get('html_url', ''),
            'url': item.get('url', ''),
            'due_at': item.get('content_details', {}).get('due_at'),
            'points_possible': item.get('content_details', {}).get('points_possible'),
        }
        for item in data
        if isinstance(item, dict)
    ]
    _cache_set(cache_key, items)
    return items


def _get_assignments(course_id: int | None = None) -> list:
    cache_key = f'assignments:{course_id or "all"}'
    cached = _cache_get(cache_key, CACHE_TTL_ASSIGNMENTS)
    if cached is not None:
        return cached

    if course_id:
        course_ids = [course_id]
    else:
        courses = _get_courses()
        course_ids = [c['id'] for c in courses]

    assignments = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for cid in course_ids:
        try:
            items = _canvas_get(
                f'/courses/{cid}/assignments',
                {'bucket': 'upcoming', 'order_by': 'due_at', 'per_page': 50},
            )
            for a in items:
                if not isinstance(a, dict):
                    continue
                due = a.get('due_at')
                assignments.append({
                    'id': a['id'],
                    'course_id': cid,
                    'name': a.get('name', ''),
                    'due_at': due,
                    'points_possible': a.get('points_possible'),
                    'submission_types': a.get('submission_types', []),
                    'submitted': bool(a.get('has_submitted_submissions')),
                    'html_url': a.get('html_url', ''),
                })
        except Exception:
            pass

    assignments.sort(key=lambda a: a.get('due_at') or '9999')
    _cache_set(cache_key, assignments)
    return assignments


def _get_assignment_details(course_id: int, assignment_id: int) -> dict:
    try:
        data = _canvas_get(f'/courses/{course_id}/assignments/{assignment_id}')
        return {
            'name': data.get('name', ''),
            'due_at': data.get('due_at'),
            'points_possible': data.get('points_possible'),
            'description': _strip_html(data.get('description', '')),
            'submission_types': data.get('submission_types', []),
            'rubric': data.get('rubric', []),
            'html_url': data.get('html_url', ''),
        }
    except Exception as exc:
        return {'error': str(exc)}


def _get_grades() -> list:
    cached = _cache_get('grades', CACHE_TTL_COURSES)
    if cached is not None:
        return cached
    courses = _get_courses()
    grades = []
    for c in courses:
        try:
            enrollments = _canvas_get(
                f'/courses/{c["id"]}/enrollments',
                {'type[]': 'StudentEnrollment', 'user_id': 'self'},
            )
            for e in enrollments:
                if not isinstance(e, dict):
                    continue
                grade = e.get('grades', {})
                grades.append({
                    'course_id': c['id'],
                    'course_name': c['name'],
                    'current_grade': grade.get('current_grade'),
                    'current_score': grade.get('current_score'),
                    'final_grade': grade.get('final_grade'),
                    'final_score': grade.get('final_score'),
                })
        except Exception:
            pass
    _cache_set('grades', grades)
    return grades


def _strip_html(html: str) -> str:
    """Very basic HTML tag stripping for assignment descriptions."""
    import re
    text = re.sub(r'<[^>]+>', ' ', html or '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:3000]


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

def _save_message(session_id: int, role: str, content: str):
    now = datetime.now(timezone.utc).isoformat()
    with _get_db() as conn:
        conn.execute(
            "INSERT INTO canvas_messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, now),
        )
        conn.commit()


def _touch_session(session_id: int):
    now = datetime.now(timezone.utc).isoformat()
    with _get_db() as conn:
        conn.execute(
            "UPDATE canvas_sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Session routes
# ---------------------------------------------------------------------------

@canvas_bp.route('/api/canvas/sessions', methods=['GET'])
def list_sessions():
    # ?course_id=null → general sessions (course_id IS NULL)
    # ?course_id=123  → sessions for that course
    # no param        → all sessions
    raw = request.args.get('course_id')
    with _get_db() as conn:
        if raw is None:
            rows = conn.execute(
                "SELECT id, title, course_id, created_at, updated_at FROM canvas_sessions ORDER BY updated_at DESC"
            ).fetchall()
        elif raw == 'null':
            rows = conn.execute(
                "SELECT id, title, course_id, created_at, updated_at FROM canvas_sessions "
                "WHERE course_id IS NULL ORDER BY updated_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, course_id, created_at, updated_at FROM canvas_sessions "
                "WHERE course_id = ? ORDER BY updated_at DESC",
                (int(raw),),
            ).fetchall()
    return jsonify([dict(r) for r in rows])


@canvas_bp.route('/api/canvas/session-counts', methods=['GET'])
def session_counts():
    """Return session counts keyed by course_id (string). 'null' = general sessions."""
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT course_id, COUNT(*) as cnt FROM canvas_sessions GROUP BY course_id"
        ).fetchall()
    counts = {}
    for r in rows:
        key = 'null' if r['course_id'] is None else str(r['course_id'])
        counts[key] = r['cnt']
    return jsonify(counts)


@canvas_bp.route('/api/canvas/sessions', methods=['POST'])
def create_session():
    data = request.get_json(silent=True) or {}
    course_id = data.get('course_id')  # None = general session
    if course_id is not None:
        course_id = int(course_id)
    now = datetime.now(timezone.utc).isoformat()
    with _get_db() as conn:
        cur = conn.execute(
            "INSERT INTO canvas_sessions (title, course_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
            ('New session', course_id, now, now),
        )
        conn.commit()
        session_id = cur.lastrowid
    return jsonify({'id': session_id})


@canvas_bp.route('/api/canvas/sessions/<int:session_id>', methods=['GET'])
def get_session(session_id: int):
    with _get_db() as conn:
        row = conn.execute(
            "SELECT id, title, created_at, updated_at, auto_summary FROM canvas_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return jsonify({'error': 'Session not found'}), 404
        messages = conn.execute(
            "SELECT role, content, created_at FROM canvas_messages WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()
    return jsonify({**dict(row), 'messages': [dict(m) for m in messages]})


@canvas_bp.route('/api/canvas/sessions/<int:session_id>', methods=['PATCH'])
def update_session(session_id: int):
    data = request.get_json(silent=True) or {}
    title = str(data.get('title', '')).strip()
    if not title:
        return jsonify({'error': 'title required'}), 400
    with _get_db() as conn:
        conn.execute(
            "UPDATE canvas_sessions SET title = ? WHERE id = ?",
            (title, session_id),
        )
        conn.commit()
    return jsonify({'ok': True})


@canvas_bp.route('/api/canvas/sessions/<int:session_id>', methods=['DELETE'])
def delete_session(session_id: int):
    with _get_db() as conn:
        conn.execute("DELETE FROM canvas_sessions WHERE id = ?", (session_id,))
        conn.commit()
    return jsonify({'ok': True})


# ---------------------------------------------------------------------------
# Courses + assignments routes
# ---------------------------------------------------------------------------

@canvas_bp.route('/api/canvas/courses', methods=['GET'])
def get_courses_route():
    try:
        return jsonify(_get_courses())
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


@canvas_bp.route('/api/canvas/assignments', methods=['GET'])
def get_assignments_route():
    course_id = request.args.get('course_id', type=int)
    try:
        return jsonify(_get_assignments(course_id))
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


# ---------------------------------------------------------------------------
# Calendar sync route
# ---------------------------------------------------------------------------

@canvas_bp.route('/api/canvas/sync-calendar', methods=['POST'])
def sync_calendar():
    import json as _json
    import time

    token_path = Path(current_app.config['DATA_DIR']) / 'gcal_token.json'
    if not token_path.exists():
        return jsonify({'error': 'Google Calendar not connected. Connect it via the Dashboard tab first.'}), 400

    try:
        token_data = _json.loads(token_path.read_text())
    except Exception:
        return jsonify({'error': 'Failed to read Google Calendar token.'}), 400

    if time.time() * 1000 > token_data.get('expires_at', 0):
        return jsonify({'error': 'Google Calendar token expired. Please reconnect via the Dashboard tab.'}), 400

    access_token = token_data.get('access_token', '')
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    try:
        assignments = _get_assignments()
    except Exception as exc:
        return jsonify({'error': f'Failed to fetch Canvas assignments: {exc}'}), 500

    # Fetch existing Canvas-tagged events to avoid duplicates
    now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    existing_resp = httpx.get(
        f'{CALENDAR_API}/calendars/primary/events',
        headers=headers,
        params={
            'privateExtendedProperty': 'source=canvas',
            'timeMin': now_iso,
            'singleEvents': 'true',
            'maxResults': '500',
        },
        timeout=15.0,
    )
    existing_ids: set[str] = set()
    if existing_resp.is_success:
        for event in existing_resp.json().get('items', []):
            aid = event.get('extendedProperties', {}).get('private', {}).get('canvasAssignmentId')
            if aid:
                existing_ids.add(aid)

    created = 0
    skipped = 0
    errors = 0

    for a in assignments:
        if not a.get('due_at'):
            skipped += 1
            continue

        assignment_id_str = str(a['id'])
        if assignment_id_str in existing_ids:
            skipped += 1
            continue

        try:
            due = datetime.fromisoformat(a['due_at'].replace('Z', '+00:00'))
            start_iso = due.strftime('%Y-%m-%dT%H:%M:%SZ')
            end_iso = (due + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')

            # Find course name
            courses = _get_courses()
            course_name = next((c['name'] for c in courses if c['id'] == a['course_id']), 'Canvas')

            event = {
                'summary': f"{course_name}: {a['name']}",
                'description': f"Canvas assignment\n{a.get('html_url', '')}",
                'start': {'dateTime': start_iso, 'timeZone': 'UTC'},
                'end': {'dateTime': end_iso, 'timeZone': 'UTC'},
                'extendedProperties': {
                    'private': {
                        'source': 'canvas',
                        'canvasAssignmentId': assignment_id_str,
                    }
                },
            }

            create_resp = httpx.post(
                f'{CALENDAR_API}/calendars/primary/events',
                headers=headers,
                json=event,
                timeout=15.0,
            )
            if create_resp.is_success:
                created += 1
            else:
                errors += 1
        except Exception:
            errors += 1

    return jsonify({
        'ok': True,
        'created': created,
        'skipped': skipped,
        'errors': errors,
        'message': f'Synced {created} assignment(s) to Google Calendar.',
    })


# ---------------------------------------------------------------------------
# Brief route
# ---------------------------------------------------------------------------

@canvas_bp.route('/api/canvas/brief', methods=['GET'])
def get_brief():
    try:
        assignments = _get_assignments()
        return jsonify({'markdown': _build_brief_markdown(assignments)})
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500


def _build_brief_markdown(assignments: list) -> str:
    now = datetime.now(timezone.utc)
    week_end = now + timedelta(days=7)
    due_this_week = []
    overdue = []

    for a in assignments:
        if not a.get('due_at'):
            continue
        try:
            due = datetime.fromisoformat(a['due_at'].replace('Z', '+00:00'))
        except ValueError:
            continue
        if due < now:
            overdue.append((a, due))
        elif due <= week_end:
            due_this_week.append((a, due))

    lines = ['## 🎓 Academics', '']

    if due_this_week:
        lines.append('**Due this week:**')
        for a, due in due_this_week:
            day = due.strftime('%a %b %-d')
            lines.append(f'- {a["name"]} — {day}')
    else:
        lines.append('**Due this week:** Nothing due')

    lines.append('')

    if overdue:
        lines.append('**Overdue:**')
        for a, due in overdue:
            day = due.strftime('%b %-d')
            lines.append(f'- {a["name"]} (was due {day})')
    else:
        lines.append('**Overdue:** None')

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

CANVAS_TOOLS = [
    {
        'type': 'function',
        'function': {
            'name': 'get_courses',
            'description': 'List all active enrolled courses from Canvas.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_assignments',
            'description': 'Get upcoming assignments from Canvas, optionally for a specific course.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'course_id': {
                        'type': 'integer',
                        'description': 'Canvas course ID to scope results. Omit for all courses.',
                    },
                },
                'required': [],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_assignment_details',
            'description': 'Get the full description, rubric, and requirements for a specific Canvas assignment.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'course_id': {'type': 'integer', 'description': 'Canvas course ID'},
                    'assignment_id': {'type': 'integer', 'description': 'Canvas assignment ID'},
                },
                'required': ['course_id', 'assignment_id'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_modules',
            'description': 'List all modules for a Canvas course, showing the course structure and topics covered.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'course_id': {'type': 'integer', 'description': 'Canvas course ID'},
                },
                'required': ['course_id'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_module_items',
            'description': 'List all items (lectures, readings, assignments, quizzes, pages) inside a specific Canvas module.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'course_id': {'type': 'integer', 'description': 'Canvas course ID'},
                    'module_id': {'type': 'integer', 'description': 'Canvas module ID (from get_modules)'},
                },
                'required': ['course_id', 'module_id'],
            },
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'get_grades',
            'description': 'Get current grade standing for all enrolled courses.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'sync_to_calendar',
            'description': 'Push Canvas assignment due dates to Google Calendar.',
            'parameters': {'type': 'object', 'properties': {}, 'required': []},
        },
    },
    {
        'type': 'function',
        'function': {
            'name': 'search_web',
            'description': 'Search the web for information to help with coursework or research.',
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
            'name': 'read_local_file',
            'description': 'Read a local PDF, CSV, or XLSX file and return its text content. Use when the user attaches a file path.',
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
    'get_courses':            lambda _: 'Fetching enrolled courses…',
    'get_assignments':        lambda a: f"Fetching assignments{' for course ' + str(a['course_id']) if a.get('course_id') else ''}…",
    'get_assignment_details': lambda _: 'Loading assignment details…',
    'get_modules':            lambda a: f"Fetching modules for course {a.get('course_id', '')}…",
    'get_module_items':       lambda a: f"Fetching items in module {a.get('module_id', '')}…",
    'get_grades':             lambda _: 'Fetching grades…',
    'sync_to_calendar':       lambda _: 'Syncing to Google Calendar…',
    'search_web':             lambda a: f"Searching: \"{a.get('query', '')}\"",
    'read_local_file':        lambda a: f"Reading {Path(a.get('path', '')).name}…",
}


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _handle_sync_to_calendar(_args: dict) -> str:
    """Call the sync endpoint internally."""
    import json as _json
    import time

    token_path = Path(current_app.config['DATA_DIR']) / 'gcal_token.json'
    if not token_path.exists():
        return 'Google Calendar not connected. Please connect it via the Dashboard tab.'

    try:
        token_data = _json.loads(token_path.read_text())
    except Exception:
        return 'Failed to read Google Calendar token.'

    if time.time() * 1000 > token_data.get('expires_at', 0):
        return 'Google Calendar token expired. Please reconnect via the Dashboard tab.'

    access_token = token_data.get('access_token', '')
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    try:
        assignments = _get_assignments()
    except Exception as exc:
        return f'Failed to fetch assignments: {exc}'

    now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    existing_resp = httpx.get(
        f'{CALENDAR_API}/calendars/primary/events',
        headers=headers,
        params={
            'privateExtendedProperty': 'source=canvas',
            'timeMin': now_iso,
            'singleEvents': 'true',
            'maxResults': '500',
        },
        timeout=15.0,
    )
    existing_ids: set[str] = set()
    if existing_resp.is_success:
        for event in existing_resp.json().get('items', []):
            aid = event.get('extendedProperties', {}).get('private', {}).get('canvasAssignmentId')
            if aid:
                existing_ids.add(aid)

    created = 0
    skipped = 0
    courses = _get_courses()

    for a in assignments:
        if not a.get('due_at') or str(a['id']) in existing_ids:
            skipped += 1
            continue
        try:
            due = datetime.fromisoformat(a['due_at'].replace('Z', '+00:00'))
            start_iso = due.strftime('%Y-%m-%dT%H:%M:%SZ')
            end_iso = (due + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
            course_name = next((c['name'] for c in courses if c['id'] == a['course_id']), 'Canvas')
            event = {
                'summary': f"{course_name}: {a['name']}",
                'description': f"Canvas assignment\n{a.get('html_url', '')}",
                'start': {'dateTime': start_iso, 'timeZone': 'UTC'},
                'end': {'dateTime': end_iso, 'timeZone': 'UTC'},
                'extendedProperties': {
                    'private': {'source': 'canvas', 'canvasAssignmentId': str(a['id'])}
                },
            }
            resp = httpx.post(
                f'{CALENDAR_API}/calendars/primary/events',
                headers=headers, json=event, timeout=15.0,
            )
            if resp.is_success:
                created += 1
            else:
                skipped += 1
        except Exception:
            skipped += 1

    return f'Synced {created} assignment(s) to Google Calendar ({skipped} already existed or had no due date).'


_CANVAS_TOOL_HANDLERS = {
    'get_courses':            lambda _: json.dumps(_get_courses()),
    'get_assignments':        lambda a: json.dumps(_get_assignments(a.get('course_id'))),
    'get_assignment_details': lambda a: json.dumps(_get_assignment_details(a['course_id'], a['assignment_id'])),
    'get_modules':            lambda a: json.dumps(_get_modules(a['course_id'])),
    'get_module_items':       lambda a: json.dumps(_get_module_items(a['course_id'], a['module_id'])),
    'get_grades':             lambda _: json.dumps(_get_grades()),
    'sync_to_calendar':       _handle_sync_to_calendar,
    'search_web':             _search_web,
    'read_local_file':        _read_local_file,
}


# ---------------------------------------------------------------------------
# System prompt context builder
# ---------------------------------------------------------------------------

def _build_context_block() -> str:
    """Fetch courses + near-term assignments to inject into the system prompt."""
    try:
        courses = _get_courses()
        courses_text = '\n'.join(f"- {c['name']} (ID: {c['id']})" for c in courses) or '(none)'
    except Exception as exc:
        courses_text = f'(error fetching courses: {exc})'

    try:
        assignments = _get_assignments()
        now = datetime.now(timezone.utc)
        soon = now + timedelta(days=14)
        upcoming = [
            a for a in assignments
            if a.get('due_at') and datetime.fromisoformat(
                a['due_at'].replace('Z', '+00:00')
            ) <= soon
        ]
        if upcoming:
            lines = []
            for a in upcoming:
                due = datetime.fromisoformat(a['due_at'].replace('Z', '+00:00'))
                status = '✓ Submitted' if a['submitted'] else 'Not submitted'
                lines.append(f"- [{due.strftime('%b %-d')}] {a['name']} ({status})")
            assignments_text = '\n'.join(lines)
        else:
            assignments_text = '(no upcoming assignments in the next 14 days)'
    except Exception as exc:
        assignments_text = f'(error fetching assignments: {exc})'

    return (
        f"=== Enrolled Courses ===\n{courses_text}\n\n"
        f"=== Upcoming Assignments (next 14 days) ===\n{assignments_text}"
    )


# ---------------------------------------------------------------------------
# Chat route
# ---------------------------------------------------------------------------

@canvas_bp.route('/api/canvas/chat', methods=['POST'])
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
    course_id = data.get('course_id')  # optional scope

    today = datetime.now().strftime('%A, %B %-d, %Y')
    utc_offset = datetime.now().astimezone().strftime('%z')
    offset_str = f"{utc_offset[:3]}:{utc_offset[3:]}"

    context_block = _build_context_block()

    scope_note = ''
    if course_id:
        try:
            courses = _get_courses()
            course = next((c for c in courses if c['id'] == course_id), None)
            if course:
                scope_note = f'\nCurrent focus: {course["name"]} (course ID {course_id})'
        except Exception:
            pass

    think_prefix = '<|think|>' if think else ''
    system_content = (
        f"{think_prefix}You are an AI academic tutor for Ryan Hogan.\n"
        f"Today is {today}. Your local UTC offset is {offset_str}.\n"
        "You have access to tools to fetch Canvas course data, assignments, grades, and can search the web.\n"
        "Help Ryan with his coursework: explain concepts, review assignment requirements, "
        "create study plans, help draft outlines, and answer academic questions.\n"
        "Be specific, practical, and cite sources when researching topics.\n"
        f"{scope_note}\n\n"
        f"{context_block}"
    )
    system_msg = {'role': 'system', 'content': system_content}

    def generate():
        loop_messages = [system_msg] + list(messages)

        last = messages[-1]
        if last.get('role') == 'user':
            _save_message(session_id, 'user', last['content'])

        try:
            while True:
                think_buf = ''
                past_thinking = False
                accumulated_content = ''
                accumulated_tool_calls = {}

                with httpx.stream(
                    'POST',
                    f'{OMLX_URL}/v1/chat/completions',
                    headers={'Authorization': f'Bearer {OMLX_API_KEY}'},
                    json={
                        'model': OMLX_MODEL,
                        'messages': loop_messages,
                        'tools': CANVAS_TOOLS,
                        'max_tokens': 4096 if think else 2048,
                        'temperature': OMLX_TEMPERATURE,
                        'stream': True,
                    },
                    timeout=300.0 if think else 120.0,
                ) as resp:
                    resp.raise_for_status()
                    for raw in resp.iter_lines():
                        if not raw.startswith('data: '):
                            continue
                        payload = raw[6:]
                        if payload == '[DONE]':
                            break
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue

                        delta = chunk['choices'][0].get('delta', {})

                        for tc in (delta.get('tool_calls') or []):
                            idx = tc['index']
                            if idx not in accumulated_tool_calls:
                                accumulated_tool_calls[idx] = {
                                    'id': '', 'function': {'name': '', 'arguments': ''},
                                }
                            if tc.get('id'):
                                accumulated_tool_calls[idx]['id'] = tc['id']
                            fn = tc.get('function', {})
                            accumulated_tool_calls[idx]['function']['name'] += fn.get('name') or ''
                            accumulated_tool_calls[idx]['function']['arguments'] += fn.get('arguments') or ''

                        content = delta.get('content') or ''
                        if not content:
                            continue
                        if past_thinking:
                            accumulated_content += content
                            yield (json.dumps({'chunk': content}) + '\n').encode()
                        else:
                            think_buf += content
                            if '<channel|>' in think_buf:
                                past_thinking = True
                                after = think_buf.split('<channel|>', 1)[1]
                                think_buf = ''
                                if after:
                                    accumulated_content += after
                                    yield (json.dumps({'chunk': after}) + '\n').encode()
                            elif len(think_buf) > 30 and not think_buf.startswith('<|channel>'):
                                past_thinking = True
                                accumulated_content += think_buf
                                yield (json.dumps({'chunk': think_buf}) + '\n').encode()
                                think_buf = ''

                if accumulated_tool_calls:
                    tool_calls_list = [
                        {
                            'id': tc['id'],
                            'type': 'function',
                            'function': {
                                'name': tc['function']['name'],
                                'arguments': tc['function']['arguments'],
                            },
                        }
                        for tc in accumulated_tool_calls.values()
                    ]
                    loop_messages.append({
                        'role': 'assistant',
                        'content': None,
                        'tool_calls': tool_calls_list,
                    })

                    for tc in tool_calls_list:
                        fn = tc['function']
                        name = fn['name']
                        args = fn['arguments']
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}

                        label = _TOOL_STATUS.get(name, lambda a: f'Using {name}…')(args)
                        yield (json.dumps({'status': label}) + '\n').encode()

                        handler = _CANVAS_TOOL_HANDLERS.get(name)
                        result = handler(args) if handler else f'Unknown tool: {name}'

                        tool_content = result if isinstance(result, str) else json.dumps(result)
                        _save_message(session_id, 'tool', tool_content)
                        loop_messages.append({
                            'role': 'tool',
                            'tool_call_id': tc['id'],
                            'content': tool_content,
                        })
                else:
                    _save_message(session_id, 'assistant', accumulated_content)
                    _touch_session(session_id)
                    break

        except httpx.ConnectError:
            yield b'{"error": "Cannot connect to oMLX. Is it running?"}\n'
        except httpx.HTTPStatusError as exc:
            yield (json.dumps({'error': f'oMLX error: {exc.response.status_code}'}) + '\n').encode()
        except Exception as exc:
            yield (json.dumps({'error': str(exc)}) + '\n').encode()

    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')


# ---------------------------------------------------------------------------
# Auto-summarise + title
# ---------------------------------------------------------------------------

@canvas_bp.route('/api/canvas/sessions/<int:session_id>/summarise', methods=['POST'])
def summarise_session(session_id: int) -> Response:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM canvas_messages WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        ).fetchall()

    if not rows:
        return jsonify({'ok': True, 'summary': ''})

    transcript = '\n'.join(f"{r['role'].upper()}: {r['content'][:500]}" for r in rows)
    prompt = (
        "Summarise this academic tutoring conversation in 3-5 sentences. "
        "Focus on the topics covered, key concepts explained, assignments discussed, and any action items.\n\n"
        f"{transcript}"
    )

    try:
        resp = httpx.post(
            f'{OMLX_URL}/v1/chat/completions',
            headers={'Authorization': f'Bearer {OMLX_API_KEY}'},
            json={
                'model': OMLX_MODEL,
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 512,
                'temperature': OMLX_TEMPERATURE,
            },
            timeout=120.0,
        )
        resp.raise_for_status()
        summary = _strip_thinking(resp.json()['choices'][0]['message'].get('content', ''))
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

    with _get_db() as conn:
        conn.execute(
            "UPDATE canvas_sessions SET auto_summary = ? WHERE id = ?",
            (summary, session_id),
        )
        conn.commit()

    return jsonify({'ok': True, 'summary': summary})


@canvas_bp.route('/api/canvas/sessions/<int:session_id>/title', methods=['GET'])
def get_session_title(session_id: int) -> Response:
    with _get_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM canvas_messages WHERE session_id = ? ORDER BY created_at LIMIT 4",
            (session_id,),
        ).fetchall()

    if not rows:
        return jsonify({'title': 'New session'})

    exchange = '\n'.join(f"{r['role']}: {r['content'][:200]}" for r in rows)
    prompt = (
        "Generate a short (5-8 word) descriptive title for this academic tutoring conversation. "
        "Return only the title, no quotes, no punctuation at the end.\n\n"
        f"{exchange}"
    )

    try:
        resp = httpx.post(
            f'{OMLX_URL}/v1/chat/completions',
            headers={'Authorization': f'Bearer {OMLX_API_KEY}'},
            json={
                'model': OMLX_MODEL,
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 32,
                'temperature': OMLX_TEMPERATURE,
            },
            timeout=60.0,
        )
        resp.raise_for_status()
        title = _strip_thinking(resp.json()['choices'][0]['message'].get('content', ''))[:100]
    except Exception:
        return jsonify({'title': 'Tutoring session'})

    with _get_db() as conn:
        conn.execute(
            "UPDATE canvas_sessions SET title = ? WHERE id = ?",
            (title, session_id),
        )
        conn.commit()

    return jsonify({'title': title})
