"""The embedded template copy must stay in sync with src/app/templates/."""

import os

from app.templates_inline import TEMPLATES
from tests.conftest import ROOT


def _on_disk_templates() -> dict:
    found = {}
    base = os.path.join(ROOT, "src", "app", "templates")
    for dirpath, _dirnames, filenames in os.walk(base):
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            key = os.path.relpath(full, base).replace(os.sep, "/")
            with open(full, encoding="utf-8") as handle:
                found[key] = handle.read()
    return found


def test_inline_templates_match_disk():
    on_disk = _on_disk_templates()
    assert set(TEMPLATES) == set(on_disk), (
        "templates_inline.py is stale - run python scripts/build_inline_templates.py"
    )
    for key, content in on_disk.items():
        assert TEMPLATES[key] == content, f"stale embedded copy of {key}"


def test_inline_templates_render_without_filesystem():
    from jinja2 import DictLoader, Environment

    env = Environment(loader=DictLoader(TEMPLATES), autoescape=True)
    env.globals.update(
        url_for=lambda *a, **k: "/",
        csrf_token=lambda: "token",
        get_flashed_messages=lambda *a, **k: [],
        current_user=None,
        request=None,
    )
    html = env.get_template("error.html").render(code=404, message="Nope.")
    assert "Error 404" in html
    assert "Nope." in html
