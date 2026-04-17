import json
import os
import time
from pathlib import Path

import httpx
from flask import Blueprint, Response, current_app, jsonify, request

from .utils import json_error

tasks_bp = Blueprint('tasks', __name__)

TASKS_API = 'https://tasks.googleapis.com/tasks/v1'
TASKLIST = '@default'


def _token_file() -> Path:
    return Path(current_app.config['DATA_DIR']) / 'gtasks_token.json'


def _load_token() -> dict | None:
    f = _token_file()
    if not f.exists():
        return None
    try:
        data = json.loads(f.read_text())
        if time.time() * 1000 > data.get('expires_at', 0):
            f.unlink(missing_ok=True)
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _auth_headers(token: dict) -> dict:
    return {'Authorization': f'Bearer {token["access_token"]}'}


def _normalise(task: dict) -> dict:
    """Map Google Task fields to the shape the frontend expects."""
    # Google returns due as a full RFC 3339 timestamp; strip to YYYY-MM-DD
    due_raw = task.get('due', '')
    due_date = due_raw[:10] if due_raw else None
    return {
        'id': task['id'],
        'text': task.get('title', ''),
        'completed': task.get('status') == 'completed',
        'due_date': due_date,
    }


@tasks_bp.route('/api/tasks/token', methods=['POST'])
def save_token():
    data = request.get_json(silent=True) or {}
    token_data = {
        'access_token': data.get('access_token', ''),
        'expires_at': int(time.time() * 1000) + int(data.get('expires_in', 3600)) * 1000,
    }
    f = _token_file()
    f.parent.mkdir(exist_ok=True)
    f.write_text(json.dumps(token_data))
    os.chmod(f, 0o600)
    return jsonify({'ok': True})


@tasks_bp.route('/api/tasks', methods=['GET'])
def get_tasks():
    token = _load_token()
    if not token:
        return json_error('not_connected', 401)

    resp = httpx.get(
        f'{TASKS_API}/lists/{TASKLIST}/tasks',
        params={'showCompleted': 'true', 'showHidden': 'true', 'maxResults': '100'},
        headers=_auth_headers(token),
    )
    if not resp.is_success:
        return json_error('tasks_api_error', 502, status=resp.status_code)

    tasks = resp.json().get('items', [])
    return jsonify([_normalise(t) for t in tasks])


@tasks_bp.route('/api/tasks', methods=['POST'])
def create_task():
    token = _load_token()
    if not token:
        return json_error('not_connected', 401)

    data = request.get_json(silent=True) or {}
    text = data.get('text', '').strip()
    if not text:
        return json_error('text required', 400)

    body = {'title': text, 'status': 'needsAction'}
    due_date = data.get('due_date', '').strip()  # expects YYYY-MM-DD
    if due_date:
        body['due'] = f'{due_date}T00:00:00.000Z'

    resp = httpx.post(
        f'{TASKS_API}/lists/{TASKLIST}/tasks',
        json=body,
        headers=_auth_headers(token),
    )
    if not resp.is_success:
        return json_error('tasks_api_error', 502, status=resp.status_code)

    return jsonify(_normalise(resp.json())), 201


@tasks_bp.route('/api/tasks/<task_id>', methods=['PATCH'])
def update_task(task_id: str):
    token = _load_token()
    if not token:
        return json_error('not_connected', 401)

    data = request.get_json(silent=True) or {}
    completed = bool(data.get('completed'))
    body = {'status': 'completed' if completed else 'needsAction'}
    if not completed:
        body['completed'] = None  # clear the completed timestamp

    resp = httpx.patch(
        f'{TASKS_API}/lists/{TASKLIST}/tasks/{task_id}',
        json=body,
        headers=_auth_headers(token),
    )
    if not resp.is_success:
        return json_error('tasks_api_error', 502, status=resp.status_code)

    return jsonify(_normalise(resp.json()))


@tasks_bp.route('/api/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id: str):
    token = _load_token()
    if not token:
        return json_error('not_connected', 401)

    resp = httpx.delete(
        f'{TASKS_API}/lists/{TASKLIST}/tasks/{task_id}',
        headers=_auth_headers(token),
    )
    if resp.status_code == 404:
        return json_error('not found', 404)
    if not resp.is_success:
        return json_error('tasks_api_error', 502, status=resp.status_code)

    return Response(status=204)
