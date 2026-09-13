"""Application configuration.

Secrets come from the environment (local `.env` file or Cloudflare Wrangler
secrets in production). The app refuses to start without SECRET_KEY, except
under TESTING or on the Workers runtime where the secret is read per-request
from the workers env (see app/__init__.py `_refresh_secret_from_workers_env`).
"""

import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTANCE_DIR = os.path.join(ROOT_DIR, "instance")


def _load_dotenv() -> None:
    """Minimal `.env` loader (KEY=VALUE lines). Avoids a python-dotenv dependency."""
    path = os.path.join(ROOT_DIR, ".env")
    if not os.path.isfile(path):
        return
    try:
        with open(path, encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        return  # missing/unreadable .env is fine; env vars may be set directly


_load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    TESTING = False
    AUTO_INIT_DB = True
    SQLITE_PATH = os.environ.get("SQLITE_PATH") or os.path.join(INSTANCE_DIR, "hangman.db")

    # Secure session cookies (all environments, incl. tests).
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Flask-WTF CSRF + input validation.
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    # Flask-Limiter (in-memory storage; per-isolate on Workers - see docs).
    RATELIMIT_ENABLED = True

    # Reject absurdly large request bodies early.
    MAX_CONTENT_LENGTH = 64 * 1024


class TestingConfig(Config):
    TESTING = True
    # Dummy value for automated tests only; never used in production.
    SECRET_KEY = "test-secret-key"  # nosec B105
    AUTO_INIT_DB = False
    RATELIMIT_ENABLED = False
    WTF_CSRF_ENABLED = False
