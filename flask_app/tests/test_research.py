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
