import json
import os
import time
from pathlib import Path

import httpx
from flask import Blueprint, current_app, jsonify, request

from .utils import json_error

calendar_bp = Blueprint('calendar', __name__)

CALENDAR_API = 'https://www.googleapis.com/calendar/v3'
API_KEY = os.getenv('GOOGLE_API_KEY', '')


def _token_file() -> Path:
    return Path(current_app.config['DATA_DIR']) / 'gcal_token.json'


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


@calendar_bp.route('/api/calendar/token', methods=['POST'])
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


@calendar_bp.route('/api/calendar/events', methods=['GET'])
def get_events():
    token = _load_token()
    if not token:
        return json_error('not_connected', 401)

    now = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    end = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + 14 * 86400))

    response = httpx.get(
        f'{CALENDAR_API}/calendars/primary/events',
        params={
            'key': API_KEY,
            'timeMin': now,
            'timeMax': end,
            'singleEvents': 'true',
            'orderBy': 'startTime',
            'maxResults': '50',
        },
        headers={'Authorization': f'Bearer {token["access_token"]}'},
    )

    if not response.is_success:
        return json_error('calendar_api_error', 502, status=response.status_code)

    return jsonify(response.json().get('items', []))
