---
name: bgcoach
description: Run and operate the bgcoach backgammon trainer in this repo — start the server, generate more positions, import a .mat/.sgf match for a player, inspect a user's cards and progress in SQLite, check a position with gnubg, and verify UI changes in the browser. Use for any "run it", "add positions", "import my match", "why did it show X", or "check this position" request in this project.
---

# Operating bgcoach

Read `AGENTS.md` first for the board format and the gnubg main-thread rule.
All commands run from the repo root. `run.sh` creates `.venv` on first use; if it
doesn't exist yet, run `./run.sh` once (or `uv venv -p 3.13 .venv && uv pip install -p .venv -r requirements-dev.txt`).

## Start the app

```bash
PORT=8000 ./run.sh        # long-running: start it in the background
curl -s localhost:8000/api/stats | head -c 300
```

`run.sh` loads `.env` (see `.env.example`) and builds a 2000-position database on
first run (~1.5 min). Use another `PORT` if 8000 is taken. For experiments, point
`BGCOACH_DB` at a copy made with the backup API, never `cp` (WAL mode):

```bash
.venv/bin/python -c "import sqlite3; s=sqlite3.connect('data/bgcoach.sqlite'); d=sqlite3.connect('/tmp/bgcoach-copy.sqlite'); s.backup(d)"
BGCOACH_DB=/tmp/bgcoach-copy.sqlite .venv/bin/uvicorn app:app --app-dir server --port 8001
```

## Add positions

```bash
.venv/bin/python server/generate.py --positions 5000                 # ~22 positions/s
.venv/bin/python server/generate.py --positions 2000 --min-gap 0.04  # only clearer decisions
```

Safe to run while the server is up. Report the count per kind afterwards:

```bash
.venv/bin/python -c "import sqlite3; c=sqlite3.connect('data/bgcoach.sqlite'); print(c.execute('select kind, count(*) from positions group by kind order by 2 desc').fetchall())"
```

## Import a match

```bash
.venv/bin/python server/importer.py path/to/match.mat --player "Exact Name"   # --user, --min-error
```

The player name must match the file exactly; on a mismatch the script prints the two
names. A `MatchFileError` names the game and move that failed to replay — open the file
at that line; the usual causes are hand-edited positions or an unknown notation. If a
real export fails, add a trimmed copy to `tests/fixtures/` with a test before fixing
`server/matchfile.py`.

## Answer "why did it show me this?"

Order in `/api/next`: due learning cards → due reviews (biggest error first, max
`srs.MAX_REVIEWS_PER_DAY`) → queued imports (max `srs.NEW_PER_DAY`) → random unseen.
Inspect one user's deck (default user is `me`):

```bash
.venv/bin/python - <<'PY'
import sqlite3; c = sqlite3.connect('data/bgcoach.sqlite'); c.row_factory = sqlite3.Row
for r in c.execute("select position_id, state, due, interval_d, reps, lapses, round(priority,3) p, origin from cards where user='me' order by due limit 20"):
    print(dict(r))
PY
```

## Check a position with the engine

```bash
.venv/bin/python - <<'PY'
import sys; sys.path.insert(0, 'server')
import bg, facts
b = bg.from_id("4HPwATDgc/ABMA")          # gnubg position ID, player on roll = board[1]
a = bg.analyse(b, (3, 1))
for m in a[:5]: print(f"{m['text']:<16} {m['equity']:+.3f} ply {m['ply']}")
print(facts.compare(b, (3, 1), a, 1)["other"])
PY
```

## Verify a UI change

1. `node --check web/app.js`, then `.venv/bin/python -m pytest -q`.
2. Start a server on a database copy (above) so testing doesn't add attempts to the real user.
3. In the browser: Train → play a move (click = highlighted die, right-click = other die,
   click dice/Space = swap) → Submit → check the ranking, the Why panel and the start-position
   toggle (S / dice). Then Progress and Import (drop `tests/fixtures/match_gnubg.mat`).
4. Stop the extra server when done.
