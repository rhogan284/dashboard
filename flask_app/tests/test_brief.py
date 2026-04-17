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


# ── /api/brief/history ──────────────────────────────────────────────────────

def test_history_returns_empty_when_no_briefs_dir(client, data_dir):
    """Returns [] when the briefs/ directory doesn't exist."""
    import shutil
    briefs_dir = data_dir / 'briefs'
    shutil.rmtree(briefs_dir, ignore_errors=True)
    resp = client.get('/api/brief/history')
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_history_returns_up_to_five_entries(client, data_dir):
    """Returns at most 5 entries, newest first."""
    briefs_dir = data_dir / 'briefs'
    briefs_dir.mkdir(exist_ok=True)
    dates = ['2026-04-10', '2026-04-11', '2026-04-12', '2026-04-13',
             '2026-04-14', '2026-04-15']
    for d in dates:
        (briefs_dir / f'{d}.md').write_text(f'# Brief {d}')
    resp = client.get('/api/brief/history')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 5
    assert data[0]['date'] == '2026-04-15'  # newest first


def test_history_entry_has_date_and_label(client, data_dir):
    """Each entry has 'date' and 'label' keys."""
    briefs_dir = data_dir / 'briefs'
    briefs_dir.mkdir(exist_ok=True)
    (briefs_dir / '2026-04-10.md').write_text('# Brief')
    resp = client.get('/api/brief/history')
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert 'date' in data[0]
    assert 'label' in data[0]
    assert data[0]['date'] == '2026-04-10'


# ── /api/brief/archive/<date> ────────────────────────────────────────────────

def test_archive_returns_markdown_content(client, data_dir):
    """Returns the markdown content of the archived brief."""
    briefs_dir = data_dir / 'briefs'
    briefs_dir.mkdir(exist_ok=True)
    (briefs_dir / '2026-04-10.md').write_text('# Morning Brief')
    resp = client.get('/api/brief/archive/2026-04-10')
    assert resp.status_code == 200
    assert '# Morning Brief' in resp.get_data(as_text=True)


def test_archive_returns_404_for_missing_date(client, data_dir):
    """Returns 404 when no brief exists for the given date."""
    resp = client.get('/api/brief/archive/2020-01-01')
    assert resp.status_code == 404


def test_archive_returns_400_for_invalid_date_format(client, data_dir):
    """Returns 400 for non-date strings."""
    resp = client.get('/api/brief/archive/not-a-date')
    assert resp.status_code == 400


# ── /api/brief/config ────────────────────────────────────────────────────────

def test_get_config_returns_defaults_when_no_file(client, data_dir):
    """Returns all-true defaults when brief_config.json doesn't exist."""
    config_file = data_dir / 'brief_config.json'
    config_file.unlink(missing_ok=True)
    resp = client.get('/api/brief/config')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data == {'gmail': True, 'calendar': True, 'markets': True, 'canvas': True}


def test_patch_config_merges_partial_update(client, data_dir):
    """PATCH merges updates and ignores unknown keys."""
    resp = client.patch(
        '/api/brief/config',
        json={'gmail': False, 'unknown_key': True},
        content_type='application/json',
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['gmail'] is False
    assert data['calendar'] is True
    assert 'unknown_key' not in data


def test_patch_config_persists(client, data_dir):
    """PATCH writes the config to disk."""
    import json as _json
    client.patch('/api/brief/config', json={'canvas': False}, content_type='application/json')
    config_file = data_dir / 'brief_config.json'
    assert config_file.exists()
    saved = _json.loads(config_file.read_text())
    assert saved['canvas'] is False


