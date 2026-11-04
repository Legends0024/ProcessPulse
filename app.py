import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, send_from_directory
from config import config
from backend.models import db, init_db
from backend.routes import api_bp
from backend.ml import get_detector

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    HAS_LIMITER = True
except ImportError:
    HAS_LIMITER = False


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    app = Flask(__name__, 
                template_folder="frontend/templates",
                static_folder="frontend/static")
    app.config.from_object(config[config_name])

    setup_logging(app)
    init_db(app)

    if HAS_LIMITER:
        limiter = Limiter(
            get_remote_address,
            app=app,
            default_limits=[app.config["RATE_LIMIT_DEFAULT"]],
            storage_uri="memory://"
        )
        limiter.limit(app.config["RATE_LIMIT_AGENT"])(api_bp)

    app.register_blueprint(api_bp)

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/favicon.ico")
    @app.route("/favicon.svg")
    def favicon():
        return send_from_directory(app.static_folder, "assets/favicon.svg", mimetype="image/svg+xml")

    @app.errorhandler(404)
    def not_found(e):
        try:
            return render_template("404.html"), 404
        except Exception:
            return "404 - Page Not Found", 404

    @app.errorhandler(500)
    def server_error(e):
        try:
            return render_template("500.html"), 500
        except Exception:
            return "Internal Server Error", 500

    with app.app_context():
        detector = get_detector()
        if not detector.is_trained:
            detector.train()

    return app


def setup_logging(app):
    log_level = getattr(logging, app.config.get("LOG_LEVEL", "INFO"))
    log_file = app.config.get("LOG_FILE", "logs/processpulse.log")
    log_directory = os.path.dirname(log_file)
    if log_directory:
        os.makedirs(log_directory, exist_ok=True)

    handler = RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=5)
    handler.setLevel(log_level)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]"
    )
    handler.setFormatter(formatter)

    app.logger.addHandler(handler)
    app.logger.setLevel(log_level)
    app.logger.info("ProcessPulse startup")


app = create_app()

if __name__ == "__main__":
    app.run(
        host=app.config["BACKEND_HOST"],
        port=app.config["BACKEND_PORT"],
        debug=app.config.get("FLASK_DEBUG", True)
    )