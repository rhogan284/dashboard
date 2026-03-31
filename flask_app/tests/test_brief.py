import json
import sys
import os
from datetime import date, timedelta


# ── /api/brief/status ────────────────────────────────────────────────────────

def test_brief_status_default_when_no_file(client):
    """Returns never_run default when brief_status.json doesn't exist."""
    response = client.get('/api/brief/status')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'never_run'
    assert data['generated_at'] is None
    assert data['error'] is None
    assert data['gmail_connected'] is False


def test_brief_status_reads_existing_file(client, app):
    """Returns data from brief_status.json when it exists."""
    status = {
        'status': 'success',
        'generated_at': '2026-03-29T07:00:00',
        'error': None,
    }
    status_file = app.config['DATA_DIR'] / 'brief_status.json'
    status_file.write_text(json.dumps(status))

    response = client.get('/api/brief/status')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'success'
    assert data['generated_at'] == '2026-03-29T07:00:00'


def test_brief_status_gmail_connected_when_token_exists(client, app):
    """gmail_connected is True when brief_token.json contains a refresh_token."""
    token = {
        'token': 'access_token',
        'refresh_token': 'refresh_token_value',
        'token_uri': 'https://oauth2.googleapis.com/token',
        'client_id': 'client_id',
        'client_secret': 'client_secret',
        'scopes': ['https://www.googleapis.com/auth/gmail.readonly'],
    }
    token_file = app.config['DATA_DIR'] / 'brief_token.json'
    token_file.write_text(json.dumps(token))

    response = client.get('/api/brief/status')
    assert response.status_code == 200
    assert response.get_json()['gmail_connected'] is True


# ── /api/brief/preview ───────────────────────────────────────────────────────

def test_brief_preview_returns_empty_when_no_file(client):
    """Returns empty body when morning_brief.md doesn't exist."""
    response = client.get('/api/brief/preview')
    assert response.status_code == 200
    assert response.data == b''


def test_brief_preview_serves_existing_file(client, app):
    """Serves morning_brief.md when it exists."""
    md = '# Morning Brief\n\nTest content.'
    (app.config['DATA_DIR'] / 'morning_brief.md').write_text(md)

    response = client.get('/api/brief/preview')
    assert response.status_code == 200
    assert b'# Morning Brief' in response.data


# ── morning_brief.py helpers ─────────────────────────────────────────────────

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'scripts'))
from morning_brief import (
    format_today_events,
    format_week_events,
    assemble_brief,
)


def test_format_today_events_returns_today_only():
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    events = [
        {'summary': 'Today meeting', 'start': {'date': today}},
        {'summary': 'Tomorrow event', 'start': {'date': tomorrow}},
    ]
    result = format_today_events(events)
    assert 'Today meeting' in result
    assert 'Tomorrow event' not in result


def test_format_today_events_empty():
    assert format_today_events([]) == '(nothing scheduled today)'


def test_format_week_events_excludes_today():
    today = date.today().isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    events = [
        {'summary': 'Today meeting', 'start': {'date': today}},
        {'summary': 'Tomorrow event', 'start': {'date': tomorrow}},
    ]
    result = format_week_events(events)
    assert 'Tomorrow event' in result
    assert 'Today meeting' not in result


def test_format_week_events_empty():
    assert format_week_events([]) == '(no events this week)'


def test_assemble_brief_contains_all_sections():
    gmail_md = '## 📧 Email Highlights\n- Nothing urgent'
    markets_md = '## 🇺🇸 US Markets\nS&P flat'
    calendar_md = '## 📅 Calendar\nNo events'
    result = assemble_brief(gmail_md, markets_md, calendar_md, 'Monday, March 30, 2026')
    assert 'Morning Brief' in result
    assert 'Email Highlights' in result
    assert 'US Markets' in result
    assert 'Calendar' in result
    assert 'Monday, March 30, 2026' in result
