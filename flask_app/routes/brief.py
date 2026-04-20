import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, date, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, redirect, request, Response, stream_with_context

from .utils import json_error

brief_bp = Blueprint('brief', __name__)

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/calendar',
]

_REDIRECT_URI = 'http://localhost:8001/api/brief/oauth/callback'
_POST_AUTH_REDIRECT = 'http://localhost:8001/?brief_connected=1'


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


def _gmail_connected() -> bool:
    f = _token_file()
    if not f.exists():
        return False
    try:
        data = json.loads(f.read_text())
        return bool(data.get('refresh_token'))
    except (json.JSONDecodeError, OSError):
        return False


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

    data['gmail_connected'] = _gmail_connected()
    return jsonify(data)


@brief_bp.route('/api/brief/generate', methods=['POST'])
def generate_brief():
    project_root = _project_root()
    script_path = project_root / 'scripts' / 'morning_brief.py'

    if not script_path.exists():
        return json_error(f'script not found: {script_path}', 500, started=False)

    # Prevent concurrent runs
    status_path = _status_file()
    if status_path.exists():
        try:
            current = json.loads(status_path.read_text())
            if current.get('status') == 'running':
                return json_error('already running', 409, started=False)
        except (json.JSONDecodeError, OSError):
            pass

    # Write running status synchronously so SSE sees it immediately
    try:
        fd, tmp = tempfile.mkstemp(dir=status_path.parent)
        with os.fdopen(fd, 'w') as f:
            json.dump({'status': 'running', 'generated_at': None, 'error': None, 'gmail_connected': False}, f)
        os.replace(tmp, status_path)
    except Exception:
        pass

    try:
        subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as exc:
        return json_error(str(exc), 500, started=False)

    return jsonify({'started': True})


@brief_bp.route('/api/brief/auth', methods=['GET'])
def get_auth_url():
    client_secret = _client_secret_file()
    if not client_secret.exists():
        return json_error('client_secret.json not found', 404)

    try:
        from google_auth_oauthlib.flow import Flow

        flow = Flow.from_client_secrets_file(
            str(client_secret),
            scopes=SCOPES,
            redirect_uri=_REDIRECT_URI,
        )
        auth_url, _ = flow.authorization_url(
            access_type='offline',
            prompt='consent',
        )

        # Persist the code verifier so the callback can complete PKCE exchange
        verifier_file = _data_dir() / 'brief_code_verifier.txt'
        if getattr(flow, 'code_verifier', None):
            verifier_file.write_text(flow.code_verifier)
    except Exception as exc:
        return json_error(str(exc), 500)

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
            redirect_uri=_REDIRECT_URI,
        )

        # Restore code verifier if PKCE was used during auth URL generation
        verifier_file = _data_dir() / 'brief_code_verifier.txt'
        if verifier_file.exists():
            flow.code_verifier = verifier_file.read_text().strip()
            verifier_file.unlink(missing_ok=True)

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
        fd, tmp = tempfile.mkstemp(dir=token_file.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(token_data, f)
            os.replace(tmp, token_file)
            os.chmod(token_file, 0o600)
        except Exception:
            os.unlink(tmp)
            raise
    except Exception as exc:
        return json_error(str(exc), 500)

    return redirect(_POST_AUTH_REDIRECT)


@brief_bp.route('/api/brief/stream', methods=['GET'])
def stream_status():
    """SSE endpoint that pushes brief status until generation finishes."""
    def generate():
        last_sent: dict | None = None
        for _ in range(150):  # max ~5 minutes at 2 s intervals
            f = _status_file()
            try:
                data = json.loads(f.read_text()) if f.exists() else {'status': 'never_run', 'generated_at': None, 'error': None}
            except Exception:
                data = {'status': 'never_run', 'generated_at': None, 'error': None}
            data['gmail_connected'] = _gmail_connected()

            if data != last_sent:
                yield f"data: {json.dumps(data)}\n\n"
                last_sent = data

            if data.get('status') != 'running':
                break

            time.sleep(2)

    return Response(
        stream_with_context(generate()),
        content_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@brief_bp.route('/api/logs', methods=['GET'])
def get_logs():
    n = min(int(request.args.get('n', 50)), 500)
    log_file = Path(current_app.config['DATA_DIR']) / 'dashboard.log'
    if not log_file.exists():
        return jsonify({'lines': []})
    try:
        lines = log_file.read_text(errors='replace').splitlines()
        return jsonify({'lines': lines[-n:]})
    except OSError as exc:
        return jsonify({'lines': [], 'error': str(exc)})


@brief_bp.route('/api/brief/preview', methods=['GET'])
def preview_brief():
    md_file = _data_dir() / 'morning_brief.md'

    if md_file.exists():
        try:
            content = md_file.read_text()
        except OSError:
            content = ''
    else:
        content = ''

    return Response(content, content_type='text/plain; charset=utf-8')


def _briefs_dir() -> Path:
    return _data_dir() / 'briefs'


def _brief_config_file() -> Path:
    return _data_dir() / 'brief_config.json'


_SECTION_KEYS = ['gmail', 'calendar', 'markets', 'canvas']
_DEFAULT_CONFIG = {k: True for k in _SECTION_KEYS}


def _load_brief_config() -> dict:
    f = _brief_config_file()
    if not f.exists():
        return dict(_DEFAULT_CONFIG)
    try:
        data = json.loads(f.read_text())
        return {k: bool(data.get(k, True)) for k in _SECTION_KEYS}
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULT_CONFIG)


def _save_brief_config(config: dict):
    f = _brief_config_file()
    f.parent.mkdir(exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=f.parent)
    try:
        with os.fdopen(fd, 'w') as fh:
            json.dump(config, fh)
        os.replace(tmp, f)
    except Exception:
        os.unlink(tmp)
        raise


@brief_bp.route('/api/brief/history', methods=['GET'])
def get_history():
    briefs_dir = _briefs_dir()
    if not briefs_dir.exists():
        return jsonify([])

    files = sorted(briefs_dir.glob('????-??-??.md'), reverse=True)[:5]
    today = datetime.now().date()  # local time — matches how brief files are named

    result = []
    for f in files:
        date_str = f.stem  # 'YYYY-MM-DD'
        try:
            d = date.fromisoformat(date_str)
        except ValueError:
            continue
        delta = (today - d).days
        if delta == 0:
            label = 'Today'
        elif delta == 1:
            label = 'Yesterday'
        else:
            label = d.strftime('%b %-d')
        result.append({'date': date_str, 'label': label})

    return jsonify(result)


@brief_bp.route('/api/brief/archive/<date>', methods=['GET'])
def get_archive(date):
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        return json_error('invalid date format', 400)
    md_file = _briefs_dir() / f'{date}.md'
    if not md_file.exists():
        return json_error(f'no brief for {date}', 404)
    try:
        content = md_file.read_text()
    except OSError as exc:
        return json_error(str(exc), 500)
    return Response(content, content_type='text/plain; charset=utf-8')


@brief_bp.route('/api/brief/config', methods=['GET'])
def get_config():
    return jsonify(_load_brief_config())


@brief_bp.route('/api/brief/config', methods=['PATCH'])
def patch_config():
    updates = request.get_json(silent=True) or {}
    config = _load_brief_config()
    for key, val in updates.items():
        if key in _SECTION_KEYS:
            config[key] = bool(val)
    try:
        _save_brief_config(config)
    except Exception as exc:
        return json_error(str(exc), 500)
    return jsonify(config)
