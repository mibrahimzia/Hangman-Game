"""Scoring formula (single source of truth; quoted verbatim in docs/REPORT.md).

score = (word_length x 10) x difficulty_multiplier + (remaining_attempts x 5)
        - (hints_used x 15)

Difficulty multipliers: Easy = 1.0, Medium = 1.5, Hard = 2.0.
A lost game always scores 0. Scores never go below 0.
"""

DIFFICULTY_MULTIPLIERS = {"Easy": 1.0, "Medium": 1.5, "Hard": 2.0}
POINTS_PER_LETTER = 10
POINTS_PER_REMAINING_ATTEMPT = 5
HINT_PENALTY = 15


def calculate_score(*, word_length, difficulty, remaining_attempts, hints_used=0, won=True) -> int:
    if not won:
        return 0
    multiplier = DIFFICULTY_MULTIPLIERS.get(difficulty, 1.0)
    base = (int(word_length) * POINTS_PER_LETTER) * multiplier
    bonus = int(remaining_attempts) * POINTS_PER_REMAINING_ATTEMPT
    total = int(base + bonus) - int(hints_used) * HINT_PENALTY
    return max(0, total)
