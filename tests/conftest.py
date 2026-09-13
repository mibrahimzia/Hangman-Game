import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import create_app  # noqa: E402
from app import db as db_module  # noqa: E402
from app.models import add_word  # noqa: E402
from app.services.word_service import difficulty_for_word  # noqa: E402

TEST_WORDS = [
    ("cat", "Animals"),
    ("dog", "Animals"),
    ("tiger", "Animals"),
    ("elephant", "Animals"),
    ("river", "Geography"),
    ("mountain", "Geography"),
    ("atom", "Science"),
    ("planet", "Science"),
    ("ball", "Sports"),
    ("tennis", "Sports"),
    ("quiz", "General"),
    ("jazz", "General"),
    ("garden", "General"),
    ("planet", "Science"),
]


def build_test_app(sqlite_path, **overrides):
    config = {
        "TESTING": True,
        "SECRET_KEY": "test-secret-key",
        "SQLITE_PATH": str(sqlite_path),
        "AUTO_INIT_DB": False,
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
    }
    config.update(overrides)
    application = create_app(config)
    with application.app_context():
        db_module.init_local_db(str(sqlite_path), with_seed=False)
        for word, category in TEST_WORDS:
            add_word(word, difficulty_for_word(word), category)
    return application


@pytest.fixture()
def app(tmp_path):
    return build_test_app(tmp_path / "test.db")


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def app_csrf(tmp_path):
    return build_test_app(tmp_path / "csrf.db", WTF_CSRF_ENABLED=True)


@pytest.fixture()
def client_csrf(app_csrf):
    return app_csrf.test_client()


@pytest.fixture()
def app_limited(tmp_path):
    return build_test_app(tmp_path / "limited.db", RATELIMIT_ENABLED=True)


@pytest.fixture()
def client_limited(app_limited):
    return app_limited.test_client()


def start_game(client, difficulty="Easy", category="Animals", follow=True):
    return client.post(
        "/new",
        data={"difficulty": difficulty, "category": category},
        follow_redirects=follow,
    )


def game_id_of(client, app=None, domain="localhost"):
    cookie = client.get_cookie("hangman_game", domain=domain)
    if cookie is not None:
        return cookie.value
    return None


def answer_of(app, game_id):
    from app.models import get_game

    with app.app_context():
        row = get_game(game_id)
    return row["word"] if row else None


def guess_all_wrong_letters(word):
    return [c for c in "qjzxkvwyfbhmpgudclon" if c not in set(word)]


def assert_answer_hidden(text, answer):
    """Fail if the answer appears as a standalone token (case-insensitive).

    Token-based (not substring) so words like "cat" inside "category" do not
    count as leaks.
    """
    tokens = set(re.findall(r"[a-z]+", text.lower()))
    assert answer.lower() not in tokens, f"answer {answer!r} leaked client-side"
