"""Cloudflare Workers entrypoint (Python runtime only).

Serves the Flask app through the official WSGI adapter from
``workers-runtime-sdk`` (a runtime dependency in pyproject.toml, mirroring the
official flask-todo example at
https://github.com/cloudflare/python-workers-examples)::

    Default = wsgi.entrypoint(app)

The D1 binding is exposed to Flask routes as
``request.environ["workers.env"].DB`` and is consumed in src/app/db.py.

Deploy (Workers Builds / connected repo):
    build:  python3 -m pip install workers-py uv && \\\\
            export PATH="$HOME/.local/bin:$PATH" && python3 -m pywrangler sync
    deploy: python3 -m pywrangler deploy

Deploy (CLI):
    pywrangler sync                      # vendors deps into ./python_modules
    wrangler d1 execute hangman-db --file=./schema.sql
    wrangler d1 execute hangman-db --file=./db_init.sql
    wrangler secret put SECRET_KEY
    pywrangler deploy                    # or: wrangler deploy
"""

import os
import sys

# Make sibling imports robust regardless of how the runtime sets sys.path:
# wrangler uploads every *.py under this file's directory (src/).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workers import wsgi  # noqa: E402  (bundled via the workers-runtime-sdk dep)

from app import create_app  # noqa: E402

Default = wsgi.entrypoint(create_app())
