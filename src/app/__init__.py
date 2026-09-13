"""Flask application factory."""

import os
from datetime import timedelta

from flask import Flask, abort, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from jinja2 import ChoiceLoader, DictLoader

from app.config import Config
from app.db import close_local_connection, ensure_local_db, get_workers_env
from app.templates_inline import TEMPLATES as INLINE_TEMPLATES

csrf = CSRFProtect()
login_manager = LoginManager()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per hour", "20 per minute"],
    storage_uri="memory://",
)

login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"


def _on_workers_runtime() -> bool:
    """True only inside the Cloudflare Workers Python runtime (has `js`)."""
    try:
        import js  # noqa: F401

        return True
    except ImportError:
        return False


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if isinstance(config, dict):
        app.config.update(config)
    elif config is not None:
        app.config.from_object(config)

    secret = app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY")
    if secret:
        app.config["SECRET_KEY"] = secret
    if (
        not app.config.get("SECRET_KEY")
        and not app.config.get("TESTING")
        and not _on_workers_runtime()
    ):
        raise RuntimeError(
            "SECRET_KEY is not set. Export SECRET_KEY or add it to .env "
            "(see .env.example). In production use `wrangler secret put SECRET_KEY`."
        )

    app.permanent_session_lifetime = timedelta(days=7)

    # Filesystem templates win locally; the embedded copy guarantees rendering
    # on Workers even if template files are unavailable on the worker FS.
    app.jinja_loader = ChoiceLoader([app.jinja_loader, DictLoader(INLINE_TEMPLATES)])

    csrf.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)

    from app.routes.admin import admin_bp
    from app.routes.auth import auth_bp
    from app.routes.game import game_bp
    from app.routes.leaderboard import leaderboard_bp

    app.register_blueprint(game_bp)
    app.register_blueprint(leaderboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    @login_manager.user_loader
    def load_user(user_id):
        from app.models import get_user_by_id

        try:
            return get_user_by_id(int(user_id))
        except (TypeError, ValueError):
            return None

    @app.before_request
    def _refresh_secret_from_workers_env():
        """On Workers, secrets arrive via the env binding, not os.environ."""
        env = get_workers_env()
        if env is None:
            return
        worker_secret = getattr(env, "SECRET_KEY", None)
        if worker_secret:
            app.secret_key = worker_secret
        elif not app.config.get("SECRET_KEY"):
            abort(500, description="Server misconfigured: SECRET_KEY missing.")

    @app.after_request
    def _security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; form-action 'self'; "
            "img-src 'self' data:; object-src 'none'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @app.teardown_appcontext
    def _close_db(_exc):
        close_local_connection()

    @app.errorhandler(400)
    def _bad_request(error):
        return render_template(
            "error.html", code=400, message=getattr(error, "description", "Bad request.")
        ), 400

    @app.errorhandler(403)
    def _forbidden(_error):
        return render_template(
            "error.html", code=403, message="You do not have access to this page."
        ), 403

    @app.errorhandler(404)
    def _not_found(_error):
        return render_template("error.html", code=404, message="That page does not exist."), 404

    @app.errorhandler(429)
    def _rate_limited(_error):
        return render_template(
            "error.html", code=429, message="Too many requests. Slow down and retry."
        ), 429

    @app.errorhandler(500)
    def _server_error(_error):
        return render_template(
            "error.html", code=500, message="Something went wrong on our side."
        ), 500

    @app.cli.command("init-db")
    def init_db_command():
        """Create (or reset) the local SQLite database from schema + seed."""
        from app.db import init_local_db

        init_local_db(app.config["SQLITE_PATH"], with_seed=True)
        print(f"Initialised {app.config['SQLITE_PATH']}")

    @app.cli.command("create-admin")
    def create_admin_command():
        """Create an admin user (password is prompted, never stored in git)."""
        import getpass

        import click
        from werkzeug.security import generate_password_hash

        from app.models import create_user, get_user_by_username, set_admin
        from app.services.word_service import validate_username

        username = click.prompt("Admin username", type=str)
        ok, cleaned_or_error = validate_username(username)
        if not ok:
            raise click.ClickException(cleaned_or_error)
        if get_user_by_username(cleaned_or_error) is not None:
            raise click.ClickException("That username is already taken.")
        password = getpass.getpass("Password (min 8 characters): ")
        if len(password) < 8:
            raise click.ClickException("Password must be at least 8 characters.")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            raise click.ClickException("Passwords do not match.")
        create_user(cleaned_or_error, generate_password_hash(password, method="pbkdf2:sha256"))
        set_admin(cleaned_or_error, True)
        print(f"Admin user '{cleaned_or_error}' created.")

    if app.config.get("AUTO_INIT_DB", True) and not _on_workers_runtime():
        ensure_local_db(app.config["SQLITE_PATH"])

    # Avoid unused-import lint noise while keeping request available for blueprints.
    _ = request

    return app
