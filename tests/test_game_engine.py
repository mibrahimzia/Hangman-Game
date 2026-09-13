"""Unit tests for the pure game engine and scoring (no Flask needed)."""

import pytest

from app.services.game_engine import HangmanGame
from app.services.scoring import calculate_score
from app.services.word_service import (
    attempts_for_difficulty,
    difficulty_for_word,
    validate_player_name,
)


def make_game(word="planet", difficulty="Medium"):
    return HangmanGame(word, difficulty, attempts_for_difficulty(difficulty))


# -- guessing ---------------------------------------------------------------


def test_correct_single_letter():
    game = make_game("cat")
    assert game.guess("c") == "correct"
    assert game.masked_letters == ["C", "", ""]
    assert game.remaining == game.max_attempts


def test_repeated_letter_reveals_both():
    game = make_game("letter")
    assert game.guess("t") == "correct"
    assert game.masked_letters == ["", "", "T", "T", "", ""]


def test_wrong_letter_decrements_attempts():
    game = make_game("cat")
    before = game.remaining
    assert game.guess("z") == "incorrect"
    assert game.remaining == before - 1


def test_duplicate_guess_does_not_decrement():
    game = make_game("cat")
    game.guess("z")
    before = game.remaining
    assert game.guess("z") == "duplicate"
    assert game.guess("Z") == "duplicate"  # case-insensitive
    assert game.remaining == before


def test_invalid_guesses_do_not_change_state():
    game = make_game("cat")
    before = (list(game.guessed), game.remaining)
    for bad in ("", "ab", "1", "!", " ", None):
        assert game.guess(bad) == "invalid"
    assert (list(game.guessed), game.remaining) == before


def test_complete_win():
    game = make_game("cat")
    assert game.guess("c") == "correct"
    assert game.guess("a") == "correct"
    assert game.guess("t") == "win"
    assert game.status == "won"
    assert game.is_finished


def test_complete_loss():
    game = HangmanGame("cat", "Hard", 2)
    assert game.guess("z") == "incorrect"
    assert game.guess("q") == "loss"
    assert game.status == "lost"
    assert game.remaining == 0


@pytest.mark.parametrize("difficulty,attempts", [("Easy", 8), ("Medium", 6), ("Hard", 5)])
def test_difficulties_set_attempts(difficulty, attempts):
    assert attempts_for_difficulty(difficulty) == attempts
    game = HangmanGame("planet", difficulty, attempts)
    assert game.max_attempts == attempts
    assert game.remaining == attempts


def test_guess_after_finish_is_stable():
    game = make_game("cat")
    for letter in "cat":
        game.guess(letter)
    assert game.guess("z") == "win"
    assert game.remaining == game.max_attempts


def test_hint_reveals_letter_without_costing_attempt():
    game = make_game("planet")
    before = game.remaining
    letter = game.use_hint()
    assert letter in set("planet")
    assert letter in game.guessed
    assert game.remaining == before
    assert game.hints_used == 1


def test_forfeit_marks_lost():
    game = make_game("planet")
    game.forfeit()
    assert game.status == "lost"
    assert game.remaining == 0


def test_row_roundtrip():
    game = make_game("planet")
    game.guess("p")
    row = {
        "word": game.word,
        "difficulty": game.difficulty,
        "max_attempts": game.max_attempts,
        "guessed": "".join(game.guessed),
        "remaining": game.remaining,
        "hints_used": 0,
        "status": "playing",
    }
    clone = HangmanGame.from_row(row)
    assert clone.word == "planet"
    assert clone.guessed == ["p"]
    assert clone.to_update() == {"guessed": "p"}


# -- scoring -----------------------------------------------------------------


def test_score_easy_example():
    # (5 x 10) x 1.0 + (8 x 5) = 90
    assert calculate_score(word_length=5, difficulty="Easy", remaining_attempts=8, won=True) == 90


def test_score_medium_example():
    # (6 x 10) x 1.5 + (3 x 5) = 105
    assert (
        calculate_score(word_length=6, difficulty="Medium", remaining_attempts=3, won=True) == 105
    )


def test_score_hard_with_hint():
    # (9 x 10) x 2.0 + (5 x 5) - 15 = 190
    assert (
        calculate_score(
            word_length=9, difficulty="Hard", remaining_attempts=5, hints_used=1, won=True
        )
        == 190
    )


def test_score_loss_is_zero():
    assert calculate_score(word_length=9, difficulty="Hard", remaining_attempts=0, won=False) == 0


def test_score_never_negative():
    assert (
        calculate_score(
            word_length=3, difficulty="Easy", remaining_attempts=0, hints_used=99, won=True
        )
        == 0
    )


def test_final_score_uses_engine_state():
    game = make_game("cat")  # Medium: (3x10)x1.5 + (6x5) = 75
    for letter in "cat":
        game.guess(letter)
    assert game.final_score() == 75
    assert game.live_score() == 75


# -- difficulty rule ----------------------------------------------------------


@pytest.mark.parametrize(
    "word,expected",
    [
        ("cat", "Easy"),
        ("dog", "Easy"),
        ("planet", "Medium"),
        ("tennis", "Medium"),
        ("jazz", "Hard"),  # uncommon letters
        ("quiz", "Hard"),  # uncommon letters
        ("mountain", "Medium"),  # length 8, common letters, score 8
        ("flywheel", "Hard"),  # length 8 but tricky letters push score to 12
        ("hippopotamus", "Hard"),  # long
    ],
)
def test_difficulty_rule(word, expected):
    assert difficulty_for_word(word) == expected


# -- player names --------------------------------------------------------------


@pytest.mark.parametrize("name", ["Ayesha", "Bilal_99", "Zoe-1", "a b", "X" * 20])
def test_valid_player_names(name):
    ok, cleaned = validate_player_name(name)
    assert ok and cleaned == name.strip()


@pytest.mark.parametrize(
    "name", ["", "   ", "\t", None, "X" * 21, "<script>", "O'Brien", "a/b", "semi;colon"]
)
def test_invalid_player_names_rejected(name):
    ok, _ = validate_player_name(name)
    assert not ok
