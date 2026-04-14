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


# ── Tool handlers ─────────────────────────────────────────────────────────────

import sqlite3 as _sqlite3

from routes.research import _query_portfolio, _read_local_file


def test_query_portfolio_missing_db(tmp_path):
    import routes.research as rr
    rr.PORTFOLIO_DB_PATH = str(tmp_path / 'nonexistent.db')
    result = rr._query_portfolio({'operation': 'holdings'})
    assert 'Portfolio query error' in result


def test_query_portfolio_holdings(tmp_path):
    db_path = tmp_path / 'portfolio.db'
    conn = _sqlite3.connect(str(db_path))
    conn.execute("""CREATE TABLE holdings (
        ticker TEXT, platform TEXT, units REAL, avg_cost REAL, sleeve TEXT
    )""")
    conn.execute("INSERT INTO holdings VALUES ('AAPL', 'IB', 10, 150.0, 'Core')")
    conn.commit()
    conn.close()

    import routes.research as rr
    rr.PORTFOLIO_DB_PATH = str(db_path)

    result = rr._query_portfolio({'operation': 'holdings'})
    assert 'AAPL' in result
    assert 'IB' in result


def test_read_local_file_csv(tmp_path):
    csv_path = tmp_path / 'test.csv'
    csv_path.write_text("ticker,value\nAAPL,100\nGOOG,200\n")

    from routes.research import _read_local_file
    result = _read_local_file({'path': str(csv_path)})
    assert 'AAPL' in result
    assert 'GOOG' in result


def test_read_local_file_missing():
    from routes.research import _read_local_file
    result = _read_local_file({'path': '/tmp/does_not_exist_xyz.csv'})
    assert 'not found' in result.lower()


def test_read_local_file_unsupported_type(tmp_path):
    p = tmp_path / 'file.txt'
    p.write_text('hello')
    from routes.research import _read_local_file
    result = _read_local_file({'path': str(p)})
    assert 'Unsupported' in result


# ── Market context helper ─────────────────────────────────────────────────────

def test_build_market_context_returns_formatted_block():
    from routes.research import _build_market_context
    mock_info = {
        'regularMarketPrice': 5000.0,
        'regularMarketChangePercent': -1.5,
    }
    with patch('yfinance.Ticker') as mock_ticker_class:
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info
        mock_ticker_class.return_value = mock_ticker
        result = _build_market_context()
    assert '## Market Context' in result
    assert 'S&P 500' in result
    assert '5000' in result
    assert '-1.50%' in result


def test_build_market_context_handles_yfinance_failure():
    from routes.research import _build_market_context
    with patch('yfinance.Ticker', side_effect=Exception('network error')):
        result = _build_market_context()
    assert '## Market Context' in result
    assert 'unavailable' in result


# ── Chat endpoint ─────────────────────────────────────────────────────────────

from unittest.mock import MagicMock, patch


def _mock_ollama_response(content='Test response'):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        'message': {'role': 'assistant', 'content': content, 'tool_calls': None}
    }
    return mock_resp


def test_chat_requires_session_id_and_messages(client):
    response = client.post('/api/research/chat', json={})
    assert response.status_code == 400


def test_chat_streams_ndjson(client):
    session_id = client.post('/api/research/sessions').get_json()['id']
    with patch('routes.research.httpx.post', return_value=_mock_ollama_response('Hello!')):
        response = client.post('/api/research/chat', json={
            'session_id': session_id,
            'messages': [{'role': 'user', 'content': 'Hi'}],
            'think': False,
        })
    assert response.status_code == 200
    assert response.content_type == 'application/x-ndjson'
    lines = [l for l in response.data.decode().strip().split('\n') if l]
    assert len(lines) >= 1
    import json as _json
    data = _json.loads(lines[-1])
    assert 'message' in data
    assert data['message']['content'] == 'Hello!'


def test_chat_persists_messages_to_db(client):
    session_id = client.post('/api/research/sessions').get_json()['id']
    with patch('routes.research.httpx.post', return_value=_mock_ollama_response('World!')):
        client.post('/api/research/chat', json={
            'session_id': session_id,
            'messages': [{'role': 'user', 'content': 'Hello'}],
        })
    session = client.get(f'/api/research/sessions/{session_id}').get_json()
    roles = [m['role'] for m in session['messages']]
    assert 'user' in roles
    assert 'assistant' in roles


# ── Portfolio review endpoint ─────────────────────────────────────────────────

import httpx as _httpx


def test_review_returns_503_when_portfolio_app_unreachable(client):
    with patch('routes.research.httpx.get', side_effect=_httpx.ConnectError('refused')):
        response = client.post('/api/research/review')
    assert response.status_code == 503
    data = response.get_json()
    assert 'not reachable' in data['error'].lower()


def test_review_creates_session_and_streams_response(client):
    mock_get = MagicMock()
    mock_get.raise_for_status = MagicMock()
    mock_get.json.return_value = {'markdown': '# Portfolio Review\nTest content'}

    import json as _json
    with patch('routes.research.httpx.get', return_value=mock_get), \
         patch('routes.research.httpx.post', return_value=_mock_ollama_response('Here are my recommendations.')), \
         patch('routes.research._build_market_context', return_value='## Market Context\n- VIX: 18\n'):
        response = client.post('/api/research/review')
        body = response.data

    assert response.status_code == 200
    assert response.content_type == 'application/x-ndjson'
    lines = [l for l in body.decode().strip().split('\n') if l]
    first = _json.loads(lines[0])
    assert 'session_id' in first
    last = _json.loads(lines[-1])
    assert 'message' in last
    assert 'recommendations' in last['message']['content'].lower()


def test_review_persists_user_and_assistant_messages(client):
    mock_get = MagicMock()
    mock_get.raise_for_status = MagicMock()
    mock_get.json.return_value = {'markdown': '# Review\nContent'}

    import json as _json
    with patch('routes.research.httpx.get', return_value=mock_get), \
         patch('routes.research.httpx.post', return_value=_mock_ollama_response('Analysis complete.')), \
         patch('routes.research._build_market_context', return_value=''):
        response = client.post('/api/research/review')
        body = response.data

    lines = [l for l in body.decode().strip().split('\n') if l]
    session_id = _json.loads(lines[0])['session_id']

    session = client.get(f'/api/research/sessions/{session_id}').get_json()
    roles = [m['role'] for m in session['messages']]
    assert 'user' in roles
    assert 'assistant' in roles


def test_review_session_title_is_portfolio_review(client):
    mock_get = MagicMock()
    mock_get.raise_for_status = MagicMock()
    mock_get.json.return_value = {'markdown': '# Review'}

    import json as _json
    with patch('routes.research.httpx.get', return_value=mock_get), \
         patch('routes.research.httpx.post', return_value=_mock_ollama_response('Done.')), \
         patch('routes.research._build_market_context', return_value=''):
        response = client.post('/api/research/review')
        body = response.data

    lines = [l for l in body.decode().strip().split('\n') if l]
    session_id = _json.loads(lines[0])['session_id']

    sessions = client.get('/api/research/sessions').get_json()
    match = next((s for s in sessions if s['id'] == session_id), None)
    assert match is not None
    assert match['title'] == 'Portfolio Review'


# ── Summarise + title endpoints ───────────────────────────────────────────────

def test_summarise_empty_session_returns_ok(client):
    session_id = client.post('/api/research/sessions').get_json()['id']
    response = client.post(f'/api/research/sessions/{session_id}/summarise')
    assert response.status_code == 200
    data = response.get_json()
    assert data['ok'] is True
    assert data['summary'] == ''


def test_summarise_session_calls_ollama_and_saves(client):
    session_id = client.post('/api/research/sessions').get_json()['id']
    with patch('routes.research.httpx.post', return_value=_mock_ollama_response('Response text')):
        client.post('/api/research/chat', json={
            'session_id': session_id,
            'messages': [{'role': 'user', 'content': 'Analyse AAPL'}],
        })
    with patch('routes.research.httpx.post', return_value=_mock_ollama_response('Summary of AAPL research.')):
        response = client.post(f'/api/research/sessions/{session_id}/summarise')
    assert response.status_code == 200
    assert response.get_json()['ok'] is True
    session = client.get(f'/api/research/sessions/{session_id}').get_json()
    assert session['auto_summary'] == 'Summary of AAPL research.'


def test_get_title_returns_new_session_for_empty(client):
    session_id = client.post('/api/research/sessions').get_json()['id']
    response = client.get(f'/api/research/sessions/{session_id}/title')
    assert response.status_code == 200
    assert response.get_json()['title'] == 'New session'


def test_get_title_calls_ollama_and_saves(client):
    session_id = client.post('/api/research/sessions').get_json()['id']
    with patch('routes.research.httpx.post', return_value=_mock_ollama_response('AAPL earnings analysis')):
        client.post('/api/research/chat', json={
            'session_id': session_id,
            'messages': [{'role': 'user', 'content': 'What are AAPL earnings?'}],
        })
    with patch('routes.research.httpx.post', return_value=_mock_ollama_response('AAPL Q1 Earnings Deep Dive')):
        response = client.get(f'/api/research/sessions/{session_id}/title')
    assert response.status_code == 200
    assert response.get_json()['title'] == 'AAPL Q1 Earnings Deep Dive'


# ── Research memory helper ────────────────────────────────────────────────────

def test_read_memory_returns_file_content(tmp_path):
    mem_file = tmp_path / 'research_memory'
    mem_file.write_text('Purpose & context\nRyan is a 22-year-old investor.', encoding='utf-8')
    with patch('routes.research.RESEARCH_MEMORY_PATH', new=mem_file):
        from routes.research import _read_memory
        result = _read_memory()
    assert 'Ryan is a 22-year-old investor.' in result


def test_read_memory_returns_empty_string_when_file_missing(tmp_path):
    missing = tmp_path / 'no_such_file'
    with patch('routes.research.RESEARCH_MEMORY_PATH', new=missing):
        from routes.research import _read_memory
        result = _read_memory()
    assert result == ''
