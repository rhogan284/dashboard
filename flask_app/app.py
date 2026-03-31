import os
from pathlib import Path
from flask import Flask, render_template
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / '.env')


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)

    app.config['DATA_DIR'] = Path(__file__).parent / 'data'

    if config:
        app.config.update(config)

    app.config['DATA_DIR'].mkdir(exist_ok=True)

    from routes.llm import llm_bp
    from routes.notes import notes_bp
    from routes.calendar import calendar_bp
    from routes.brief import brief_bp
    from routes.tasks import tasks_bp

    app.register_blueprint(llm_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(calendar_bp)
    app.register_blueprint(brief_bp)
    app.register_blueprint(tasks_bp)

    @app.route('/')
    def index():
        return render_template(
            'index.html',
            google_client_id=os.getenv('GOOGLE_CLIENT_ID', ''),
        )

    return app


if __name__ == '__main__':
    application = create_app()
    application.run(port=8001, debug=False)
