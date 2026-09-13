"""Database layer: Cloudflare D1 on Workers, SQLite locally.

Both backends share one schema (schema.sql) and one query style: prepared
statements with `?` placeholders and bound parameters. No SQL string
interpolation anywhere in this codebase.

On Workers, the D1 binding is exposed by the WSGI adapter as
``request.environ["workers.env"].DB`` and JS promises are awaited with
``pyodide.ffi.run_sync`` (the officially supported pattern).
"""

import os
import sqlite3

from flask import current_app, g, has_request_context, request


def _root_dir() -> str:
    here = os.path.abspath(__file__)  # src/app/db.py -> repo root is 3 levels up
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


def _schema_path() -> str:
    return os.path.join(_root_dir(), "schema.sql")


def _seed_path() -> str:
    return os.path.join(_root_dir(), "db_init.sql")


def get_workers_env():
    """Return the Cloudflare Workers env for this request, or None locally."""
    try:
        if has_request_context():
            return request.environ.get("workers.env")
    except RuntimeError:
        return None
    return None


def on_workers_request() -> bool:
    return get_workers_env() is not None


# ---------------------------------------------------------------------------
# D1 access (Workers only)
# ---------------------------------------------------------------------------


def _run_sync(coro):
    from pyodide.ffi import run_sync as _run_sync_impl

    return _run_sync_impl(coro)


def _js_to_py(value):
    """Best-effort conversion of a D1 RPC result into plain Python data."""
    to_py = getattr(value, "to_py", None)
    if callable(to_py):
        try:
            converted = to_py()
        except Exception:  # noqa: BLE001 - fall through to raw value
            return value
        return _js_to_py(converted)
    if isinstance(value, dict):
        return {key: _js_to_py(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_js_to_py(item) for item in value]
    return value


def _d1_prepare(sql, params):
    env = get_workers_env()
    stmt = env.DB.prepare(sql)
    if params:
        stmt = stmt.bind(*list(params))
    return stmt


def _d1_all(sql, params):
    res = _run_sync(_d1_prepare(sql, params).all())
    if isinstance(res, dict):
        rows = res.get("results", [])
    else:
        rows = getattr(res, "results", []) or []
    out = []
    for row in rows:
        row = _js_to_py(row)
        out.append(dict(row) if isinstance(row, dict) else {})
    return out


def _d1_one(sql, params):
    res = _run_sync(_d1_prepare(sql, params).first())
    if res is None:
        return None
    res = _js_to_py(res)
    return dict(res) if isinstance(res, dict) else None


def _d1_write(sql, params):
    res = _run_sync(_d1_prepare(sql, params).run())
    res = _js_to_py(res)
    if isinstance(res, dict):
        meta = res.get("meta", {}) or {}
        try:
            return int(meta.get("changes", 0))
        except (TypeError, ValueError):
            return 0
    return 0


# ---------------------------------------------------------------------------
# Local SQLite access
# ---------------------------------------------------------------------------


def get_local_connection() -> sqlite3.Connection:
    if "sqlite_conn" not in g:
        path = current_app.config["SQLITE_PATH"]
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        g.sqlite_conn = conn
    return g.sqlite_conn


def close_local_connection() -> None:
    conn = g.pop("sqlite_conn", None)
    if conn is not None:
        conn.close()


def _local_all(sql, params):
    cur = get_local_connection().execute(sql, tuple(params))
    return [dict(row) for row in cur.fetchall()]


def _local_one(sql, params):
    conn = get_local_connection()
    row = conn.execute(sql, tuple(params)).fetchone()
    # INSERT ... RETURNING flows through here, so always commit (harmless for SELECT).
    conn.commit()
    return dict(row) if row is not None else None


def _local_write(sql, params):
    conn = get_local_connection()
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur.rowcount


# ---------------------------------------------------------------------------
# Unified API used by app/models.py
# ---------------------------------------------------------------------------


def query_all(sql: str, params=()) -> list:
    if on_workers_request():
        return _d1_all(sql, params)
    return _local_all(sql, params)


def query_one(sql: str, params=()):
    if on_workers_request():
        return _d1_one(sql, params)
    return _local_one(sql, params)


def execute_write(sql: str, params=()) -> int:
    if on_workers_request():
        return _d1_write(sql, params)
    return _local_write(sql, params)


# ---------------------------------------------------------------------------
# Local database initialisation
# ---------------------------------------------------------------------------


def init_local_db(path: str, with_seed: bool = True) -> None:
    """Create a fresh local database from schema.sql (+ db_init.sql seed)."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    conn = sqlite3.connect(path)
    try:
        with open(_schema_path(), encoding="utf-8") as handle:
            conn.executescript(handle.read())
        seed_path = _seed_path()
        if with_seed and os.path.isfile(seed_path):
            with open(seed_path, encoding="utf-8") as handle:
                conn.executescript(handle.read())
        conn.commit()
    finally:
        conn.close()


def ensure_local_db(path: str) -> None:
    """Create the local database on first run if it (or its tables) is missing."""
    needs_init = True
    if os.path.isfile(path):
        probe = sqlite3.connect(path)
        try:
            row = probe.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'words'"
            ).fetchone()
            needs_init = row is None
        except sqlite3.DatabaseError:
            needs_init = True
        finally:
            probe.close()
    if needs_init:
        init_local_db(path, with_seed=True)
