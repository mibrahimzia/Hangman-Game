"""Security regression tests: headers, cookies, CSRF, XSS, auth, limits."""

import os

from app.models import get_user_by_username, insert_score, set_admin
from tests.conftest import ROOT


def test_security_headers_present(client):
    response = client.get("/")
    headers = response.headers
    assert headers["Content-Security-Policy"].startswith("default-src 'self'")
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "Referrer-Policy" in headers
    assert "Strict-Transport-Security" in headers
    assert "Permissions-Policy" in headers


def test_game_cookie_is_locked_down(client):
    response = client.post("/new", data={"difficulty": "Easy", "category": "All"})
    cookies = response.headers.getlist("Set-Cookie")
    game_cookie = next(c for c in cookies if c.startswith("hangman_game="))
    assert "HttpOnly" in game_cookie
    assert "Secure" in game_cookie
    assert "SameSite=Lax" in game_cookie


def test_session_cookie_is_locked_down(client):
    response = client.post(
        "/register",
        data={
            "username": "cookieuser",
            "password": "password123",
            "confirm": "password123",
        },
    )
    cookies = response.headers.getlist("Set-Cookie")
    session_cookie = next(c for c in cookies if c.startswith("session="))
    assert "HttpOnly" in session_cookie
    assert "Secure" in session_cookie
    assert "SameSite=Lax" in session_cookie


def test_csrf_blocks_forms_without_token(client_csrf):
    assert client_csrf.post("/new", data={"difficulty": "Easy"}).status_code == 400
    assert client_csrf.post("/guess", data={"letter": "a"}).status_code == 400


def test_forms_carry_csrf_tokens(client):
    html = client.get("/").data.decode()
    assert 'name="csrf_token"' in html


def test_leaderboard_escapes_player_names(client, app):
    with app.app_context():
        insert_score("<script>alert(1)</script>", 50, "Easy", "won", "General", None)
    html = client.get("/leaderboard").data.decode()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_submit_score_rejects_html_names(client, app):
    from tests.conftest import start_game

    start_game(client)
    from app.models import get_game
    from tests.conftest import game_id_of

    with app.app_context():
        row = get_game(game_id_of(client))
    for letter in set(row["word"]):
        client.post("/guess", data={"letter": letter})
    response = client.post("/submit-score", data={"player_name": "<b>bold</b>"})
    assert response.status_code == 302
    assert "/submit-score" in response.location


def _register(client, username, password="password123"):
    return client.post(
        "/register",
        data={
            "username": username,
            "password": password,
            "confirm": password,
        },
        follow_redirects=True,
    )


def test_admin_routes_require_admin(client, app):
    assert client.get("/admin/").status_code == 302  # anonymous -> login
    _register(client, "normaluser")
    assert client.get("/admin/").status_code == 403  # logged in, not admin
    with app.app_context():
        set_admin("normaluser", True)
    assert client.get("/admin/").status_code == 200


def test_admin_can_delete_score_and_add_word(client, app):
    _register(client, "adminuser")
    with app.app_context():
        set_admin("adminuser", True)
        score_id = insert_score("Spammer", 5, "Easy", "won", "General", None)
    response = client.post(f"/admin/scores/{score_id}/delete", follow_redirects=True)
    assert response.status_code == 200
    assert "Spammer" not in client.get("/leaderboard").data.decode()

    response = client.post(
        "/admin/words/add", data={"word": "xylophone", "category": "Science"}, follow_redirects=True
    )
    assert "xylophone" in response.data.decode()
    response = client.post(
        "/admin/words/add", data={"word": "xylophone", "category": "Science"}, follow_redirects=True
    )
    assert "already in the vocabulary" in response.data.decode()


def test_passwords_hashed_with_pbkdf2(client, app):
    _register(client, "hashuser")
    with app.app_context():
        user = get_user_by_username("hashuser")
    assert user.password_hash.startswith("pbkdf2:sha256")
    assert "password123" not in user.password_hash


def test_login_is_rate_limited(client_limited):
    statuses = [
        client_limited.post("/login", data={"username": "nobody", "password": "wrong"}).status_code
        for _ in range(6)
    ]
    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429


def test_login_next_param_blocks_open_redirects(client):
    _register(client, "redirectuser")
    client.get("/logout")
    response = client.post(
        "/login",
        data={
            "username": "redirectuser",
            "password": "password123",
            "next": "https://evil.example.com/",
        },
    )
    assert response.status_code == 302
    assert response.location == "/"


def test_models_use_bound_parameters_not_interpolation():
    for name in ("src/app/models.py", "src/app/db.py"):
        with open(os.path.join(ROOT, name), encoding="utf-8") as handle:
            source = handle.read()
        assert 'f"SELECT' not in source
        assert "f'SELECT" not in source
        assert '"SELECT %' not in source
        assert "'SELECT %" not in source
        assert '"INSERT %' not in source
        assert "?" in source  # placeholders are used


def test_no_emoji_in_source():
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "src")):
        # Vendored third-party code is byte-identical to PyPI releases; only
        # first-party sources are held to the glyph policy.
        dirnames[:] = [d for d in dirnames if d != "python_modules"]
        for filename in filenames:
            if not filename.endswith((".py", ".html", ".js", ".css")):
                continue
            with open(os.path.join(dirpath, filename), encoding="utf-8") as handle:
                for lineno, line in enumerate(handle, 1):
                    assert all(ord(ch) < 0x2500 for ch in line), (
                        f"non-ASCII glyph in {filename}:{lineno}"
                    )
