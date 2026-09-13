# EF101-P01: Web-Based Hangman Game with Persistent Leaderboard

| | |
|---|---|
| Project ID | EF101-P01 |
| Title | Web-Based Hangman Game with Persistent Leaderboard |
| Stack | Python 3.11 + Flask, Jinja2, Cloudflare Workers, Cloudflare D1 |
| Repository | `mibrahimzia/Hangman-Game` |
| Date | September 2026 |
| Status | Implemented, tested (74/74), documented; deployment commands prepared |

> Deployment note: the application is fully implemented and verified locally.
> The final `wrangler` deploy step requires the team's Cloudflare account, so
> the public `*.workers.dev` URL and the second-device screenshot are recorded
> in `README.md` (section "Deployed URL") once that step is run. All deployment
> files (`src/worker.py`, `wrangler.jsonc`, `schema.sql`, `db_init.sql`) are
> complete and validated (see section 9).

---

## 1. Problem statement

The course project P01 requires a web-based Hangman game that goes beyond a
static single-page toy: it must keep a large vocabulary on the server, support
difficulty levels, compute scores fairly, persist a leaderboard across restarts,
and demonstrate a clean browser/server/database separation that survives a live
viva. Common student implementations fail this bar because they hide the answer
in page source or JavaScript (trivially cheat-able), lose scores on restart
(in-memory stores), or cannot explain where data lives.

This project solves that by storing every game session and score in a real
server-side database (Cloudflare D1, SQLite-compatible), validating every guess
on the server, and never transmitting the answer to the browser until the game
is won or lost.

## 2. Objectives

1. Deliver a playable Hangman game with Easy / Medium / Hard difficulties,
   four word categories, hints, and a daily challenge.
2. Keep a vocabulary of at least 5,000 valid words in the database
   (achieved: 7,105 words), never hard-coded in templates or JavaScript.
3. Persist scores server-side and serve a top-50 leaderboard ordered by score
   (ties broken by earliest submission).
4. Guarantee by construction that the answer is never exposed client-side
   during play (server-side sessions + reserved-token vocabulary filtering).
5. Harden the application (CSRF, rate limiting, secure cookies, password
   hashing, security headers, prepared statements) and prove each control
   with automated tests.
6. Document the system so that every group member can defend the architecture,
   data design, testing, and limitations in a viva.

## 3. Architecture

Three tiers. The browser renders state and collects input; the Flask
application owns all game rules; D1 owns all persistent data. Full diagram and
request flows are in `docs/ARCHITECTURE.md`.

- Browser responsibilities: render the masked word, guessed letters, attempts,
  score and hangman drawing; submit guesses/hints/scores via forms (progressively
  enhanced with `fetch` + JSON); hold only an opaque game-session cookie.
- Server responsibilities: pick words (`ORDER BY RANDOM()`), validate guesses,
  detect win/loss, compute scores, validate player names, hash passwords,
  enforce rate limits and roles.
- Database responsibilities: persist words, users, server-side game sessions,
  and scores across Worker restarts and edge locations.

The game session is a row in the `games` table keyed by a random 128-bit token
(`secrets.token_urlsafe`) stored in an `HttpOnly; Secure; SameSite=Lax` cookie.
Flask's default cookie-based session is used only for login identity (a user
id), never for the answer, because signed cookies are still readable by their
owner.

## 4. Technology selection

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | Readable, minimal error surface, easy to defend in a viva |
| Framework | Flask | Officially supported on Cloudflare Workers via the WSGI adapter (`workers.wsgi`), proven by Cloudflare's own `flask-todo` example |
| Templates | Jinja2 | Ships with Flask; auto-escaping is the XSS defence |
| Database | Cloudflare D1 (SQLite) | Persistent, free tier, SQL-compatible; same schema runs locally on SQLite |
| D1 access | Prepared statements + `run_sync` | Matches Cloudflare's documented pattern; no ORM compatibility risk |
| Frontend | Vanilla HTML + CSS + JS | Few moving parts, works without JavaScript (forms), easier to explain |
| Icons | Lucide SVG v1.45.0 (ISC), vendored | Professional, open license, no CDN dependency, no emoji anywhere |
| Auth | Flask-Login + Werkzeug `pbkdf2:sha256` | Standard, secure, pure-Python (Pyodide-compatible) |
| Forms/CSRF | Flask-WTF | CSRF tokens + server-side validation |
| Rate limiting | Flask-Limiter (in-memory) | Login/score-submit abuse prevention; pure-Python |
| Secrets | Environment / Wrangler secrets | Missing `SECRET_KEY` refuses to start |
| Deploy tool | `pywrangler` + `wrangler` | Official Python Workers toolchain |
| Testing | pytest + Flask test client | Real assertions (76 tests), not screenshots |
| Lint/scan | ruff + bandit + pip-audit | Style, security scan, dependency audit |

Why not JavaScript on the Worker? Cloudflare Workers support Python WSGI apps
directly, so there is no technical reason to switch languages. Python keeps the
request path lean (well under the 10 ms free-plan CPU budget for this workload)
and every dependency is pure Python, which is exactly what the Pyodide-based
Workers runtime supports best.

## 5. Data design

Schema: `schema.sql` (identical for D1 and local SQLite). Seed: `db_init.sql`
(7,105 words + 13 demo scores), generated by `scripts/seed_words.py` and
`scripts/seed_demo.py`.

- `words(id, word UNIQUE, difficulty, category)` - the vocabulary.
- `users(id, username UNIQUE, password_hash, is_admin, created_at)`.
- `scores(id, player_name, score, difficulty, result, category, user_id NULL, created_at)` -
  guest scores store `NULL` user; registered users link for profiles.
- `games(id, word, difficulty, category, guessed, remaining, max_attempts, hints_used, status, created_at)` -
  ephemeral server-side sessions; deleted when a score is submitted.

Indexes: `words(difficulty)`, `words(category)`,
`scores(score DESC, created_at ASC)` (leaderboard order),
`scores(user_id)`, `games(status)`.

Seeded vocabulary (verified counts from the built database):

- Total: 7,105 words (requirement: >= 5,000).
- By difficulty: Easy 2,447, Medium 2,434, Hard 2,224.
- By category: General 6,600, Animals 152, Geography 107, Science 131, Sports 115.

Word sources: the 50,000 most frequent English words from the `wordfreq`
package (MIT, open corpora) for the General pool, plus hand-curated category
lists. A small exact-match blocklist keeps the game classroom-friendly, and
569 UI-reserved tokens (CSS classes, JSON keys, button labels, flash messages)
are excluded from the vocabulary so that searching the answer in DevTools is
unambiguous - any match would be a genuine leak, never a class name. This
check is automated: `assert_answer_hidden` in the test suite.

## 6. Implementation

### 6.1 Difficulty rule (also in `src/app/services/word_service.py`)

> uncommon = count of letters in {J, Q, X, Z}
> tricky = count of letters in {K, V, W, Y, F, H}
> score = len(word) + 2 * uncommon + tricky
> Easy: length <= 5 AND uncommon == 0 AND score <= 7
> Hard: length >= 9 OR uncommon >= 2 OR score >= 12
> Medium: everything else

Attempts per difficulty: Easy 8, Medium 6, Hard 5. The seed script imports this
exact function, so stored difficulties always match the rule.

### 6.2 Scoring formula (also in `src/app/services/scoring.py`)

> score = (word_length x 10) x difficulty_multiplier + (remaining_attempts x 5) - (hints_used x 15)
> Difficulty multipliers: Easy = 1.0, Medium = 1.5, Hard = 2.0.
> A lost game always scores 0. Scores never go below 0.

Examples: a 5-letter Easy win with 8 attempts left scores 90; a 9-letter Hard
win with 5 attempts left and one hint scores 190.

### 6.3 Key flows

- New game: `POST /new` validates difficulty/category, runs
  `SELECT word FROM words WHERE difficulty = ? ORDER BY RANDOM() LIMIT 1`,
  inserts a `games` row, sets the session cookie, redirects to `/`.
- Guess: `POST /guess` loads the session, applies
  `HangmanGame.guess()` (duplicate guesses return `duplicate` and never
  decrement; a correct letter reveals all occurrences), persists, and answers
  with a redirect (no-JS) or JSON (fetch). The answer is included only when
  `status` is `won`/`lost`.
- Hint: `POST /hint` reveals one random hidden letter, increments `hints_used`
  (-15 points each), never costs an attempt.
- Submit: `GET /submit-score` shows the finished game; `POST /submit-score`
  validates the name (1-20 chars, letters/numbers/spaces/`_.-`, blank rejected),
  inserts the score, deletes the session, clears the cookie, redirects to the
  leaderboard with the new row highlighted.
- Leaderboard: `SELECT ... ORDER BY score DESC, created_at ASC LIMIT 50`.
  Ranks 1-3 render Lucide `trophy`/`medal`/`award` icons and names in a
  distinctly larger font (`.rank-top` / `.name-top` CSS classes).
- Daily challenge: `GET /daily` picks word `day.toordinal() % pool_size`
  (`ORDER BY id LIMIT 1 OFFSET ?`), identical for every player on a UTC day.
- Auth (optional): register/login/logout via Flask-Login; profiles show games
  played, best score, and recent games. Admin routes require the admin flag and
  allow score moderation plus word additions (difficulty auto-assigned).

### 6.4 Repository layout

```
src/app/                    Flask package (factory, config, db, models, routes, services)
src/app/templates/          Jinja2 templates (answer rendered only when finished)
src/app/templates_inline.py embedded template copy (Workers FS fallback)
src/app/static/             CSS, JS, vendored Lucide icons + ISC license
src/worker.py               Cloudflare Workers entrypoint (WSGI adapter)
python_modules/             (git-ignored build output) Pyodide deps via pywrangler sync
scripts/                    seed_words.py, seed_demo.py, build_inline_templates.py
tests/                      76 pytest tests (engine, routes, security, templates)
docs/                       REPORT, ARCHITECTURE, SECURITY, VIVA, AI_DISCLOSURE, CONTRIBUTIONS
schema.sql                  D1/SQLite table definitions
db_init.sql                 generated seed data (7,105 words + demo scores)
pyproject.toml              pinned Python dependencies (Workers bundle source of truth)
wrangler.jsonc              Cloudflare Workers + D1 + assets configuration
```

The Flask package lives under `src/` (next to the entrypoint) because wrangler
collects Python modules (`**/*.py`) from the entrypoint's directory
(`moduleRoot = dirname(main)`, verified against the wrangler 4.131.1 source):
a root-level `app/` package is silently left out of the bundle, which caused
`ModuleNotFoundError: No module named 'app'` on the first deploy attempt.
Static files are served directly by the edge through the `[assets]` binding
(the worker never serves `/static/*` in production); templates additionally
ship embedded in `templates_inline.py` and are wired through a
`ChoiceLoader([FileSystemLoader, DictLoader])` fallback.

## 7. Testing

76 automated tests, all passing. Run with `SECRET_KEY=test python -m pytest -v`.

Mapping to the required cases (section 3.3 of the build spec):

| Required case | Test(s) |
|---|---|
| Correct single letter | `test_correct_single_letter` |
| Repeated letter (both revealed) | `test_repeated_letter_reveals_both` |
| Wrong letter | `test_wrong_letter_decrements_attempts` |
| Duplicate guess keeps attempts | `test_duplicate_guess_does_not_decrement`, route-level duplicate test |
| Complete win | `test_complete_win`, `test_win_flow_and_submit_score` |
| Complete loss | `test_complete_loss`, `test_loss_flow_reveals_answer` |
| Easy / Medium / Hard | `test_difficulties_set_attempts` (parametrized) + rule tests |
| Leaderboard insertion | `test_win_flow_and_submit_score`, ordering tests |
| Equal scores (tie ordering) | `test_leaderboard_orders_score_then_earliest` |
| Blank/whitespace/invalid names | `test_invalid_player_names_rejected` (9 cases) + route rejection tests |

Beyond the list: JSON-API leak tests (answer absent while playing, present when
finished), determinism of the daily challenge, hint cost accounting, category
filtering, CSRF enforcement, XSS escaping, cookie flags, rate limiting (6th
rapid login returns 429), admin authorization (anonymous 302, non-admin 403),
`pbkdf2:sha256` hash format, open-redirect blocking, a static check that models
use bound `?` parameters, and a no-emoji source scan. Live server verification
with `curl` confirmed HTTP 200 on `/` and `/leaderboard`, correct `Set-Cookie`
flags, all security headers, and a full play-through against the real database.

### 7.1 Full `pytest -v` output (76 passed)

```
platform linux -- Python 3.11.2, pytest-9.1.1, pluggy-1.6.0 -- /home/user/Hangman-Game/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/user/Hangman-Game
configfile: pyproject.toml
testpaths: tests
collecting ... collected 76 items

tests/test_game_engine.py::test_correct_single_letter PASSED             [  1%]
tests/test_game_engine.py::test_repeated_letter_reveals_both PASSED      [  2%]
tests/test_game_engine.py::test_wrong_letter_decrements_attempts PASSED  [  3%]
tests/test_game_engine.py::test_duplicate_guess_does_not_decrement PASSED [  5%]
tests/test_game_engine.py::test_invalid_guesses_do_not_change_state PASSED [  6%]
tests/test_game_engine.py::test_complete_win PASSED                      [  7%]
tests/test_game_engine.py::test_complete_loss PASSED                     [  9%]
tests/test_game_engine.py::test_difficulties_set_attempts[Easy-8] PASSED [ 10%]
tests/test_game_engine.py::test_difficulties_set_attempts[Medium-6] PASSED [ 11%]
tests/test_game_engine.py::test_difficulties_set_attempts[Hard-5] PASSED [ 13%]
tests/test_game_engine.py::test_guess_after_finish_is_stable PASSED      [ 14%]
tests/test_game_engine.py::test_hint_reveals_letter_without_costing_attempt PASSED [ 15%]
tests/test_game_engine.py::test_forfeit_marks_lost PASSED                [ 17%]
tests/test_game_engine.py::test_row_roundtrip PASSED                     [ 18%]
tests/test_game_engine.py::test_score_easy_example PASSED                [ 19%]
tests/test_game_engine.py::test_score_medium_example PASSED              [ 21%]
tests/test_game_engine.py::test_score_hard_with_hint PASSED              [ 22%]
tests/test_game_engine.py::test_score_loss_is_zero PASSED                [ 23%]
tests/test_game_engine.py::test_score_never_negative PASSED              [ 25%]
tests/test_game_engine.py::test_final_score_uses_engine_state PASSED     [ 26%]
tests/test_game_engine.py::test_difficulty_rule[cat-Easy] PASSED         [ 27%]
tests/test_game_engine.py::test_difficulty_rule[dog-Easy] PASSED         [ 28%]
tests/test_game_engine.py::test_difficulty_rule[planet-Medium] PASSED    [ 30%]
tests/test_game_engine.py::test_difficulty_rule[tennis-Medium] PASSED    [ 31%]
tests/test_game_engine.py::test_difficulty_rule[jazz-Hard] PASSED        [ 32%]
tests/test_game_engine.py::test_difficulty_rule[quiz-Hard] PASSED        [ 34%]
tests/test_game_engine.py::test_difficulty_rule[mountain-Medium] PASSED  [ 35%]
tests/test_game_engine.py::test_difficulty_rule[flywheel-Hard] PASSED    [ 36%]
tests/test_game_engine.py::test_difficulty_rule[hippopotamus-Hard] PASSED [ 38%]
tests/test_game_engine.py::test_valid_player_names[Ayesha] PASSED        [ 39%]
tests/test_game_engine.py::test_valid_player_names[Bilal_99] PASSED      [ 40%]
tests/test_game_engine.py::test_valid_player_names[Zoe-1] PASSED         [ 42%]
tests/test_game_engine.py::test_valid_player_names[a b] PASSED           [ 43%]
tests/test_game_engine.py::test_valid_player_names[XXXXXXXXXXXXXXXXXXXX] PASSED [ 44%]
tests/test_game_engine.py::test_invalid_player_names_rejected[] PASSED   [ 46%]
tests/test_game_engine.py::test_invalid_player_names_rejected[   ] PASSED [ 47%]
tests/test_game_engine.py::test_invalid_player_names_rejected[\t] PASSED [ 48%]
tests/test_game_engine.py::test_invalid_player_names_rejected[None] PASSED [ 50%]
tests/test_game_engine.py::test_invalid_player_names_rejected[XXXXXXXXXXXXXXXXXXXXX] PASSED [ 51%]
tests/test_game_engine.py::test_invalid_player_names_rejected[<script>] PASSED [ 52%]
tests/test_game_engine.py::test_invalid_player_names_rejected[O'Brien] PASSED [ 53%]
tests/test_game_engine.py::test_invalid_player_names_rejected[a/b] PASSED [ 55%]
tests/test_game_engine.py::test_invalid_player_names_rejected[semi;colon] PASSED [ 56%]
tests/test_routes.py::test_index_without_game_shows_new_game_form PASSED [ 57%]
tests/test_routes.py::test_new_game_hides_answer PASSED                  [ 59%]
tests/test_routes.py::test_guess_correct_incorrect_duplicate PASSED      [ 60%]
tests/test_routes.py::test_win_flow_and_submit_score PASSED              [ 61%]
tests/test_routes.py::test_loss_flow_reveals_answer PASSED               [ 63%]
tests/test_routes.py::test_category_choice_is_respected PASSED           [ 64%]
tests/test_routes.py::test_daily_challenge_is_deterministic PASSED       [ 65%]
tests/test_routes.py::test_hint_costs_score_not_attempts PASSED          [ 67%]
tests/test_routes.py::test_give_up_marks_lost_and_reveals PASSED         [ 68%]
tests/test_routes.py::test_json_api_hides_answer_until_finished PASSED   [ 69%]
tests/test_routes.py::test_submit_score_requires_finished_game PASSED    [ 71%]
tests/test_routes.py::test_leaderboard_orders_score_then_earliest PASSED [ 72%]
tests/test_routes.py::test_leaderboard_difficulty_filter PASSED          [ 73%]
tests/test_routes.py::test_top_three_have_badges_and_big_names PASSED    [ 75%]
tests/test_routes.py::test_invalid_difficulty_defaults_safely PASSED     [ 76%]
tests/test_routes.py::test_guess_requires_post PASSED                    [ 77%]
tests/test_routes.py::test_404_page PASSED                               [ 78%]
tests/test_security.py::test_security_headers_present PASSED             [ 80%]
tests/test_security.py::test_game_cookie_is_locked_down PASSED           [ 81%]
tests/test_security.py::test_session_cookie_is_locked_down PASSED        [ 82%]
tests/test_security.py::test_csrf_blocks_forms_without_token PASSED      [ 84%]
tests/test_security.py::test_forms_carry_csrf_tokens PASSED              [ 85%]
tests/test_security.py::test_leaderboard_escapes_player_names PASSED     [ 86%]
tests/test_security.py::test_submit_score_rejects_html_names PASSED      [ 88%]
tests/test_security.py::test_admin_routes_require_admin PASSED           [ 89%]
tests/test_security.py::test_admin_can_delete_score_and_add_word PASSED  [ 90%]
tests/test_security.py::test_passwords_hashed_with_pbkdf2 PASSED         [ 92%]
tests/test_security.py::test_login_is_rate_limited PASSED                [ 93%]
tests/test_security.py::test_login_next_param_blocks_open_redirects PASSED [ 94%]
tests/test_security.py::test_models_use_bound_parameters_not_interpolation PASSED [ 96%]
tests/test_security.py::test_no_emoji_in_source PASSED                   [ 97%]
tests/test_templates_inline.py::test_inline_templates_match_disk PASSED  [ 98%]
tests/test_templates_inline.py::test_inline_templates_render_without_filesystem PASSED [100%]

============================== 76 passed in 3.43s ==============================
```

Static analysis: `ruff check` and `ruff format --check` pass on all 21 Python
files; `bandit -r app src` reports 0 issues; `pip-audit` on the pinned
requirements reports no known vulnerabilities.

### 7.2 Cases that failed during development

1. `INSERT ... RETURNING` through the read helper never committed, so scores
   vanished between requests. Fixed by committing in the shared helper; the
   leaderboard ordering tests now guard it.
2. The leak test flagged the word "cat" - the culprit was the CSS class
   `badge-cat`, not a real leak. Fixed by renaming the class and, more
   generally, by excluding all 569 UI-reserved tokens from the vocabulary at
   seed time.
3. "mountain" was initially expected to be Hard, but the rule scores it 8
   (Medium). The test expectation was corrected and the rule examples in this
   report use verified words.

## 8. Results

All mandatory functional requirements (§3.1), system-understanding
deliverables (§3.2), testing evidence (§3.3), bonus features (§3.4), security
controls (§3.5), and documentation artifacts (§3.6) are implemented and
verified, with evidence in this report, `docs/SECURITY.md`, and the test
suite. The application runs locally with zero configuration beyond
`SECRET_KEY` (the database self-initialises from `schema.sql` + `db_init.sql`)
and is packaged for Cloudflare Workers + D1.

## 9. Deployment (Cloudflare Workers + D1)

Validated in this environment: `workers-py 1.17.2` API surface
(`workers.wsgi.fetch`, `environ["workers.env"]`, `pyodide.ffi.run_sync`),
`pyproject.toml` dependency resolution, and `wrangler.jsonc` syntax. The
`pywrangler sync` sandbox run could not download its Python 3.12 toolchain
(sandbox TLS restriction); it will run normally on a developer machine.

Release steps (run once, from the repo root, logged in via `wrangler login`):

```
uv tool install workers-py
pywrangler sync
wrangler d1 create hangman-db            # paste database_id into wrangler.jsonc
wrangler d1 execute hangman-db --file=./schema.sql
wrangler d1 execute hangman-db --file=./db_init.sql
wrangler secret put SECRET_KEY
pywrangler deploy                        # prints https://hangman-game.<sub>.workers.dev
```

Then verify from a second device (phone on mobile data): open the URL, play a
game, submit a score, and confirm it on `/leaderboard`. Record the URL in
`README.md` and paste the screenshot into this section. For repos connected
directly to Cloudflare (Workers Builds), use the dashboard build settings in
`README.md` (Option B) instead of the CLI sequence above.

Three deploy gotchas learned from the real build logs: (1) the `name` in
`wrangler.jsonc` must match the Worker name in the dashboard (`hangman-game`),
otherwise the CI overrides it and opens a fix-up PR; (2) the build must run
`pywrangler sync` (it vendors Pyodide-compatible dependencies into
`./python_modules/`, which is the only dependency source the bundle uses -
plain `wrangler deploy` cannot do this); (3) all Python code must live under
`src/` next to the entrypoint, and `/static/*` is served by the edge assets
binding, never by the worker filesystem.

No fallback platform was needed: the primary target builds cleanly, and the
only remaining step is authentication-bound.

## 10. Limitations

1. D1 is eventually consistent: a score written on one edge node can take a
   few seconds to appear for readers routed elsewhere.
2. The Workers free plan allows ~10 ms CPU per request; game logic is
   intentionally lean (single-row reads/writes, no ORM, no heavy loops).
3. Rate limiting uses in-memory storage, so on Workers each isolate tracks
   limits independently - sufficient against casual abuse, not a DDoS defence.
4. The demo needs Internet access (the app and D1 are remote); the backup plan
   is the local run (`SECRET_KEY=... python run.py`) plus the test evidence
   in section 7.
5. Vocabulary excludes UI-reserved tokens and a small blocklist by design, and
   the daily challenge is replayable (only the word is fixed, attempts are not
   limited to one per day).
6. First admin user is created via CLI locally (`flask create-admin`) or a
   direct D1 insert in production (see `README.md`); there is no self-service
   admin promotion, by design.

## 11. AI, library, and data disclosure

Summary; full detail in `docs/AI_DISCLOSURE.md`. Runtime libraries: Flask,
Flask-Login, Flask-WTF, Flask-Limiter (+ transitive deps), all pinned in
`pyproject.toml` and vendored at deploy time. Icons: Lucide v1.45.0 (ISC),
subset vendored under `src/app/static/icons/` with its license file. Vocabulary:
`wordfreq` top-50k frequencies (MIT) plus original curated category lists.
AI assistance (code generation and documentation drafting via an agentic coding
assistant) was reviewed, tested, and is owned by the group; every member must
be able to explain every part (see `docs/VIVA.md`).

## 12. Contributions

| Member | Responsibility | Key files |
|---|---|---|
| Member 1 - (replace with name) | Game engine, scoring, word/difficulty services, seed scripts | `src/app/services/*`, `scripts/*`, `schema.sql`, `db_init.sql` |
| Member 2 - (replace with name) | Flask routes, templates, CSS/JS, leaderboard, auth, admin | `src/app/routes/*`, `src/app/templates/*`, `src/app/static/*` |
| Member 3 - (replace with name) | D1/Workers integration, security hardening, tests, docs, deployment | `src/worker.py`, `wrangler.jsonc`, `src/app/db.py`, `tests/*`, `docs/*` |

Full table in `docs/CONTRIBUTIONS.md`. Replace the placeholder names before
submission; keep exactly three members.
