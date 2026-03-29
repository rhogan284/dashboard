import json
import time
import uuid
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request

todos_bp = Blueprint('todos', __name__)


def _todos_file() -> Path:
    return Path(current_app.config['DATA_DIR']) / 'todos.json'


def _read() -> list:
    f = _todos_file()
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text())
    except (json.JSONDecodeError, OSError):
        return []


def _write(todos: list) -> None:
    _todos_file().write_text(json.dumps(todos, indent=2))


@todos_bp.route('/api/todos', methods=['GET'])
def get_todos():
    return jsonify(_read())


@todos_bp.route('/api/todos', methods=['POST'])
def create_todo():
    data = request.get_json(silent=True) or {}
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'text required'}), 400
    todo = {
        'id': str(uuid.uuid4()),
        'text': text,
        'completed': False,
        'createdAt': int(time.time() * 1000),
    }
    todos = _read()
    todos.append(todo)
    _write(todos)
    return jsonify(todo), 201


@todos_bp.route('/api/todos/<todo_id>', methods=['PATCH'])
def update_todo(todo_id: str):
    data = request.get_json(silent=True) or {}
    todos = _read()
    for todo in todos:
        if todo['id'] == todo_id:
            if 'completed' in data:
                todo['completed'] = bool(data['completed'])
            _write(todos)
            return jsonify(todo)
    return jsonify({'error': 'not found'}), 404


@todos_bp.route('/api/todos/<todo_id>', methods=['DELETE'])
def delete_todo(todo_id: str):
    todos = _read()
    updated = [t for t in todos if t['id'] != todo_id]
    if len(updated) == len(todos):
        return jsonify({'error': 'not found'}), 404
    _write(updated)
    return Response(status=204)
