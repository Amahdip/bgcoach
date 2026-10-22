#!/bin/sh
# Start bgcoach on http://localhost:8000 (creates the venv and a starter database on first run).
set -e
cd "$(dirname "$0")"
# Optional settings such as ANTHROPIC_API_KEY (used for the Persian explanations).
[ -f .env ] && { set -a; . ./.env; set +a; }
[ -d .venv ] || { uv venv -q -p 3.13 .venv && uv pip install -q -p .venv -r requirements.txt; }
[ -f data/bgcoach.sqlite ] || .venv/bin/python server/generate.py --positions 2000 </dev/null
exec .venv/bin/uvicorn app:app --app-dir server --port "${PORT:-8000}" </dev/null
