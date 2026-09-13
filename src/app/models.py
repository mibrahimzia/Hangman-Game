"""D1 query helpers. Every statement is a prepared statement with bound `?`
parameters - user input is never interpolated into SQL."""

from datetime import UTC, datetime

from flask_login import UserMixin

from app.db import execute_write, query_all, query_one


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


# ---------------------------------------------------------------------------
# Words
# ---------------------------------------------------------------------------


def random_word(difficulty: str, category=None):
    if category:
        return query_one(
            "SELECT id, word, difficulty, category FROM words "
            "WHERE difficulty = ? AND category = ? ORDER BY RANDOM() LIMIT 1",
            (difficulty, category),
        )
    return query_one(
        "SELECT id, word, difficulty, category FROM words "
        "WHERE difficulty = ? ORDER BY RANDOM() LIMIT 1",
        (difficulty,),
    )


def daily_word(day):
    """Deterministic word for a UTC date: same date -> same word for everyone."""
    from app.services.word_service import daily_pool_index

    row = query_one("SELECT COUNT(*) AS n FROM words")
    pool = int(row["n"]) if row else 0
    if pool <= 0:
        return None
    offset = daily_pool_index(day, pool)
    return query_one(
        "SELECT id, word, difficulty, category FROM words ORDER BY id LIMIT 1 OFFSET ?",
        (offset,),
    )


def count_words() -> int:
    row = query_one("SELECT COUNT(*) AS n FROM words")
    return int(row["n"]) if row else 0


def word_exists(word: str) -> bool:
    row = query_one("SELECT 1 AS found FROM words WHERE word = ?", (word,))
    return row is not None


def add_word(word: str, difficulty: str, category: str) -> bool:
    try:
        execute_write(
            "INSERT INTO words (word, difficulty, category) VALUES (?, ?, ?)",
            (word, difficulty, category),
        )
        return True
    except Exception:  # noqa: BLE001 - UNIQUE violation means "already present"
        return word_exists(word)


# ---------------------------------------------------------------------------
# Server-side game sessions
# ---------------------------------------------------------------------------


def create_game(game_id, word, difficulty, category, max_attempts) -> None:
    execute_write(
        "INSERT INTO games (id, word, difficulty, category, guessed, remaining,"
        " max_attempts, hints_used, status, created_at)"
        " VALUES (?, ?, ?, ?, '', ?, ?, 0, 'playing', ?)",
        (game_id, word, difficulty, category, max_attempts, max_attempts, utc_now_iso()),
    )


def get_game(game_id):
    return query_one(
        "SELECT id, word, difficulty, category, guessed, remaining, max_attempts,"
        " hints_used, status, created_at FROM games WHERE id = ?",
        (game_id,),
    )


def save_game(game_id, guessed, remaining, status, hints_used) -> None:
    execute_write(
        "UPDATE games SET guessed = ?, remaining = ?, status = ?, hints_used = ? WHERE id = ?",
        (guessed, remaining, status, hints_used, game_id),
    )


def delete_game(game_id) -> None:
    execute_write("DELETE FROM games WHERE id = ?", (game_id,))


# ---------------------------------------------------------------------------
# Scores / leaderboard
# ---------------------------------------------------------------------------


def insert_score(player_name, score, difficulty, result, category, user_id):
    row = query_one(
        "INSERT INTO scores (player_name, score, difficulty, result, category,"
        " user_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) RETURNING id",
        (player_name, score, difficulty, result, category, user_id, utc_now_iso()),
    )
    return int(row["id"]) if row else 0


def top_scores(limit=50, difficulty=None):
    if difficulty:
        return query_all(
            "SELECT id, player_name, score, difficulty, result, category, created_at"
            " FROM scores WHERE difficulty = ?"
            " ORDER BY score DESC, created_at ASC LIMIT ?",
            (difficulty, limit),
        )
    return query_all(
        "SELECT id, player_name, score, difficulty, result, category, created_at"
        " FROM scores ORDER BY score DESC, created_at ASC LIMIT ?",
        (limit,),
    )


def recent_scores(limit=20):
    return query_all(
        "SELECT id, player_name, score, difficulty, result, category, created_at"
        " FROM scores ORDER BY id DESC LIMIT ?",
        (limit,),
    )


def delete_score(score_id) -> bool:
    return execute_write("DELETE FROM scores WHERE id = ?", (score_id,)) > 0


def user_stats(user_id) -> dict:
    row = query_one(
        "SELECT COUNT(*) AS games, COALESCE(MAX(score), 0) AS best FROM scores WHERE user_id = ?",
        (user_id,),
    )
    return {
        "games_played": int(row["games"]) if row else 0,
        "best_score": int(row["best"]) if row else 0,
    }


def recent_scores_for_user(user_id, limit=10):
    return query_all(
        "SELECT id, player_name, score, difficulty, result, category, created_at"
        " FROM scores WHERE user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class User(UserMixin):
    def __init__(self, row: dict):
        self.id = row["id"]
        self.username = row["username"]
        self.password_hash = row["password_hash"]
        self.is_admin = bool(row.get("is_admin", 0))
        self.created_at = row.get("created_at")

    def get_id(self):
        return str(self.id)


def get_user_by_id(user_id):
    row = query_one(
        "SELECT id, username, password_hash, is_admin, created_at FROM users WHERE id = ?",
        (user_id,),
    )
    return User(row) if row else None


def get_user_by_username(username):
    row = query_one(
        "SELECT id, username, password_hash, is_admin, created_at FROM users WHERE username = ?",
        (username,),
    )
    return User(row) if row else None


def create_user(username, password_hash):
    row = query_one(
        "INSERT INTO users (username, password_hash, is_admin, created_at)"
        " VALUES (?, ?, 0, ?) RETURNING id",
        (username, password_hash, utc_now_iso()),
    )
    return get_user_by_id(int(row["id"]))


def set_admin(username, is_admin=True) -> None:
    execute_write(
        "UPDATE users SET is_admin = ? WHERE username = ?",
        (1 if is_admin else 0, username),
    )


def list_users(limit=50):
    return query_all(
        "SELECT id, username, is_admin, created_at FROM users ORDER BY id ASC LIMIT ?",
        (limit,),
    )


def admin_overview() -> dict:
    words = query_one("SELECT COUNT(*) AS n FROM words") or {"n": 0}
    scores = query_one("SELECT COUNT(*) AS n FROM scores") or {"n": 0}
    users = query_one("SELECT COUNT(*) AS n FROM users") or {"n": 0}
    playing = query_one("SELECT COUNT(*) AS n FROM games WHERE status = 'playing'") or {"n": 0}
    return {
        "words": int(words["n"]),
        "scores": int(scores["n"]),
        "users": int(users["n"]),
        "games_in_progress": int(playing["n"]),
    }
