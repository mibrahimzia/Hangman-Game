"""Optional authentication: register, login, logout, profile."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app import limiter
from app.models import (
    create_user,
    get_user_by_username,
    recent_scores_for_user,
    user_stats,
)
from app.services.word_service import validate_username

auth_bp = Blueprint("auth", __name__)

_HASH_METHOD = "pbkdf2:sha256"  # pure-Python, Pyodide-compatible
_MIN_PASSWORD_LEN = 8


def _safe_next(default_endpoint="game.index"):
    target = request.args.get("next") or request.form.get("next") or ""
    if not target.startswith("/") or target.startswith("//"):
        return url_for(default_endpoint)
    return target


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("game.index"))
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        ok, cleaned_or_error = validate_username(username)
        if not ok:
            flash(cleaned_or_error)
        elif len(password) < _MIN_PASSWORD_LEN:
            flash("Password must be at least 8 characters.")
        elif password != confirm:
            flash("Passwords do not match.")
        elif get_user_by_username(cleaned_or_error) is not None:
            flash("That username is already taken.")
        else:
            user = create_user(
                cleaned_or_error, generate_password_hash(password, method=_HASH_METHOD)
            )
            login_user(user)
            flash(f"Welcome, {user.username}. Account created.")
            return redirect(_safe_next())
    return render_template("register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("game.index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_user_by_username(username)
        if user is not None and check_password_hash(user.password_hash, password):
            login_user(user)
            flash(f"Welcome back, {user.username}.")
            return redirect(_safe_next())
        flash("Invalid username or password.")
    return render_template("login.html")


@auth_bp.get("/logout")
def logout():
    logout_user()
    flash("You have been logged out.")
    return redirect(url_for("game.index"))


@auth_bp.get("/profile")
@login_required
def profile():
    stats = user_stats(current_user.id)
    recent = recent_scores_for_user(current_user.id, 10)
    return render_template("profile.html", stats=stats, recent=recent)
