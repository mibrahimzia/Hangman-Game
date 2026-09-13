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
SECRET_KEY=test .venv/bin/python -m pytest -v        # 81 tests
.venv/bin/python -m ruff check .
.venv/bin/bandit -r src -x '*/python_modules/*'      # first-party code only
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

### Option B - Cloudflare dashboard (connected repo / Workers Builds)

Third-party dependencies are vendored into the repo as pure-Python source
under `src/python_modules/` (regenerate with
`python3 scripts/vendor_python_modules.py` after changing pins), so the
default build settings work with no extra steps - build command
`pip install .`, deploy command `npx wrangler versions upload`.
`pywrangler sync` is NOT required for deploys (it remains useful for local
`wrangler dev` iterations).

- Production branch: the connected branch must contain `wrangler.jsonc`,
  `src/worker.py`, and `pyproject.toml` - building a branch without them
  fails with "Could not detect a directory containing static files".
  (`main` only has these after the PR is merged; building the feature
  branch directly also works.)
- Before the first deploy, apply the schema + seed to D1 from any machine
  with `wrangler` logged in:
  `wrangler d1 execute hangman-db --file=./schema.sql`
  `wrangler d1 execute hangman-db --file=./db_init.sql`
  (If your D1 database has a different name than `hangman-db`, update
  `database_name` in `wrangler.jsonc` to match.)
- Set the secret: Worker → Settings → Variables and Secrets → add a
  **Secret** named `SECRET_KEY` with a long random value
  (or `wrangler secret put SECRET_KEY` from the CLI).

Backup demo plan (offline evaluation): run locally as in Quick start and show
the `pytest -v` output in `docs/REPORT.md` section 7.

### Local Workers emulation (optional)

Runs the real `workerd` runtime with a local D1 on your machine:

```bash
python3 -m pywrangler sync          # vendors deps into ./python_modules/
echo 'SECRET_KEY=local-dev-only-change-me' > .dev.vars   # git-ignored
npx wrangler d1 execute hangman-db --local --file=./schema.sql
npx wrangler d1 execute hangman-db --local --file=./db_init.sql
npx wrangler dev --local            # serves http://127.0.0.1:8787
```

## Docs

- `docs/REPORT.md` - full project report (objectives, design, testing, results)
- `docs/ARCHITECTURE.md` - system diagram and request flows
- `docs/SECURITY.md` - security controls with evidence
- `docs/VIVA.md` - viva questions with defensible answers
- `docs/AI_DISCLOSURE.md` - libraries, data sources, AI assistance
- `docs/CONTRIBUTIONS.md` - three-member contribution table

## License

MIT (see `LICENSE`). Icons: Lucide, ISC license
(`src/app/static/icons/LICENSE`).
