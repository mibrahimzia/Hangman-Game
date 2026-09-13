# EF101-P01 - Web-Based Hangman Game

Python + Flask hangman with a persistent leaderboard on Cloudflare D1.
7,105-word server-side vocabulary, three difficulties, four categories, hints,
daily challenge, optional accounts with profiles, and an admin dashboard.
The answer is never sent to the browser while playing (server-side sessions).

## Deployed URL

> `https://hangman.REPLACE_ME.workers.dev`
> (Run the Deploy section below with the team's Cloudflare account, then
> replace this line with the real URL. Verify from a second device.)

## Quick start (local)

Requirements: Python 3.11+.

```bash
python -m venv .venv
.venv/bin/pip install Flask Flask-Login Flask-WTF Flask-Limiter
# or: .venv/bin/pip install -r docs/requirements-pinned.txt
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
.venv/bin/python run.py        # serves http://127.0.0.1:5000
```

The SQLite database self-initialises on first run from `schema.sql` +
`db_init.sql`. No other setup needed. For tests and lint:

```bash
.venv/bin/pip install pytest ruff bandit pip-audit
SECRET_KEY=test .venv/bin/python -m pytest -v        # 74 tests
.venv/bin/python -m ruff check app src scripts tests run.py
.venv/bin/bandit -r app src
.venv/bin/pip-audit -r docs/requirements-pinned.txt
```

## Rebuilding the seed data

```bash
.venv/bin/pip install wordfreq     # build-time only, never deployed
.venv/bin/python scripts/seed_words.py   # writes db_init.sql (words)
.venv/bin/python scripts/seed_demo.py    # appends demo scores
```

## Creating an admin

Locally: `.venv/bin/flask --app run create-admin USERNAME`
(password is prompted, never stored in git).

In production (D1), generate a hash locally, then insert:

```bash
.venv/bin/python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('CHOOSE-A-STRONG-PASSWORD', method='pbkdf2:sha256'))"
wrangler d1 execute hangman-db --command="INSERT INTO users (username, password_hash, is_admin, created_at) VALUES ('admin', '<HASH>', 1, '2026-09-13T00:00:00.000000Z')"
```

## Deploy (Cloudflare Workers + D1)

```bash
uv tool install workers-py          # or: pip install workers-py
wrangler login
pywrangler sync
wrangler d1 create hangman-db       # paste database_id into wrangler.jsonc
wrangler d1 execute hangman-db --file=./schema.sql
wrangler d1 execute hangman-db --file=./db_init.sql
wrangler secret put SECRET_KEY
pywrangler deploy                   # prints the public workers.dev URL
```

Verify from a second device (phone on mobile data): play a game, submit a
score, check `/leaderboard`. Then record the URL at the top of this file.

Backup demo plan (offline evaluation): run locally as in Quick start and show
the `pytest -v` output in `docs/REPORT.md` section 7.

## Docs

- `docs/REPORT.md` - full project report (objectives, design, testing, results)
- `docs/ARCHITECTURE.md` - system diagram and request flows
- `docs/SECURITY.md` - security controls with evidence
- `docs/VIVA.md` - viva questions with defensible answers
- `docs/AI_DISCLOSURE.md` - libraries, data sources, AI assistance
- `docs/CONTRIBUTIONS.md` - three-member contribution table

## License

MIT (see `LICENSE`). Icons: Lucide, ISC license
(`app/static/icons/LICENSE`).
