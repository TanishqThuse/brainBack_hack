"""
backend/app.py
--------------
Flask application factory.
Routes are thin — all business logic lives in the pipeline.
"""

import logging
from flask import Flask
from backend.routes.voice  import voice_bp
from backend.routes.status import status_bp
from backend.routes.ui     import ui_bp

log = logging.getLogger("bankbot.app")


def create_app(cfg) -> Flask:
    """
    Create and configure the Flask application.
    cfg must have pipeline/session singletons attached by startup.py.
    """
    app = Flask(
        __name__,
        template_folder="../frontend/templates",
        static_folder="../frontend/static",
    )
    app.secret_key = cfg.FLASK_SECRET

    # Make cfg available to all blueprints via app.config
    app.config["BANKBOT_CFG"] = cfg

    # Register route blueprints
    app.register_blueprint(ui_bp)
    app.register_blueprint(voice_bp,  url_prefix="/api")
    app.register_blueprint(status_bp, url_prefix="/api")

    log.info("Flask app created with blueprints: ui, voice, status")
    return app
