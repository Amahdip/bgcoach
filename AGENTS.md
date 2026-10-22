# AGENTS.md

Guide for AI coding agents (Claude Code, Codex, Cursor, ...) working on bgcoach.
Humans: start with [README.md](README.md).

## What this is

A backgammon checker-play trainer. Python 3.10–3.13 backend (FastAPI + the `gnubg`
engine module + SQLite), a no-build vanilla JS single-page app with an SVG board.

## Commands

```bash
./run.sh                                                   # venv + starter DB on first run, serves :8000
.venv/bin/python -m pytest -q                              # all tests (~5 s)
node --check web/app.js                                    # the only "build" check for the frontend
.venv/bin/python server/generate.py --positions 5000       # add self-play positions
.venv/bin/python server/importer.py match.mat --player Me  # import a match from the CLI
.venv/bin/uvicorn app:app --app-dir server --port 8000     # server without run.sh
```

Set `BGCOACH_DB=/tmp/x.sqlite` to work against a scratch database.

## Layout

| Path | Role |
|---|---|
| `server/bg.py` | Rules: legal moves, move application, notation; gnubg evaluation; `analyse()` |
| `server/generate.py` | Self-play position generator (noisy 0-ply bot, keeps real decisions) |
| `server/matchfile.py` | `.mat` / `.sgf` parser and replay |
| `server/importer.py` | Import a match: analyse the user's moves, queue mistakes as cards |
| `server/srs.py` | Spaced repetition schedule and daily caps |
| `server/facts.py` | Measurable facts about a play (shots, points, prime, chances) |
| `server/explain_fa.py` | Persian explanation from fixed templates (no API) |
| `server/explain.py` | Persian explanation via the Claude API, cached in `explanations` |
| `server/db.py` | SQLite schema + additive migrations |
| `server/app.py` | FastAPI endpoints + serves `web/` |
| `web/` | `index.html`, `app.js`, `style.css` — no framework, no bundler |
| `tests/` | pytest; `tests/fixtures/` has match files + `truth.json` |

## Conventions that matter

- **Board format** (same as gnubg): `(opp, me)`, two 25-int tuples, each from that side's
  own view. Index `i` is point `i+1`, index 24 is the bar. `board[1]` is on roll. Moves are
  flat tuples of `from, to` pairs, 1-based, `25` = bar, `0` = off. `bg.swap()` flips sides.
- **Never trust `gnubg.findbestmoves()` move tuples** — it truncates at the first bear-off
  (`5/off 3/off` comes back as `(5,)`). We generate moves in `bg.legal_moves()` and only ask
  gnubg to `evaluate()` positions. `tests/test_rules.py` checks our generator against gnubg.
- **Equities are only comparable at the same depth.** `analyse()` scores everything at
  0-ply and the top 8 at `plies` (2); each entry carries `"ply"`. Anything that ranks a move
  outside the top 8 must call `bg.refine()` first (see `app.answer`, `importer`).
- **gnubg segfaults off the main thread.** Every endpoint is `async def` so FastAPI runs it on
  the event loop (main thread). Don't add sync (`def`) endpoints that touch gnubg, don't use
  `run_in_threadpool`, and don't use FastAPI's `TestClient` in tests (it runs the app on a
  portal thread) — call endpoint functions with `asyncio.run()` like `tests/test_app.py`.
  Don't call `gnubg.command("new session")`: it blocks waiting for stdin.
- **Schema changes are additive**: add to `SCHEMA` / `EXPLANATIONS` with `create ... if not
  exists`, or append to `db.MIGRATIONS` (column check + one-off SQL). Users have real data.
- **Copying the database**: it's in WAL mode. Use `sqlite3.Connection.backup()`, not `cp`,
  while anything has it open.
- **Explanations must stay grounded**: any new explanation text must come from numbers in
  `facts.py`. The Claude prompt (`explain.SYSTEM`) forbids inventing facts; keep it that way.
  Persian strings use the real ZWNJ character (U+200C), e.g. `می‌زند`.
- **Frontend**: plain DOM + template strings; escape user/file text with `esc()`. Keep move
  notation inside Persian text wrapped by `ltrMoves()` so it isn't reversed by bidi.
- Tests must not hit the network: `tests/conftest.py` clears `ANTHROPIC_API_KEY`.

## Before you finish

1. `.venv/bin/python -m pytest -q` passes.
2. `node --check web/app.js` passes.
3. For UI changes, run the server and click through the change (Train → answer → Why panel,
   Progress, Import). Static files are served with `Cache-Control: no-cache`.
4. Update README.md if behaviour or commands changed.
