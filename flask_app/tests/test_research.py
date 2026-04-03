import sqlite3
from pathlib import Path


def test_db_tables_created_on_startup(app):
    db_path = Path(app.config['DATA_DIR']) / 'research.db'
    assert db_path.exists(), "research.db should be created on app startup"
    conn = sqlite3.connect(str(db_path))
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert 'research_sessions' in tables
    assert 'research_messages' in tables
    assert 'research_pinboard' in tables
