"""Admin routes: dashboard, score moderation, word management.

Every route requires a logged-in user with the admin flag (403 otherwise).
"""

from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import limiter
from app.models import (
    add_word,
    admin_overview,
    delete_score,
    list_users,
    recent_scores,
    word_exists,
)
from app.services.word_service import (
    CATEGORIES,
    GENERAL_CATEGORY,
    difficulty_for_word,
    validate_word,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_required(view)(*args, **kwargs)
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapper


@admin_bp.get("/")
@login_required
@admin_required
def dashboard():
    return render_template(
        "admin.html",
        overview=admin_overview(),
        recent=recent_scores(20),
        users=list_users(50),
        categories=(GENERAL_CATEGORY, *CATEGORIES),
    )


@admin_bp.post("/scores/<int:score_id>/delete")
@login_required
@admin_required
@limiter.limit("30 per minute")
def delete_score_route(score_id):
    if delete_score(score_id):
        flash("Score deleted.")
    else:
        flash("Score not found.")
    return redirect(url_for("admin.dashboard"))


@admin_bp.post("/words/add")
@login_required
@admin_required
@limiter.limit("30 per minute")
def add_word_route():
    category = request.form.get("category", GENERAL_CATEGORY)
    if category not in (GENERAL_CATEGORY, *CATEGORIES):
        category = GENERAL_CATEGORY
    ok, cleaned_or_error = validate_word(request.form.get("word", ""))
    if not ok:
        flash(cleaned_or_error)
        return redirect(url_for("admin.dashboard"))
    if word_exists(cleaned_or_error):
        flash("That word is already in the vocabulary.")
        return redirect(url_for("admin.dashboard"))
    difficulty = difficulty_for_word(cleaned_or_error)
    add_word(cleaned_or_error, difficulty, category)
    flash(f"Added '{cleaned_or_error}' as {difficulty} / {category}.")
    return redirect(url_for("admin.dashboard"))
