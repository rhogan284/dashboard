def test_get_todos_returns_empty_list_initially(client):
    response = client.get('/api/todos')
    assert response.status_code == 200
    assert response.get_json() == []


def test_create_todo(client):
    response = client.post('/api/todos', json={'text': 'Buy milk'})
    assert response.status_code == 201
    data = response.get_json()
    assert data['text'] == 'Buy milk'
    assert data['completed'] is False
    assert 'id' in data


def test_create_todo_trims_and_rejects_blank(client):
    response = client.post('/api/todos', json={'text': '   '})
    assert response.status_code == 400


def test_created_todo_appears_in_get(client):
    client.post('/api/todos', json={'text': 'Task A'})
    todos = client.get('/api/todos').get_json()
    assert len(todos) == 1
    assert todos[0]['text'] == 'Task A'


def test_toggle_todo_completed(client):
    todo_id = client.post('/api/todos', json={'text': 'Task'}).get_json()['id']
    response = client.patch(f'/api/todos/{todo_id}', json={'completed': True})
    assert response.status_code == 200
    assert response.get_json()['completed'] is True


def test_toggle_todo_not_found(client):
    response = client.patch('/api/todos/nonexistent', json={'completed': True})
    assert response.status_code == 404


def test_delete_todo(client):
    todo_id = client.post('/api/todos', json={'text': 'Task'}).get_json()['id']
    response = client.delete(f'/api/todos/{todo_id}')
    assert response.status_code == 204
    assert client.get('/api/todos').get_json() == []


def test_delete_todo_not_found(client):
    response = client.delete('/api/todos/nonexistent')
    assert response.status_code == 404


def test_todos_persist_to_file(client, app):
    client.post('/api/todos', json={'text': 'Persisted'})
    todos_file = app.config['DATA_DIR'] / 'todos.json'
    assert todos_file.exists()
    import json
    saved = json.loads(todos_file.read_text())
    assert saved[0]['text'] == 'Persisted'
