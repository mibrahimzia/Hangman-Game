"""Word helpers: difficulty rule, validation, daily-challenge index.

Difficulty rule (documented verbatim in docs/REPORT.md):

    uncommon = count of letters in {J, Q, X, Z}
    tricky   = count of letters in {K, V, W, Y, F, H}
    score    = len(word) + 2 * uncommon + tricky

    Easy   : length <= 5 AND uncommon == 0 AND score <= 7
    Hard   : length >= 9 OR uncommon >= 2 OR score >= 12
    Medium : everything else

The seed script (scripts/seed_words.py) imports this exact function so stored
difficulties always match the rule.
"""

import re

DIFFICULTIES = ("Easy", "Medium", "Hard")
CATEGORIES = ("Animals", "Geography", "Science", "Sports")
GENERAL_CATEGORY = "General"

UNCOMMON_LETTERS = frozenset("jqxz")
TRICKY_LETTERS = frozenset("kvwyfh")

MIN_WORD_LEN = 3
MAX_WORD_LEN = 12

MAX_ATTEMPTS = {"Easy": 8, "Medium": 6, "Hard": 5}

_NAME_RE = re.compile(r"^[A-Za-z0-9 _.\-]{1,20}$")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]{3,20}$")


def difficulty_for_word(word: str) -> str:
    cleaned = (word or "").strip().lower()
    length = len(cleaned)
    uncommon = sum(1 for ch in cleaned if ch in UNCOMMON_LETTERS)
    tricky = sum(1 for ch in cleaned if ch in TRICKY_LETTERS)
    score = length + 2 * uncommon + tricky
    if length <= 5 and uncommon == 0 and score <= 7:
        return "Easy"
    if length >= 9 or uncommon >= 2 or score >= 12:
        return "Hard"
    return "Medium"


def attempts_for_difficulty(difficulty: str) -> int:
    return MAX_ATTEMPTS.get(difficulty, 6)


def daily_pool_index(day, pool_size: int) -> int:
    if pool_size <= 0:
        return 0
    return day.toordinal() % pool_size


def validate_player_name(raw):
    """Returns (True, cleaned_name) or (False, error_message)."""
    if raw is None:
        return False, "Please enter a name."
    cleaned = raw.strip()
    if not cleaned:
        return False, "Name must not be blank."
    if len(cleaned) > 20:
        return False, "Name must be 20 characters or fewer."
    if not _NAME_RE.match(cleaned):
        return False, "Use letters, numbers, spaces and _ . - only."
    return True, cleaned


def validate_username(raw):
    if raw is None:
        return False, "Please enter a username."
    cleaned = raw.strip()
    if not _USERNAME_RE.match(cleaned):
        return False, "Username must be 3-20 characters: letters, numbers, _ . -"
    return True, cleaned


def validate_word(raw):
    if raw is None:
        return False, "Please enter a word."
    cleaned = raw.strip().lower()
    if not (MIN_WORD_LEN <= len(cleaned) <= MAX_WORD_LEN):
        return False, f"Word must be {MIN_WORD_LEN}-{MAX_WORD_LEN} letters."
    if not cleaned.isalpha() or not cleaned.isascii():
        return False, "Word must contain English letters only."
    return True, cleaned
