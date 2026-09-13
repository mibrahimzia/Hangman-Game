"""Guards for the self-contained Workers bundle (src/python_modules/).

The deploy uploads src/ as-is, so the vendored closure must always be
complete, pure-Python, and in sync with the audited pins. These are static
checks (fast, no subprocess); regenerate the directory with
scripts/vendor_python_modules.py if they fail.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR = ROOT / "src" / "python_modules"
PINS = ROOT / "docs" / "requirements-pinned.txt"

REQUIRED_TOP_LEVEL = [
    "flask",
    "flask_login",
    "flask_wtf",
    "flask_limiter",
    "limits",
    "deprecated",
    "ordered_set",
    "wtforms",
    "jinja2",
    "markupsafe",
    "werkzeug",
    "click",
    "itsdangerous",
    "blinker",
    "packaging",
    "wrapt",
    "workers",
    "typing_extensions.py",
]


def test_vendored_top_level_complete():
    missing = [n for n in REQUIRED_TOP_LEVEL if not (VENDOR / n).exists()]
    assert not missing, f"missing vendored entries: {missing}"


def test_vendored_workers_adapter_present():
    for name in ("__init__.py", "wsgi.py", "entrypoints.py"):
        assert (VENDOR / "workers" / name).is_file(), f"workers/{name} missing"


def test_vendored_tree_is_pure_python():
    # __pycache__ dirs are git-ignored local bytecode caches (any local import
    # of the vendored tree creates them); they can never ship. Everything else
    # must be source: no binaries, no loose bytecode.
    bad = [
        str(p.relative_to(ROOT))
        for p in VENDOR.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.suffix.lower() in {".so", ".pyd", ".dll", ".pyc", ".pyo"}
    ]
    assert not bad, f"non-source files vendored: {bad[:10]}"


def test_vendored_dist_info_is_metadata_only():
    # Minimal dist-info dirs exist solely so importlib.metadata.version()
    # keeps working (e.g. Flask's test client reads Werkzeug's version).
    dist_infos = sorted(VENDOR.glob("*.dist-info"))
    for dist_info in dist_infos:
        entries = sorted(p.name for p in dist_info.iterdir())
        assert entries == ["METADATA"], f"{dist_info.name} carries extra files: {entries}"
    expected = sum(1 for line in PINS.read_text(encoding="utf-8").splitlines() if line.strip())
    assert len(dist_infos) == expected, f"{len(dist_infos)} dist-infos, {expected} pins"


def test_vendored_manifest_matches_pins():
    manifest = (VENDOR / "VENDORED.txt").read_text(encoding="utf-8")
    for line in PINS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            assert line in manifest, f"pin missing from VENDORED.txt: {line}"
