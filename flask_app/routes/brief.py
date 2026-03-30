import json
import os
import subprocess
import sys
from pathlib import Path

from flask import Blueprint, current_app, jsonify, redirect, request, Response

brief_bp = Blueprint('brief', __name__)

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/calendar.readonly',
]

REDIRECT_URI = 'http://localhost:8001/api/brief/oauth/callback'


def _data_dir() -> Path:
    return Path(current_app.config['DATA_DIR'])


def _status_file() -> Path:
    return _data_dir() / 'brief_status.json'


def _token_file() -> Path:
    return _data_dir() / 'brief_token.json'


def _client_secret_file() -> Path:
    return _data_dir() / 'client_secret.json'


def _project_root() -> Path:
    # flask_app/ is one level below project root
    return Path(current_app.root_path).parent


@brief_bp.route('/api/brief/status', methods=['GET'])
def get_status():
    default = {
        'status': 'never_run',
        'generated_at': None,
        'draft_id': None,
        'error': None,
        'gmail_connected': False,
    }

    f = _status_file()
    if f.exists():
        try:
            data = json.loads(f.read_text())
        except (json.JSONDecodeError, OSError):
            data = dict(default)
    else:
        data = dict(default)

    data['gmail_connected'] = _token_file().exists()
    return jsonify(data)


@brief_bp.route('/api/brief/generate', methods=['POST'])
def generate_brief():
    project_root = _project_root()
    script_path = project_root / 'scripts' / 'morning_brief.py'

    try:
        subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(project_root),
        )
    except Exception as exc:
        return jsonify({'started': False, 'error': str(exc)}), 500

    return jsonify({'started': True})


@brief_bp.route('/api/brief/auth', methods=['GET'])
def get_auth_url():
    client_secret = _client_secret_file()
    if not client_secret.exists():
        return jsonify({'error': 'client_secret.json not found'}), 404

    try:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_secrets_file(
            str(client_secret),
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI,
        )
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            prompt='consent',
        )
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

    return jsonify({'auth_url': auth_url})


@brief_bp.route('/api/brief/oauth/callback', methods=['GET'])
def oauth_callback():
    code = request.args.get('code', '')
    client_secret = _client_secret_file()

    try:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_secrets_file(
            str(client_secret),
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials

        token_data = {
            'token': creds.token,
            'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri,
            'client_id': creds.client_id,
            'client_secret': creds.client_secret,
            'scopes': list(creds.scopes) if creds.scopes else SCOPES,
        }

        token_file = _token_file()
        token_file.parent.mkdir(exist_ok=True)
        token_file.write_text(json.dumps(token_data))
        os.chmod(token_file, 0o600)
    except Exception as exc:
        return jsonify({'error': str(exc)}), 500

    return redirect('http://localhost:8001/?brief_connected=1')


@brief_bp.route('/api/brief/preview', methods=['GET'])
def preview_brief():
    preview_file = _data_dir() / 'morning_brief_preview.html'

    if preview_file.exists():
        try:
            html = preview_file.read_text()
        except OSError:
            html = '<html><body style="font-family:sans-serif;padding:40px;color:#666"><p>No brief generated yet.</p></body></html>'
    else:
        html = '<html><body style="font-family:sans-serif;padding:40px;color:#666"><p>No brief generated yet.</p></body></html>'

    return Response(html, content_type='text/html')
