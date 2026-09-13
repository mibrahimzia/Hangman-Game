"""Pure Hangman game logic. No Flask, no database - fully unit-testable.

A game is persisted as a row in the `games` table (server-side session); this
module converts rows <-> objects and applies guesses.
"""

import random

from app.services.scoring import calculate_score

STATUS_PLAYING = "playing"
STATUS_WON = "won"
STATUS_LOST = "lost"

OUTCOME_CORRECT = "correct"
OUTCOME_INCORRECT = "incorrect"
OUTCOME_DUPLICATE = "duplicate"
OUTCOME_INVALID = "invalid"
OUTCOME_WIN = "win"
OUTCOME_LOSS = "loss"


class HangmanGame:
    def __init__(
        self,
        word,
        difficulty,
        max_attempts,
        guessed=(),
        remaining=None,
        hints_used=0,
        status=STATUS_PLAYING,
        category="General",
    ):
        self.word = word.lower()
        self.difficulty = difficulty
        self.category = category or "General"
        self.max_attempts = int(max_attempts)
        self.guessed = [c for c in (guessed or [])]
        self.remaining = self.max_attempts if remaining is None else int(remaining)
        self.hints_used = int(hints_used)
        self.status = status

    @classmethod
    def from_row(cls, row: dict) -> "HangmanGame":
        return cls(
            word=row["word"],
            difficulty=row["difficulty"],
            max_attempts=row["max_attempts"],
            guessed=list(row.get("guessed") or ""),
            remaining=row["remaining"],
            hints_used=row.get("hints_used", 0),
            status=row.get("status", STATUS_PLAYING),
            category=row.get("category", "General"),
        )

    def to_update(self) -> dict:
        return {"guessed": "".join(self.guessed)}

    # -- derived state ------------------------------------------------------
    @property
    def is_finished(self) -> bool:
        return self.status in (STATUS_WON, STATUS_LOST)

    @property
    def masked_letters(self) -> list:
        guessed = set(self.guessed)
        return [c.upper() if c in guessed else "" for c in self.word]

    @property
    def masked_display(self) -> str:
        return " ".join(c if c else "_" for c in self.masked_letters)

    @property
    def wrong_count(self) -> int:
        return self.max_attempts - self.remaining

    # -- actions ------------------------------------------------------------
    def guess(self, raw) -> str:
        """Apply one guessed letter. Returns an OUTCOME_* string."""
        if self.is_finished:
            return OUTCOME_WIN if self.status == STATUS_WON else OUTCOME_LOSS
        letter = (raw or "").strip().lower()
        if len(letter) != 1 or not letter.isalpha():
            return OUTCOME_INVALID
        if letter in self.guessed:
            return OUTCOME_DUPLICATE  # never costs an attempt
        self.guessed.append(letter)
        if letter in self.word:
            if all(c in self.guessed for c in self.word):
                self.status = STATUS_WON
                return OUTCOME_WIN
            return OUTCOME_CORRECT
        self.remaining -= 1
        if self.remaining <= 0:
            self.remaining = 0
            self.status = STATUS_LOST
            return OUTCOME_LOSS
        return OUTCOME_INCORRECT

    def use_hint(self):
        """Reveal one random hidden letter. Returns the letter, or None."""
        if self.is_finished:
            return None
        hidden = sorted({c for c in self.word if c not in self.guessed})
        if not hidden:
            return None
        # Gameplay randomness only; game IDs use secrets.token_urlsafe.
        letter = random.choice(hidden)  # nosec B311
        self.guessed.append(letter)
        self.hints_used += 1
        if all(c in self.guessed for c in self.word):
            self.status = STATUS_WON
        return letter

    def forfeit(self) -> None:
        if not self.is_finished:
            self.status = STATUS_LOST
            self.remaining = 0

    # -- scoring ------------------------------------------------------------
    def final_score(self) -> int:
        return calculate_score(
            word_length=len(self.word),
            difficulty=self.difficulty,
            remaining_attempts=self.remaining,
            hints_used=self.hints_used,
            won=(self.status == STATUS_WON),
        )

    def live_score(self) -> int:
        """Projected score if the player won right now (0 once lost)."""
        if self.status == STATUS_LOST:
            return 0
        return calculate_score(
            word_length=len(self.word),
            difficulty=self.difficulty,
            remaining_attempts=self.remaining,
            hints_used=self.hints_used,
            won=True,
        )
