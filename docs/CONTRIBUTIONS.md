# Contributions - EF101-P01 Hangman

> Exactly three members. Replace the `Member N` placeholders with real names
> (and IDs if required) before submission; keep the responsibilities truthful.

| Member | Responsibility | Key files |
|---|---|---|
| Member 1 - (replace with name) | Game engine, scoring, word/difficulty services, vocabulary + demo seed scripts, schema design | `src/app/services/game_engine.py`, `src/app/services/scoring.py`, `src/app/services/word_service.py`, `scripts/seed_words.py`, `scripts/seed_demo.py`, `schema.sql`, `db_init.sql` |
| Member 2 - (replace with name) | Flask routes (game, leaderboard, auth, admin), Jinja templates, CSS/JS frontend, Lucide icon vendoring | `src/app/routes/*.py`, `src/app/templates/*.html`, `src/app/static/css/style.css`, `src/app/static/js/game.js`, `src/app/static/icons/*` |
| Member 3 - (replace with name) | App factory/config, D1 + Workers integration, security hardening, test suite, documentation, deployment | `src/app/__init__.py`, `src/app/config.py`, `src/app/db.py`, `src/worker.py`, `wrangler.jsonc`, `pyproject.toml`, `tests/*.py`, `docs/*.md` |

## Joint work

All members reviewed the full codebase, ran the test suite, played the live
game, and prepared viva answers together. Viva readiness is joint: any member
can explain the browser/server split, the scoring formula, the difficulty
rule, the D1 schema, and the security controls.
