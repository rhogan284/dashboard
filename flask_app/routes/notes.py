import os
import tempfile
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

notes_bp = Blueprint('notes', __name__)


def _notes_file() -> Path:
    return Path(current_app.config['DATA_DIR']) / 'notes.txt'


@notes_bp.route('/api/notes', methods=['GET'])
def get_notes():
    f = _notes_file()
    return jsonify({'content': f.read_text() if f.exists() else ''})


@notes_bp.route('/api/notes', methods=['POST'])
def save_notes():
    data = request.get_json(silent=True) or {}
    content = str(data.get('content', ''))
    f = _notes_file()
    tmp_fd, tmp_path = tempfile.mkstemp(dir=f.parent, suffix='.tmp')
    try:
        with os.fdopen(tmp_fd, 'w') as fh:
            fh.write(content)
        os.replace(tmp_path, f)
    except Exception:
        os.unlink(tmp_path)
        raise
    return jsonify({'ok': True})
