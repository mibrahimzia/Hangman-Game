"""Route tests with the Flask test client (SQLite backend)."""

from app.models import get_game, insert_score
from tests.conftest import (
    answer_of,
    assert_answer_hidden,
    game_id_of,
    guess_all_wrong_letters,
    start_game,
)


def _row(app, gid):
    with app.app_context():
        return get_game(gid)


def test_index_without_game_shows_new_game_form(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode()
    assert "New game" in html
    assert 'name="letter"' not in html


def test_new_game_hides_answer(client, app):
    start_game(client, "Easy", "Animals")
    gid = game_id_of(client)
    answer = answer_of(app, gid)
    assert answer
    html = client.get("/").data.decode()
    assert_answer_hidden(html, answer)
    assert html.count('class="letter"') == len(answer)


def test_guess_correct_incorrect_duplicate(client, app):
    start_game(client, "Easy", "Animals")
    gid = game_id_of(client)
    answer = answer_of(app, gid)
    wrong = next(c for c in "zxqjkv" if c not in answer)

    before = _row(app, gid)["remaining"]
    client.post("/guess", data={"letter": wrong})
    assert _row(app, gid)["remaining"] == before - 1

    client.post("/guess", data={"letter": wrong})  # duplicate
    assert _row(app, gid)["remaining"] == before - 1

    client.post("/guess", data={"letter": answer[0]})
    row = _row(app, gid)
    assert answer[0] in row["guessed"]
    assert row["remaining"] == before - 1


def test_win_flow_and_submit_score(client, app):
    start_game(client, "Easy", "Animals")
    gid = game_id_of(client)
    answer = answer_of(app, gid)
    for letter in set(answer):
        client.post("/guess", data={"letter": letter})
    assert _row(app, gid)["status"] == "won"

    page = client.get("/").data.decode()
    assert "Save your score" in page
    assert answer.upper() in page  # revealed only after the win

    assert client.get("/submit-score").status_code == 200

    # Blank / whitespace names are rejected and the game is preserved.
    for bad in ("", "   "):
        response = client.post("/submit-score", data={"player_name": bad})
        assert response.status_code == 302
        assert "/submit-score" in response.location
    assert _row(app, gid)["status"] == "won"

    response = client.post("/submit-score", data={"player_name": "Tester"})
    assert response.status_code == 302
    assert "/leaderboard" in response.location
    assert game_id_of(client) is None  # cookie cleared

    board = client.get(response.location).data.decode()
    assert "Tester" in board


def test_loss_flow_reveals_answer(client, app):
    start_game(client, "Hard", "General")
    gid = game_id_of(client)
    answer = answer_of(app, gid)
    attempts = _row(app, gid)["remaining"]
    for letter in guess_all_wrong_letters(answer)[:attempts]:
        client.post("/guess", data={"letter": letter})
    assert _row(app, gid)["status"] == "lost"
    page = client.get("/").data.decode()
    assert "Game over" in page
    assert answer.upper() in page


def test_category_choice_is_respected(client, app):
    start_game(client, "Easy", "Sports")
    gid = game_id_of(client)
    assert _row(app, gid)["category"] == "Sports"


def test_daily_challenge_is_deterministic(client, app):
    client.get("/daily")
    first = answer_of(app, game_id_of(client))
    client.delete_cookie("hangman_game", domain="localhost")
    client.get("/daily")
    second = answer_of(app, game_id_of(client))
    assert first and first == second
    assert _row(app, game_id_of(client))["category"] == "Daily"


def test_hint_costs_score_not_attempts(client, app):
    start_game(client, "Medium", "Science")
    gid = game_id_of(client)
    before = _row(app, gid)
    client.post("/hint")
    after = _row(app, gid)
    assert after["remaining"] == before["remaining"]
    assert after["hints_used"] == before["hints_used"] + 1
    assert len(after["guessed"]) == len(before["guessed"]) + 1


def test_give_up_marks_lost_and_reveals(client, app):
    start_game(client)
    gid = game_id_of(client)
    client.post("/give-up")
    assert _row(app, gid)["status"] == "lost"
    assert answer_of(app, gid).upper() in client.get("/").data.decode()


def test_json_api_hides_answer_until_finished(client, app):
    start_game(client, "Easy", "Animals")
    gid = game_id_of(client)
    answer = answer_of(app, gid)
    wrong = next(c for c in "zxqjkv" if c not in answer)
    response = client.post("/guess", data={"letter": wrong}, headers={"Accept": "application/json"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "playing"
    assert "answer" not in payload
    assert_answer_hidden(response.data.decode(), answer)

    for letter in set(answer):
        response = client.post(
            "/guess", data={"letter": letter}, headers={"Accept": "application/json"}
        )
    payload = response.get_json()
    assert payload["status"] == "won"
    assert payload["answer"] == answer.upper()
    assert payload["final_score"] > 0


def test_submit_score_requires_finished_game(client):
    start_game(client)
    response = client.get("/submit-score")
    assert response.status_code == 302
    assert response.location.endswith("/")


def test_leaderboard_orders_score_then_earliest(client, app):
    with app.app_context():
        insert_score("Max", 200, "Easy", "won", "General", None)
        insert_score("Zed", 100, "Easy", "won", "General", None)
        insert_score("Amy", 100, "Easy", "won", "General", None)
    html = client.get("/leaderboard").data.decode()
    assert html.index("Max") < html.index("Zed") < html.index("Amy")


def test_leaderboard_difficulty_filter(client, app):
    with app.app_context():
        insert_score("EasyPlayer", 50, "Easy", "won", "General", None)
        insert_score("HardPlayer", 10, "Hard", "won", "General", None)
    html = client.get("/leaderboard?difficulty=Hard").data.decode()
    assert "HardPlayer" in html
    assert "EasyPlayer" not in html


def test_top_three_have_badges_and_big_names(client, app):
    with app.app_context():
        insert_score("One", 300, "Easy", "won", "General", None)
        insert_score("Two", 200, "Easy", "won", "General", None)
        insert_score("Three", 100, "Easy", "won", "General", None)
        insert_score("Four", 50, "Easy", "won", "General", None)
    html = client.get("/leaderboard").data.decode()
    assert html.count("rank-top") >= 3
    assert html.count("name-top") >= 3


def test_invalid_difficulty_defaults_safely(client, app):
    response = client.post("/new", data={"difficulty": "Nope", "category": "Nope"})
    assert response.status_code == 302
    assert game_id_of(client) is not None


def test_guess_requires_post(client):
    assert client.get("/guess").status_code == 405


def test_404_page(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404
    assert "does not exist" in response.data.decode()
