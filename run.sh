#!/bin/sh
# Start bgcoach on http://127.0.0.1:8765 (creates the venv and a starter database on first run).
set -e
cd "$(dirname "$0")"
# Optional settings such as ANTHROPIC_API_KEY (used for the Persian explanations).
[ -f .env ] && { set -a; . ./.env; set +a; }
PORT="${PORT:-8765}"
[ -d .venv ] || { uv venv -q -p 3.13 .venv && uv pip install -q -p .venv -r requirements.txt; }
# Refuse to start if something (e.g. a Docker container on IPv6) already answers on this
# port: the browser would reach that instead of bgcoach.
if ! .venv/bin/python -c "
import socket, sys
for host in ('127.0.0.1', '::1'):
    try:
        socket.create_connection((host, $PORT), timeout=0.3).close()
        sys.exit(1)
    except OSError:
        pass
"; then
  echo "Port $PORT is already in use. Stop that program or pick another port: PORT=8766 ./run.sh" >&2
  exit 1
fi
[ -f data/bgcoach.sqlite ] || .venv/bin/python server/generate.py --positions 2000 </dev/null
echo "bgcoach: http://127.0.0.1:$PORT"
exec .venv/bin/uvicorn app:app --app-dir server --host 127.0.0.1 --port "$PORT" </dev/null
