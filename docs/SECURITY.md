# Security - EF101-P01 Hangman

One row per hardening item (§3.5 of the build spec), each with evidence.

| # | Control | Evidence |
|---|---|---|
| 1 | Unused packages removed | Runtime closure is exactly Flask + Flask-Login + Flask-WTF + Flask-Limiter + workers-runtime-sdk (the Workers Python adapter, which provides the `workers` module) and their hard requirements (18 pins in `docs/requirements-pinned.txt`, generated from a clean venv). Dev-only tools (`pytest`, `ruff`, `bandit`, `wordfreq`) live under `[project.optional-dependencies] dev` and are never deployed. The closure is vendored as pure-Python source under `src/python_modules/` (301 files, 0.84 MB gzipped, no binaries; regenerate with `scripts/vendor_python_modules.py`), so the deploy bundle is self-contained. |
| 2 | No debug mode | `run.py` uses `debug=False`; no `app.run(debug=True)` anywhere (`grep -rn "debug=True" app src run.py` is empty); `FLASK_ENV=production` in `wrangler.jsonc`. |
| 3 | Git history scanned for secrets | `git log` reviewed; `grep -rniE "password\s*=|secret_key\s*=\s*['\"][^'\"]|api[_-]?key|token\s*=" --include="*.py" app src scripts` finds only config plumbing and the documented `test-secret-key` dummy (excluded from scans via justified `nosec`). No `.env`, tokens, or hashes of real passwords are committed. |
| 4 | Rate limiting on `/login`, `/submit-score`, `/new` | Flask-Limiter: login/register 5/min, submit-score 10/min, new 30/min, guess 60/min, hint 30/min (`src/app/routes/*.py`). Test `test_login_is_rate_limited` asserts the 6th rapid login returns 429. |
| 5 | Admin routes protected | `/admin/*` requires login + `is_admin` (`admin_required` in `src/app/routes/admin.py`). Tests: anonymous 302 to login, non-admin 403, admin 200. |
| 6 | Passwords hashed `pbkdf2:sha256` | `generate_password_hash(pw, method="pbkdf2:sha256")` in `src/app/routes/auth.py` and the `create-admin` CLI. Test asserts stored hashes start with `pbkdf2:sha256` and never contain the password. |
| 7 | No API keys in source; `.env` ignored | `.gitignore` lists `.env`, `.dev.vars`, `*.db`, `instance/`, `__pycache__/`, `python_modules/`; only `.env.example` (placeholder) is committed. `git status --short` shows no secret files. |
| 8 | Cookies `HttpOnly`, `Secure`, `SameSite=Lax` | `SESSION_COOKIE_*` config + explicit flags on `hangman_game` (`src/app/routes/game.py::_cookie_kwargs`). Live header: `Set-Cookie: hangman_game=...; Secure; HttpOnly; Path=/; SameSite=Lax`. Tests assert flags on both cookies. |
| 9 | Dependencies pinned and audited | Exact pins in `pyproject.toml` + `docs/requirements-pinned.txt`; `pip-audit -r docs/requirements-pinned.txt` → "No known vulnerabilities found". |
| 10 | Forms sanitized + validated | Flask-WTF CSRF on all POSTs; `validate_player_name` / `validate_username` / `validate_word` allow-lists (`src/app/services/word_service.py`); difficulty/category choices are allow-listed in routes. |
| 11 | XSS protection | Jinja2 auto-escape everywhere; no `|safe` on user input (`grep -rn "|safe" src/app/templates` is empty); strict CSP header (`default-src 'self'`, no inline scripts/styles). Test inserts `<script>alert(1)</script>` directly in the DB and asserts the leaderboard renders it escaped. |
| 12 | Missing secret refuses to start | `create_app()` raises `RuntimeError` without `SECRET_KEY` (except tests/Workers, where a `before_request` hook resolves it from the Worker env or fails closed with 500). Verified: `SECRET_KEY= python -c "from app import create_app; create_app()"` raises. |
| 13 | No exposed files | Flask serves only `src/app/static/`; `.env`, `*.db`, `__pycache__`, `.git` are git-ignored and outside the static dir; unknown paths return the 404 page (tested). |
| 14 | CORS locked down | No CORS extension installed; responses carry no `Access-Control-Allow-*` headers (same-origin only). Verified in live header dump. |
| 15 | Security headers | `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Strict-Transport-Security`, `Permissions-Policy` set in `after_request` (`src/app/__init__.py`). Test + live `curl -sI` both confirm. |
| 16 | Prepared statements only | All SQL in `src/app/models.py` / `src/app/db.py` uses `?` placeholders with bound params; static test asserts no f-string/`%` SQL; D1 path uses `.prepare().bind()`. |

## Scan summary (this environment)

- `ruff check` + `ruff format --check`: pass (33 first-party files; vendored code excluded).
- `bandit -r src -x '*/python_modules/*'`: 0 issues (2 justified `nosec`: test-only dummy secret,
  gameplay `random.choice`; session IDs use `secrets`).
- `pip-audit -r docs/requirements-pinned.txt`: no known vulnerabilities.
- `pytest`: 81/81 pass, including 14 security tests.

## Accepted risks

1. Flask-Limiter uses in-memory storage, so on Workers each isolate enforces
   limits independently. Fine against casual abuse; not a DDoS defence.
2. Lost games may be submitted with score 0 (transparent; shows as "Lost" 0).
3. The daily challenge word is fixed per day but replayable; attempts are not
   limited to one play per day.
