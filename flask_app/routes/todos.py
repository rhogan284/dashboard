import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path

from flask import Blueprint, Response, current_app, jsonify, request

todos_bp = Blueprint('todos', __name__)

_lock = threading.Lock()


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
    f = _todos_file()
    tmp_fd, tmp_path = tempfile.mkstemp(dir=f.parent, suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'w') as fh:
            json.dump(todos, fh, indent=2)
        os.replace(tmp_path, f)
    except Exception:
        os.unlink(tmp_path)
        raise


@todos_bp.route('/api/todos', methods=['GET'])
def get_todos():
    with _lock:
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
    with _lock:
        todos = _read()
        todos.append(todo)
        _write(todos)
    return jsonify(todo), 201


@todos_bp.route('/api/todos/<todo_id>', methods=['PATCH'])
def update_todo(todo_id: str):
    data = request.get_json(silent=True) or {}
    with _lock:
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
    with _lock:
        todos = _read()
        updated = [t for t in todos if t['id'] != todo_id]
        if len(updated) == len(todos):
            return jsonify({'error': 'not found'}), 404
        _write(updated)
    return Response(status=204)
