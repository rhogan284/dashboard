import sqlite3
from pathlib import Path


def test_db_tables_created_on_startup(app):
    db_path = Path(app.config['DATA_DIR']) / 'research.db'
    assert db_path.exists(), "research.db should be created on app startup"
    conn = sqlite3.connect(str(db_path))
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert 'research_sessions' in tables
    assert 'research_messages' in tables
    assert 'research_pinboard' in tables


# ── Session CRUD ──────────────────────────────────────────────────────────────

def test_list_sessions_returns_empty_list_initially(client):
    response = client.get('/api/research/sessions')
    assert response.status_code == 200
    assert response.get_json() == []


def test_create_session_returns_id(client):
    response = client.post('/api/research/sessions')
    assert response.status_code == 200
    data = response.get_json()
    assert 'id' in data
    assert isinstance(data['id'], int)


def test_list_sessions_after_create(client):
    client.post('/api/research/sessions')
    client.post('/api/research/sessions')
    response = client.get('/api/research/sessions')
    sessions = response.get_json()
    assert len(sessions) == 2
    assert 'id' in sessions[0]
    assert 'title' in sessions[0]
    assert 'created_at' in sessions[0]
    assert 'updated_at' in sessions[0]


def test_get_session_returns_metadata_and_messages(client):
    session_id = client.post('/api/research/sessions').get_json()['id']
    response = client.get(f'/api/research/sessions/{session_id}')
    assert response.status_code == 200
    data = response.get_json()
    assert data['id'] == session_id
    assert data['messages'] == []


def test_delete_session(client):
    session_id = client.post('/api/research/sessions').get_json()['id']
    response = client.delete(f'/api/research/sessions/{session_id}')
    assert response.status_code == 200
    assert response.get_json()['ok'] is True
    # Verify gone
    response = client.get('/api/research/sessions')
    assert response.get_json() == []


# ── Pinboard CRUD ─────────────────────────────────────────────────────────────

def test_list_pinboard_returns_empty_initially(client):
    response = client.get('/api/research/pinboard')
    assert response.status_code == 200
    assert response.get_json() == []


def test_add_pinboard_note(client):
    response = client.post('/api/research/pinboard', json={
        'title': 'AAPL thesis',
        'content': 'Strong buy due to services growth.',
        'tags': 'aapl,tech',
    })
    assert response.status_code == 200
    data = response.get_json()
    assert 'id' in data
    assert isinstance(data['id'], int)


def test_list_pinboard_after_add(client):
    client.post('/api/research/pinboard', json={
        'title': 'Note 1', 'content': 'Body', 'tags': 'tag1',
    })
    response = client.get('/api/research/pinboard')
    notes = response.get_json()
    assert len(notes) == 1
    assert notes[0]['title'] == 'Note 1'
    assert notes[0]['tags'] == 'tag1'


def test_update_pinboard_note(client):
    note_id = client.post('/api/research/pinboard', json={
        'title': 'Old', 'content': 'Old body', 'tags': '',
    }).get_json()['id']
    response = client.patch(f'/api/research/pinboard/{note_id}', json={
        'title': 'New', 'content': 'New body', 'tags': 'updated',
    })
    assert response.status_code == 200
    assert response.get_json()['ok'] is True
    notes = client.get('/api/research/pinboard').get_json()
    assert notes[0]['title'] == 'New'
    assert notes[0]['tags'] == 'updated'


def test_delete_pinboard_note(client):
    note_id = client.post('/api/research/pinboard', json={
        'title': 'Delete me', 'content': 'x', 'tags': '',
    }).get_json()['id']
    response = client.delete(f'/api/research/pinboard/{note_id}')
    assert response.status_code == 200
    assert response.get_json()['ok'] is True
    assert client.get('/api/research/pinboard').get_json() == []
