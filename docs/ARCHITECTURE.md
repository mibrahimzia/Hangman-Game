# Architecture - EF101-P01 Hangman

## System diagram

```
+-------------------+   HTTPS   +------------------------------------------+
|      Browser      | <--------> |  Cloudflare Worker (Python + Flask)      |
|                   |           |                                          |
| - renders masked  |           |  src/worker.py                           |
|   word, drawing,  |  forms /  |    on_fetch -> workers.wsgi.fetch        |
|   score, board    |  JSON     |       |                                  |
| - holds ONE       |           |       v                                  |
|   opaque cookie:  |           |  Flask routes (src/app/routes/)              |
|   hangman_game    |           |    game.py  leaderboard.py               |
|   = random token  |           |    auth.py  admin.py                     |
|   (no answer!)    |           |       |                                  |
|                   |           |       v                                  |
| Vanilla JS only   |           |  Services (src/app/services/)  Models       |
| enhances forms;   |           |   game_engine.py  <-+  (src/app/models.py)  |
| page works with   |           |   scoring.py        |  prepared stmts  |
| JS disabled.      |           |   word_service.py   |  bound `?` params|
+-------------------+           |       |             |                    |
                                |       v             v                    |
                                |  DB layer (src/app/db.py)                    |
                                |   environ["workers.env"].DB              |
                                +-------|----------------------------------+
                                        |  D1 protocol (prepared statements)
                                        v
                                +------------------------------------------+
                                |  Cloudflare D1 (SQLite)  hangman-db      |
                                |  words | users | scores | games          |
                                +------------------------------------------+
```

Local development replaces the last two boxes with `run.py` (Flask dev
server) and `instance/hangman.db` (SQLite file, same schema). The `src/app/db.py`
layer dispatches automatically: if `request.environ["workers.env"]` exists it
uses D1 via `pyodide.ffi.run_sync`, otherwise local SQLite.

## Request flows

### Word request (new game)

```
Browser                    Flask route                 D1 binding              D1
  | POST /new                 |                           |                     |
  | difficulty, category      |                           |                     |
  | + CSRF token              |                           |                     |
  |-------------------------->|                           |                     |
  |                           | prepare + bind + .all()   |                     |
  |                           | via run_sync              |                     |
  |                           |------------------------------------------------>|
  |                           | SELECT word FROM words    |                     |
  |                           | WHERE difficulty = ?      |                     |
  |                           | ORDER BY RANDOM() LIMIT 1 |                     |
  |                           |<------------------------------------------------|
  |                           | word row                  |                     |
  |                           |------------------------------------------------>|
  |                           | INSERT INTO games (...)   |                     |
  | 302 + Set-Cookie:         |                           |                     |
  | hangman_game=<token>      |                           |                     |
  |<--------------------------|                           |                     |
```

### Guess (validated server-side; answer never leaves the server)

```
Browser                    Flask route                 games table (D1)
  | POST /guess (letter)      |                           |
  |-------------------------->| SELECT * FROM games       |
  |                           | WHERE id = ?              |
  |                           |-------------------------->|
  |                           |<--------------------------|
  |                           | HangmanGame.guess()       |
  |                           | UPDATE games SET ...      |
  |                           |-------------------------->|
  | JSON {masked, guessed,    |                           |
  |  remaining, status,       |                           |
  |  score, message}          |  <-- NO "answer" key      |
  |<--------------------------|      while playing       |
```

Only when `status` becomes `won`/`lost` does the response include `answer`
(and the page renders it). While playing, the only client-side artefact is the
opaque session token.

### Score write path

```
Browser -> POST /submit-score (player_name + CSRF) -> validate name ->
INSERT INTO scores (...) RETURNING id -> DELETE FROM games (session cleanup) ->
clear cookie -> 302 /leaderboard?highlight=<id>
```

### Leaderboard read path

```
Browser -> GET /leaderboard?difficulty=... ->
SELECT ... ORDER BY score DESC, created_at ASC LIMIT 50 ->
Jinja2 template (auto-escaped) -> HTML table, top 3 with badge icons
```

## Why the answer must never reach the client early

Exposing the full answer in page source, a JavaScript variable, or even a
signed cookie is poor design for three reasons:

1. **It is readable.** Signed (Flask session) or base64-encoded data is not
   encrypted; "View source" or DevTools reveals it instantly, so any player
   can cheat without skill.
2. **It breaks the trust boundary.** The browser is an untrusted client: all
   rules (duplicate handling, win/loss, scoring) must be enforced where the
   player cannot tamper with them - on the server, against the database row.
3. **It leaks through caches and logs.** Anything sent to the client can be
   cached, screenshotted, or logged by proxies; keeping the answer in one
   server-side row minimises exposure to exactly one reveal moment.

This project enforces the boundary structurally: `HangmanGame` lives
server-side, templates receive `answer=None` until the game finishes, the JSON
payload omits the `answer` key while playing, and the vocabulary excludes
UI-reserved tokens so DevTools verification is unambiguous. Regression tests:
`test_new_game_hides_answer`, `test_json_api_hides_answer_until_finished`.

## Secrets on Workers

Wrangler secrets (`wrangler secret put SECRET_KEY`) arrive via the Worker env
binding, not `os.environ`, and only per-request. Therefore `create_app()` sets
the key from the environment when available, and a `before_request` hook
refreshes `app.secret_key` from `request.environ["workers.env"].SECRET_KEY`.
If no secret exists anywhere, local startup raises immediately and Workers
requests fail closed (HTTP 500) instead of running unsigned.
