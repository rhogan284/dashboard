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
    content = data.get('content', '')
    _notes_file().write_text(content)
    return jsonify({'ok': True})
