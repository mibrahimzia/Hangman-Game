# AI, tools, library, and data disclosure - EF101-P01

## Runtime libraries (shipped to Workers via `pywrangler`)

All pinned exactly in `pyproject.toml`; full transitive closure (17 packages)
in `docs/requirements-pinned.txt`; `pip-audit` reports no known
vulnerabilities.

| Package | Version | License | Purpose |
|---|---|---|---|
| Flask | 3.1.3 | BSD-3 | Web framework (WSGI, served via `workers.wsgi`) |
| Flask-Login | 0.6.3 | MIT | Optional auth sessions |
| Flask-WTF | 1.3.0 | BSD-3 | CSRF protection |
| Flask-Limiter | 4.1.1 | MIT | Rate limiting (in-memory storage) |
| Jinja2 | 3.1.6 | BSD-3 | Templates (auto-escaping) |
| Werkzeug | 3.1.8 | BSD-3 | WSGI utilities, password hashing |
| WTForms | 3.2.2 | BSD-3 | Form handling (via Flask-WTF) |
| click, itsdangerous, MarkupSafe, limits, packaging, typing_extensions, ordered-set, wrapt, Deprecated, blinker | pinned | various BSD/MIT/Apache | Transitive dependencies of the above |

## Development-only tools (never deployed)

`pytest` (tests), `ruff` (lint/format), `bandit` (security scan), `pip-audit`
(dependency audit), `wordfreq` (one-off vocabulary generation),
`workers-py`/`pywrangler` (Workers toolchain validation).

## Data sources

- General vocabulary: 50,000 most frequent English words from the `wordfreq`
  package (MIT license, https://github.com/rspeer/wordfreq), filtered to
  lowercase ASCII alpha, length 3-12.
- Category vocabulary: original hand-curated lists (Animals, Geography,
  Science, Sports) in `scripts/seed_words.py`.
- Icons: Lucide `lucide-static` v1.45.0 (ISC license); a 21-file subset is
  vendored under `src/app/static/icons/` (and the 16 used in templates under
  `src/app/templates/icons/`) together with the license file. No emoji anywhere.

## AI assistance

An agentic AI coding assistant (Arena.ai Agent Mode) generated the initial
code, tests, and documentation drafts from the EF101-P01 specification in this
repository's session. All output was executed, reviewed, and verified by the
group: 81/81 tests pass, `ruff`/`bandit`/`pip-audit` are clean, and the live
server flow was verified with `curl`. The group takes full ownership of every
line and can explain the complete system in the viva (see `docs/VIVA.md`).

No AI-generated content is served to end users at runtime; the AI was a
development aid only. No user data was shared with any third-party AI service
by the application itself.
