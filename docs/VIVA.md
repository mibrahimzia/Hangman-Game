# Viva preparation - EF101-P01 Hangman

Concise, defensible answers. Every answer references a real file, table, or
route. Each member must be able to deliver all of these from memory.

## From the P01 spec

**Browser vs server responsibilities in this project?**
The browser (`src/app/templates/game.html` + `src/app/static/js/game.js`) only renders
the masked word, drawing, and score, and submits forms. The Flask server
(`src/app/routes/game.py`) owns every rule: word choice, guess validation,
win/loss detection, and scoring in `src/app/services/scoring.py`. The browser
never sees the answer until the game ends.

**How is the word requested? Where is the answer stored during play?**
`POST /new` runs `SELECT word FROM words WHERE difficulty = ? ORDER BY
RANDOM() LIMIT 1` (`src/app/models.py::random_word`), inserts a row into the
`games` table, and returns an opaque session cookie. During play the answer
exists only in that `games` row on the server.

**How are guesses checked? How do scores reach the database? How is the
leaderboard retrieved?**
`POST /guess` loads the session and calls `HangmanGame.guess()` in
`src/app/services/game_engine.py`, then persists with `UPDATE games`.
`POST /submit-score` validates the name and runs `INSERT INTO scores ...
RETURNING id`. `GET /leaderboard` runs `SELECT ... ORDER BY score DESC,
created_at ASC LIMIT 50` in `src/app/models.py::top_scores`.

**Why is exposing the full answer in client-side source poor design?**
Anything sent to the browser - page source, JS variable, even a signed cookie -
is readable in DevTools, so players could cheat effortlessly. It also breaks
the trust boundary: rules must be enforced server-side where the player cannot
tamper with them. See `docs/ARCHITECTURE.md` for the full argument.

## From the handbook viva bank (page 33)

**Where is your data stored? Which table stores this record?**
All persistent data lives in Cloudflare D1 (`hangman-db`); locally in
`instance/hangman.db` with the identical `schema.sql`. Words are in `words`,
finished results in `scores`, accounts in `users`, and live games in `games`.

**What happens after the Guess button is pressed?**
The form posts the letter to `/guess` with a CSRF token. The server loads the
`games` row, applies the guess, updates `guessed`/`remaining`/`status`, and
responds with a redirect - or JSON (`masked`, `remaining`, `score`, no
`answer`) when `fetch` asks for `application/json`. `game.js` then repaints
the board in place.

**What is the client in your system? What is the server?**
The client is the web browser rendering Jinja templates and static assets. The
server is the Flask application (`src/app/`, served by `src/worker.py` on
Cloudflare Workers), fronting the D1 database binding `env.DB`.

**What is the role of your database?**
D1 is the persistent server-side store: it holds the 7,105-word vocabulary,
user accounts, every submitted score, and every live game session. Because
state lives in D1 and not in Worker memory, scores and games survive restarts
and work across edge locations.

**Does the project require Internet access? What breaks if disconnected?**
Yes for the deployed version: the browser cannot reach the Worker or D1
offline, so nothing loads. The backup demo is the local run
(`SECRET_KEY=... python run.py`, zero network needed) plus the 76-test suite
evidence in `docs/REPORT.md`.

**How do you prevent duplicate records?**
`words.word` and `users.username` are `UNIQUE` (usernames `COLLATE NOCASE`);
seeds use `INSERT OR IGNORE`; registration checks existence first. Duplicate
*guesses* are rejected by `HangmanGame.guess()` returning `duplicate` without
touching `remaining` - covered by unit and route tests.

**What is an API in your project? What format does it return?**
`POST /guess` and `POST /hint` double as a JSON API: with
`Accept: application/json` they return JSON
(`masked`, `guessed`, `remaining`, `status`, `score`, `message`, and `answer`
only when finished). Browser forms use the same endpoints with redirects.

**How do you validate user input?**
Allow-lists in `src/app/services/word_service.py`: player names (1-20 chars,
letters/numbers/spaces/`_.-`), usernames (3-20, no spaces), words (3-12 ASCII
letters). Difficulty/category/select values are allow-listed in routes;
passwords need 8+ chars; every POST carries a Flask-WTF CSRF token.

**What test case failed during development?**
Three, all kept as regression tests: (1) scores vanished because
`INSERT ... RETURNING` went through a no-commit read helper - fixed in
`src/app/db.py`; (2) the leak test flagged "cat" because of the CSS class
`badge-cat` - renamed, and UI tokens excluded from the vocabulary at seed
time; (3) "mountain" was wrongly expected to be Hard - the rule scores it
Medium, so the test was corrected.

**What is an IP address or port here?**
Locally the dev server listens on `0.0.0.0:5000` (`run.py`, `PORT` env
overridable). In production there is no visible IP/port: the app runs on
Cloudflare's edge behind `https://hangman-game.<subdomain>.workers.dev`.

**What is one limitation of the project?**
D1 is eventually consistent, so a score can take a few seconds to appear for
readers on another edge node. Related limits: ~10 ms CPU per request on the
free plan (logic kept lean), and in-memory rate limiting is per-isolate on
Workers. Full list in `docs/REPORT.md` section 10.

**Why did you select this library?**
Flask: officially supported on Workers via `workers.wsgi`, minimal, readable.
Flask-Login + `pbkdf2:sha256`: standard auth, pure-Python for Pyodide.
Flask-WTF: CSRF + validation in one. Flask-Limiter: pure-Python throttling.
Lucide: professional ISC-licensed SVG icons with no CDN dependency.

**How would you scale this for 10,000 users?**
Workers and D1 already scale horizontally; the app keeps no per-request state
in memory. Next steps: a Cloudflare KV/Rate-Limiting-API-backed limiter for
global limits, paginated leaderboard queries, pruning stale `games` rows with
a scheduled Worker, and caching the rendered leaderboard briefly at the edge.

**What is local storage?**
In this project the phrase means two different things, and we use neither for
answers: the browser's `localStorage` (which we do not use at all - only an
opaque cookie) and the local SQLite file `instance/hangman.db` used for
development instead of D1.

**Which part did you personally implement?**
Answer honestly per the contribution table in `docs/CONTRIBUTIONS.md`:
Member 1 (engine/scoring/seeds), Member 2 (routes/templates/UI), Member 3
(Workers/D1 integration, security, tests, docs). Each of us can still explain
the whole system end to end.
