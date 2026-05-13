"""MCKO Flask application package."""

from __future__ import annotations

import json

from flask import Flask

from .config import Config
from .db import session
from .db.schema import init_db
from .routes.admin_routes import admin_bp
from .routes.api_routes import api_bp
from .routes.file_routes import file_bp
from .routes.student_routes import student_bp
from .settings import TASK_CONTENTS, TASK_NUMBERS, UPLOAD_DIR


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = Config.SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024

    app.teardown_appcontext(session.close_session)

    @app.context_processor
    def inject_globals():
        return {
            "task_numbers_json": json.dumps(TASK_NUMBERS, ensure_ascii=False),
            "task_contents_json": json.dumps(TASK_CONTENTS, ensure_ascii=False),
        }

    app.register_blueprint(student_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(file_bp)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    return app
