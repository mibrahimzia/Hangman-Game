"""Game routes: play, guess, hint, give up, submit score, daily challenge.

The answer is stored server-side in the `games` table and is NEVER rendered
into a page or JSON response until the game is won or lost.
"""

import secrets
from datetime import UTC, datetime

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user

from app import limiter
from app.models import (
    create_game,
    daily_word,
    delete_game,
    get_game,
    insert_score,
    random_word,
    save_game,
)
from app.services.game_engine import (
    OUTCOME_CORRECT,
    OUTCOME_DUPLICATE,
    OUTCOME_INCORRECT,
    OUTCOME_INVALID,
    OUTCOME_LOSS,
    OUTCOME_WIN,
    HangmanGame,
)
from app.services.word_service import (
    CATEGORIES,
    DIFFICULTIES,
    GENERAL_CATEGORY,
    attempts_for_difficulty,
    validate_player_name,
)

game_bp = Blueprint("game", __name__)

GAME_COOKIE = "hangman_game"


def _cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "secure": current_app.config["SESSION_COOKIE_SECURE"],
        "samesite": "Lax",
        "max_age": 7 * 24 * 3600,
    }


def _utc_today():
    return datetime.now(UTC).date()


def _load_game():
    game_id = request.cookies.get(GAME_COOKIE)
    if not game_id or len(game_id) > 128:
        return None, None
    row = get_game(game_id)
    if row is None:
        return None, None
    return game_id, HangmanGame.from_row(row)


def _persist(game_id, game: HangmanGame) -> None:
    save_game(game_id, game.to_update()["guessed"], game.remaining, game.status, game.hints_used)


def _wants_json() -> bool:
    return "application/json" in request.headers.get("Accept", "")


def _payload(game: HangmanGame, message="") -> dict:
    data = {
        "masked": game.masked_letters,
        "display": game.masked_display,
        "guessed": sorted(game.guessed),
        "remaining": game.remaining,
        "max_attempts": game.max_attempts,
        "wrong": game.wrong_count,
        "status": game.status,
        "score": game.live_score(),
        "difficulty": game.difficulty,
        "category": getattr(game, "category", GENERAL_CATEGORY),
        "message": message,
    }
    if game.is_finished:
        data["answer"] = game.word.upper()
        data["final_score"] = game.final_score()
    return data


def _start_game(word_row, category_label) -> Response:
    game_id = secrets.token_urlsafe(16)
    attempts = attempts_for_difficulty(word_row["difficulty"])
    create_game(
        game_id,
        word_row["word"],
        word_row["difficulty"],
        category_label or word_row["category"] or GENERAL_CATEGORY,
        attempts,
    )
    response = redirect(url_for("game.index"))
    response.set_cookie(GAME_COOKIE, game_id, **_cookie_kwargs())
    return response


@game_bp.get("/")
def index():
    game_id, game = _load_game()
    answer = game.word.upper() if (game and game.is_finished) else None
    parts_visible = 0
    if game:
        parts_visible = min(6, -(-game.wrong_count * 6 // game.max_attempts))  # ceil div
    return render_template(
        "game.html",
        game=game,
        answer=answer,
        parts_visible=parts_visible,
        difficulties=DIFFICULTIES,
        categories=("All", GENERAL_CATEGORY, *CATEGORIES),
    )


@game_bp.post("/new")
@limiter.limit("30 per minute")
def new_game():
    difficulty = request.form.get("difficulty", "Medium")
    category = request.form.get("category", "All")
    if difficulty not in DIFFICULTIES:
        difficulty = "Medium"
    if category not in ("All", GENERAL_CATEGORY, *CATEGORIES):
        category = "All"
    row = random_word(difficulty, None if category == "All" else category)
    if row is None:
        flash("No words available for that choice yet. Try another difficulty.")
        return redirect(url_for("game.index"))
    return _start_game(row, None)


@game_bp.get("/daily")
def daily():
    row = daily_word(_utc_today())
    if row is None:
        flash("Word list is not seeded yet.")
        return redirect(url_for("game.index"))
    return _start_game(row, "Daily")


@game_bp.post("/guess")
@limiter.limit("60 per minute")
def guess():
    game_id, game = _load_game()
    if game is None:
        if _wants_json():
            return jsonify({"error": "Start a new game first.", "status": "none"}), 400
        flash("Start a new game first.")
        return redirect(url_for("game.index"))
    if game.is_finished:
        if _wants_json():
            return jsonify(_payload(game, "Game already finished."))
        return redirect(url_for("game.index"))

    data = request.get_json(silent=True) or {}
    letter = request.form.get("letter", data.get("letter", ""))
    outcome = game.guess(letter)
    _persist(game_id, game)

    messages = {
        OUTCOME_CORRECT: "Good guess.",
        OUTCOME_INCORRECT: f"'{letter.strip().upper()}' is not in the word.",
        OUTCOME_DUPLICATE: "You already tried that letter.",
        OUTCOME_INVALID: "Enter a single letter A-Z.",
        OUTCOME_WIN: "You won. Well played.",
        OUTCOME_LOSS: f"Game over. The word was {game.word.upper()}.",
    }
    message = messages.get(outcome, "")
    if _wants_json():
        return jsonify(_payload(game, message))
    if message:
        flash(message)
    return redirect(url_for("game.index"))


@game_bp.post("/hint")
@limiter.limit("30 per minute")
def hint():
    game_id, game = _load_game()
    if game is None or game.is_finished:
        if _wants_json():
            return jsonify({"error": "No active game.", "status": "none"}), 400
        flash("No active game for a hint.")
        return redirect(url_for("game.index"))
    letter = game.use_hint()
    _persist(game_id, game)
    if letter is None:
        message = "No hint available."
    elif game.is_finished:
        message = "Hint completed the word. You won."
    else:
        message = f"Hint revealed '{letter.upper()}' (-15 points)."
    if _wants_json():
        return jsonify(_payload(game, message))
    flash(message)
    return redirect(url_for("game.index"))


@game_bp.post("/give-up")
def give_up():
    game_id, game = _load_game()
    if game is not None and not game.is_finished:
        game.forfeit()
        _persist(game_id, game)
        flash(f"You gave up. The word was {game.word.upper()}.")
    return redirect(url_for("game.index"))


@game_bp.get("/submit-score")
def submit_score_form():
    _, game = _load_game()
    if game is None or not game.is_finished:
        flash("Finish a game before submitting a score.")
        return redirect(url_for("game.index"))
    suggested = ""
    if current_user.is_authenticated:
        suggested = current_user.username
    return render_template(
        "submit_score.html",
        game=game,
        answer=game.word.upper(),
        final_score=game.final_score(),
        suggested=suggested,
    )


@game_bp.post("/submit-score")
@limiter.limit("10 per minute")
def submit_score():
    game_id, game = _load_game()
    if game is None or not game.is_finished:
        flash("Finish a game before submitting a score.")
        return redirect(url_for("game.index"))
    ok, cleaned_or_error = validate_player_name(request.form.get("player_name", ""))
    if not ok:
        flash(cleaned_or_error)
        return redirect(url_for("game.submit_score_form"))
    user_id = current_user.id if current_user.is_authenticated else None
    score_id = insert_score(
        player_name=cleaned_or_error,
        score=game.final_score(),
        difficulty=game.difficulty,
        result=game.status,
        category=game.category,
        user_id=user_id,
    )
    delete_game(game_id)
    response = redirect(url_for("leaderboard.index", highlight=score_id))
    response.delete_cookie(GAME_COOKIE)
    flash("Score saved to the leaderboard.")
    return response
