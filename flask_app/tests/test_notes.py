def test_get_notes_returns_empty_string_when_no_file(client):
    response = client.get('/api/notes')
    assert response.status_code == 200
    assert response.get_json()['content'] == ''


def test_save_notes(client):
    response = client.post('/api/notes', json={'content': 'hello world'})
    assert response.status_code == 200
    assert response.get_json()['ok'] is True


def test_save_and_retrieve_notes(client):
    client.post('/api/notes', json={'content': 'my notes'})
    response = client.get('/api/notes')
    assert response.get_json()['content'] == 'my notes'


def test_save_notes_persists_to_file(client, app):
    client.post('/api/notes', json={'content': 'saved!'})
    notes_file = app.config['DATA_DIR'] / 'notes.txt'
    assert notes_file.read_text() == 'saved!'


def test_overwrite_notes(client):
    client.post('/api/notes', json={'content': 'first'})
    client.post('/api/notes', json={'content': 'second'})
    assert client.get('/api/notes').get_json()['content'] == 'second'
