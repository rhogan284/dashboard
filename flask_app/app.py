import logging
import os
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from flask import Flask, render_template
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')


def _configure_logging(data_dir: Path) -> None:
    log_file = data_dir / 'dashboard.log'
    handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # Also keep stderr output during development
    logging.getLogger('werkzeug').setLevel(logging.WARNING)


def _preload_omlx():
    """Send a 1-token request on startup so the model is loaded before the first real request."""
    import time
    import httpx
    time.sleep(3)
    try:
        httpx.post(
            f"{os.getenv('OMLX_BASE_URL', 'http://localhost:8002')}/v1/chat/completions",
            headers={'Authorization': f"Bearer {os.getenv('OMLX_API_KEY', '')}"},
            json={
                'model': os.getenv('OMLX_MODEL', 'gemma-4-26b-a4b-it-4bit'),
                'messages': [{'role': 'user', 'content': 'hi'}],
                'max_tokens': 1,
            },
            timeout=120.0,
        )
    except Exception:
        pass
    finally:
        from routes.research import _set_bg_status
        _set_bg_status('idle', 'Model ready')


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)

    app.config['DATA_DIR'] = Path(__file__).parent / 'data'

    if config:
        app.config.update(config)

    app.config['DATA_DIR'].mkdir(exist_ok=True)
    _configure_logging(app.config['DATA_DIR'])

    from routes.llm import llm_bp
    from routes.calendar import calendar_bp
    from routes.brief import brief_bp
    from routes.tasks import tasks_bp
    from routes.research import research_bp
    from routes.canvas import canvas_bp
    from routes.weather import weather_bp

    app.register_blueprint(llm_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(brief_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(research_bp)
    app.register_blueprint(canvas_bp)
    app.register_blueprint(weather_bp)

    if not app.config.get('TESTING'):
        threading.Thread(target=_preload_omlx, daemon=True).start()

    @app.route('/')
    def index():
        return render_template(
            'index.html',
            google_client_id=os.getenv('GOOGLE_CLIENT_ID', ''),
        )

    return app


if __name__ == '__main__':
    application = create_app()
    application.run(port=8001, debug=False, threaded=True)
