"""Cloudflare Workers entrypoint (Python runtime only).

Serves the Flask app through the official WSGI adapter. The D1 binding is
exposed to Flask routes as ``request.environ["workers.env"].DB`` (see
``workers/wsgi.py`` -> ``build_environ``) and is consumed in app/db.py.

Deploy:
    pywrangler sync                      # vendor pyproject deps into src/vendor
    wrangler d1 execute hangman-db --file=./schema.sql
    wrangler d1 execute hangman-db --file=./db_init.sql
    wrangler secret put SECRET_KEY
    pywrangler deploy                    # or: wrangler deploy
"""

import os
import sys

try:
    from app import create_app
except ImportError:  # tolerate different bundle roots
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app import create_app

from workers import wsgi  # provided by the Workers Python runtime

app = create_app()


async def on_fetch(request, env):
    return await wsgi.fetch(app, request, env)
