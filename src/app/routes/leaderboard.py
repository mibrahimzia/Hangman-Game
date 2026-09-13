"""Leaderboard routes: top scores, ordered by score desc, earliest first."""

from flask import Blueprint, render_template, request

from app.models import top_scores
from app.services.word_service import DIFFICULTIES

leaderboard_bp = Blueprint("leaderboard", __name__)


@leaderboard_bp.get("/leaderboard")
def index():
    difficulty = request.args.get("difficulty", "All")
    if difficulty not in (*DIFFICULTIES, "All"):
        difficulty = "All"
    rows = top_scores(50, None if difficulty == "All" else difficulty)
    highlight = request.args.get("highlight", type=int)
    return render_template(
        "leaderboard.html",
        rows=rows,
        difficulty=difficulty,
        difficulties=("All", *DIFFICULTIES),
        highlight=highlight,
    )
