-- EF101-P01 Hangman schema (Cloudflare D1 / SQLite).
-- Applied with: wrangler d1 execute hangman-db --file=./schema.sql
-- (Local dev applies it automatically on first run; see app/db.py.)

CREATE TABLE IF NOT EXISTS words (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    word       TEXT NOT NULL UNIQUE,
    difficulty TEXT NOT NULL CHECK (difficulty IN ('Easy', 'Medium', 'Hard')),
    category   TEXT NOT NULL DEFAULT 'General'
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    player_name TEXT NOT NULL,
    score       INTEGER NOT NULL,
    difficulty  TEXT NOT NULL,
    result      TEXT NOT NULL CHECK (result IN ('won', 'lost')),
    category    TEXT,
    user_id     INTEGER NULL REFERENCES users (id),
    created_at  TEXT NOT NULL
);

-- Server-side game sessions. The answer lives ONLY here (never in a cookie,
-- never in page source) until the game is won or lost.
CREATE TABLE IF NOT EXISTS games (
    id           TEXT PRIMARY KEY,
    word         TEXT NOT NULL,
    difficulty   TEXT NOT NULL,
    category     TEXT NOT NULL,
    guessed      TEXT NOT NULL DEFAULT '',
    remaining    INTEGER NOT NULL,
    max_attempts INTEGER NOT NULL,
    hints_used   INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL DEFAULT 'playing' CHECK (status IN ('playing', 'won', 'lost')),
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_words_difficulty ON words (difficulty);
CREATE INDEX IF NOT EXISTS idx_words_category ON words (category);
CREATE INDEX IF NOT EXISTS idx_scores_rank ON scores (score DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_scores_user ON scores (user_id);
CREATE INDEX IF NOT EXISTS idx_games_status ON games (status);
