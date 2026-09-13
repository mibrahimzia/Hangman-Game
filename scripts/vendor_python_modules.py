"""Vendor pinned runtime deps into src/python_modules for Cloudflare Workers.

Workers Builds runs `pip install .` + `wrangler versions upload`, which never
executes `pywrangler sync` -- so third-party dependencies would be missing
from the uploaded bundle (wrangler only attaches files under src/, never
site-packages). This script reproduces what `sync` would produce -- the exact
pinned closure as pure-Python source, with binaries/tests/metadata stripped --
and commits it under src/, which wrangler DOES upload (moduleRoot walk).
src/worker.py adds the directory to sys.path.

Regenerate after changing pinned versions:
    python3 scripts/vendor_python_modules.py

Only stdlib is used; `pip` is invoked as a subprocess.
"""

import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PINS = ROOT / "docs" / "requirements-pinned.txt"
DEST = ROOT / "src" / "python_modules"

# Exact top-level import names expected by the app + worker entrypoint.
# Only these are copied (no dist-info, no stray files).
TOP_LEVEL = [
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

# Import check runs on CPython, so the Workers-only `workers` package (which
# needs Pyodide's `js` module) is verified by file presence instead.
IMPORT_CHECK = [name for name in TOP_LEVEL if name not in ("workers",)]
WORKERS_REQUIRED_FILES = ["__init__.py", "wsgi.py", "entrypoints.py"]

PRUNE_DIR_NAMES = {
    "__pycache__",
    "tests",
    "test",
    "testing",
    "testsuite",
    "docs",
    "doc",
    "examples",
    "example",
    "demos",
    "benchmarks",
    "bench",
}
PRUNE_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".so",
    ".pyd",
    ".dll",
    ".dylib",
    ".pyi",
    ".pyx",
    ".pxd",
    ".c",
    ".h",
    ".txt",
    ".md",
    ".rst",
    ".po",
    ".mo",
    ".cfg",
    ".toml",
    ".in",
    ".dist-info",
}


def _dir_size(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _prune(tree: Path) -> tuple[int, int]:
    """Delete binaries/tests/metadata from an install tree. Returns (removed, kept)."""
    removed = 0
    for dirpath, dirnames, filenames in os.walk(tree, topdown=True):
        for name in list(dirnames):
            if name in PRUNE_DIR_NAMES or name.endswith(".dist-info"):
                shutil.rmtree(os.path.join(dirpath, name))
                removed += 1
                dirnames.remove(name)
        for name in filenames:
            suffix = os.path.splitext(name)[1].lower()
            if suffix in PRUNE_SUFFIXES and not name.startswith(("LICENSE", "NOTICE")):
                os.unlink(os.path.join(dirpath, name))
                removed += 1
    kept = sum(1 for _ in tree.rglob("*") if _.is_file())
    return removed, kept


def main() -> None:
    if not PINS.is_file():
        sys.exit(f"pins file not found: {PINS}")
    staging = Path(tempfile.mkdtemp(prefix="vendor-staging-"))
    try:
        # --no-deps: the pins file already lists the full transitive closure,
        # so every version installed is exactly the audited pin.
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--quiet",
                "--no-deps",
                "--target",
                str(staging),
                "-r",
                str(PINS),
            ],
            check=True,
        )
        # Snapshot distribution metadata BEFORE pruning: minimal dist-info
        # dirs are re-created at the end so importlib.metadata.version()
        # keeps working (e.g. Flask's test client reads Werkzeug's version).
        dist_infos = {}
        for entry in staging.iterdir():
            metadata_file = entry / "METADATA"
            if entry.name.endswith(".dist-info") and metadata_file.is_file():
                meta = metadata_file.read_text(encoding="utf-8")
                name = re.search(r"^Name: (.+)$", meta, re.M).group(1).strip()
                ver = re.search(r"^Version: (.+)$", meta, re.M).group(1).strip()
                dist_infos[entry.name] = (name, ver)

        removed, _ = _prune(staging)

        missing = [n for n in TOP_LEVEL if not (staging / n).exists()]
        if missing:
            sys.exit(f"vendoring failed, missing top-level entries: {missing}")

        # Prove the C-extension packages fall back to pure Python: the staging
        # tree has no .so files left, so a bare import exercises the fallback.
        check_code = (
            ";".join(f"import {n[:-3] if n.endswith('.py') else n}" for n in IMPORT_CHECK)
            + ";import markupsafe, wrapt;print('pure-python import check OK')"
        )
        env = {
            **os.environ,
            "PYTHONPATH": str(staging),
            "PYTHONNOUSERSITE": "1",
        }
        subprocess.run(
            [sys.executable, "-S", "-c", check_code],
            check=True,
            env=env,
            cwd=tempfile.gettempdir(),
        )
        # The import check above regenerates __pycache__; prune again so no
        # bytecode ships (it doubles the size and compresses poorly).
        removed_again, _ = _prune(staging)
        removed += removed_again

        # Drop the Werkzeug interactive debugger (~0.5 MB of UI assets): it is
        # imported lazily only by app.run(debug=True), which never runs on
        # Workers (the app is served via workers.wsgi instead).
        shutil.rmtree(staging / "werkzeug" / "debug", ignore_errors=True)

        for required in WORKERS_REQUIRED_FILES:
            if not (staging / "workers" / required).is_file():
                sys.exit(f"workers package incomplete, missing workers/{required}")

        if DEST.exists():
            shutil.rmtree(DEST)
        DEST.mkdir(parents=True)
        for name in TOP_LEVEL:
            src = staging / name
            if src.is_dir():
                shutil.copytree(src, DEST / name)
            else:
                shutil.copy2(src, DEST / name)
        for dirname, (name, ver) in sorted(dist_infos.items()):
            minimal = DEST / dirname
            minimal.mkdir()
            (minimal / "METADATA").write_text(
                f"Metadata-Version: 2.1\nName: {name}\nVersion: {ver}\n",
                encoding="utf-8",
            )

        pins_text = PINS.read_text(encoding="utf-8")
        (DEST / "VENDORED.txt").write_text(
            "Vendored Cloudflare Workers runtime closure.\n"
            f"Generated by scripts/vendor_python_modules.py from docs/requirements-pinned.txt\n"
            f"Entries: {len(TOP_LEVEL)} top-level, pruned {removed} junk files/dirs.\n\n"
            + pins_text,
            encoding="utf-8",
        )

        raw_size = _dir_size(DEST)
        archive = staging / "size-probe.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            tar.add(DEST, arcname="python_modules")
        gz_size = archive.stat().st_size
        file_count = sum(1 for _ in DEST.rglob("*") if _.is_file())
        print(f"vendored {file_count} files into {DEST.relative_to(ROOT)}")
        print(f"size: {raw_size / 1e6:.2f} MB raw, {gz_size / 1e6:.2f} MB gzipped")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    main()
