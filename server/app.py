"""bgcoach API + static SPA.

    uvicorn app:app --app-dir server --port 8000
"""
import json
import random
import os
import threading
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import bg
import db
import explain
import explain_fa
import facts
import importer
import matchfile
import srs

WEB_DIR = os.path.join(os.path.dirname(__file__), "..", "web")
KINDS = ["opening", "middlegame", "race", "bearoff", "backgame", "backgame-opp"]

app = FastAPI(title="bgcoach")
conn = db.connect()
# gnubg segfaults when called from any thread but the main one, so every
# endpoint is `async def`: FastAPI then runs it on the event loop, which uvicorn
# runs on the main thread. Calls are short (< 0.5 s), so blocking is fine here.
lock = threading.Lock()


def user_of(x_user):
    return (x_user or "me").strip()[:50] or "me"


def result_of(board, move):
    opp, me = bg.apply_move(board, move)
    return {"me": list(me), "opp": list(opp)}


def position_payload(row, mode, card=None):
    board = bg.from_id(row["pid"])
    analysis = json.loads(row["analysis"])
    d1, d2 = (int(x) for x in row["dice"].split("-"))
    return {
        "id": row["id"],
        "pid": row["pid"],
        "dice": [d1, d2],
        "kind": row["kind"],
        "pips": {"me": row["pips_me"], "opp": row["pips_opp"]},
        "board": {"opp": list(board[0]), "me": list(board[1])},
        # Final positions of every legal move, so the client can tell when the
        # user has finished a legal play. No equities until they answer.
        "legal": [result_of(board, m["move"]) for m in analysis],
        "mode": mode,
        "card": card and {k: card[k] for k in ("due", "interval_d", "reps", "lapses", "state", "origin", "last_severity")},
    }


def today_counts(user):
    """Reviews done and queued cards introduced today (UTC), for the daily caps."""
    reviews = conn.execute(
        """select count(*) from attempts where user = ? and source = 'train' and was_review = 1
           and date(created_at) = date('now')""", [user]).fetchone()[0]
    introduced = conn.execute(
        """select count(*) from cards where user = ? and origin is not null
           and date(introduced_at) = date('now')""", [user]).fetchone()[0]
    return reviews, introduced


MODES = ("mixed", "review", "new")
CARD_MODES = ("learning", "review", "queued")


@app.get("/api/next")
async def next_position(kind: Optional[str] = None, mode: str = "mixed", prev: Optional[str] = None,
                        x_user: Optional[str] = Header(None)):
    """Next position to play.

    mode=mixed  : due cards and new positions alternate (prev = the mode of the
                  position just played), so reviews never block new positions.
    mode=review : only cards (missed, due reviews, queued imports), no daily caps.
    mode=new    : only positions the user has never seen.
    """
    user = user_of(x_user)
    mode = mode if mode in MODES else "mixed"
    with lock:
        kind_sql, kind_args = ("and p.kind = ?", [kind]) if kind in KINDS else ("", [])
        now = srs.iso(srs.now())
        reviews_today, introduced_today = today_counts(user)
        capped = mode != "review"

        def card_query(where, order):
            return conn.execute(
                f"""select c.*, p.* from cards c join positions p on p.id = c.position_id
                    where c.user = ? and {where} {kind_sql} order by {order} limit 1""",
                [user, *([now] if "?" in where else []), *kind_args],
            ).fetchone()

        def next_card():
            # Missed cards that are due again (a day after the miss) come first,
            # then due reviews (biggest error first), then queued imports.
            card = card_query("c.state = 'learning' and c.due <= ?", "c.due")
            if card:
                return position_payload(card, "learning", dict(card))
            if not capped or reviews_today < srs.MAX_REVIEWS_PER_DAY:
                card = card_query("c.state = 'review' and c.due <= ?", "c.priority desc, c.due")
                if card:
                    return position_payload(card, "review", dict(card))
            if not capped or introduced_today < srs.NEW_PER_DAY:
                card = card_query("c.state = 'new'", "c.priority desc")
                if card:
                    return position_payload(card, "queued", dict(card))
            return None

        def new_position():
            unseen = f"""select p.* from positions p
                         where not exists (select 1 from attempts a where a.user = ? and a.position_id = p.id)
                         {kind_sql}"""
            max_id = conn.execute("select coalesce(max(id), 0) from positions").fetchone()[0]
            start = random.randint(0, max_id)
            row = conn.execute(unseen + " and p.id >= ? order by p.id limit 1", [user, *kind_args, start]).fetchone()
            row = row or conn.execute(unseen + " order by p.id limit 1", [user, *kind_args]).fetchone()
            return position_payload(row, "new") if row else None

        if mode == "review":
            pos = next_card()
            if not pos:
                nxt = conn.execute(
                    f"""select min(c.due) from cards c join positions p on p.id = c.position_id
                        where c.user = ? and c.state != 'new' {kind_sql}""", [user, *kind_args]).fetchone()[0]
                raise HTTPException(404, "No reviews due right now." + (f" Next one is due {nxt}." if nxt else ""))
            return pos
        if mode == "new":
            order = [new_position]
        elif prev in CARD_MODES:
            order = [new_position, next_card]  # just did a review: a new position next
        else:
            order = [next_card, new_position]
        for pick in order:
            pos = pick()
            if pos:
                return pos
        raise HTTPException(404, "No positions left. Run server/generate.py to make more.")


@app.get("/api/position/{position_id}")
async def get_position(position_id: int, x_user: Optional[str] = Header(None)):
    with lock:
        row = conn.execute("select * from positions where id = ?", [position_id]).fetchone()
        if not row:
            raise HTTPException(404)
        card = conn.execute(
            "select * from cards where user = ? and position_id = ?", [user_of(x_user), position_id]
        ).fetchone()
        return position_payload(row, "practice", card and dict(card))


class Answer(BaseModel):
    position_id: int
    result: dict  # {"me": [25 ints], "opp": [25 ints]} after the user's move
    ms: Optional[int] = None


@app.post("/api/answer")
async def answer(a: Answer, x_user: Optional[str] = Header(None)):
    user = user_of(x_user)
    with lock:
        row = conn.execute("select * from positions where id = ?", [a.position_id]).fetchone()
        if not row:
            raise HTTPException(404)
        board = bg.from_id(row["pid"])
        analysis = json.loads(row["analysis"])
        idx = next(
            (i for i, m in enumerate(analysis) if result_of(board, m["move"]) == a.result),
            None,
        )
        if idx is None:
            raise HTTPException(400, "Not a legal move")
        if analysis[idx].get("ply", row["plies"] if idx < 8 else 0) < row["plies"]:
            # Outside the deeply analysed candidates: score it at the same depth
            # so the error is fair, and keep the result for next time.
            idx = bg.refine(board, analysis, idx, row["plies"])
            conn.execute("update positions set analysis = ? where id = ?", [json.dumps(analysis), row["id"]])
        chosen = analysis[idx]
        best = analysis[0]["equity"]
        rank = idx + 1
        eq_loss = max(0.0, best - chosen["equity"])
        g = srs.grade(rank, a.ms, eq_loss)
        sev = srs.severity(eq_loss) if rank > 1 else None

        card = conn.execute(
            "select * from cards where user = ? and position_id = ?", [user, a.position_id]
        ).fetchone()
        # was_review: 0 = not a card yet, 1 = review, 2 = first time a queued card is shown
        was_review = 0 if card is None else (2 if card["state"] == "new" else 1)
        updated = srs.schedule(dict(card) if card else None, g)
        if updated:
            conn.execute(
                """insert into cards (user, position_id, due, interval_d, ease, reps, lapses, last_review,
                                      state, priority, introduced_at, last_severity)
                   values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   on conflict(user, position_id) do update set
                   due = excluded.due, interval_d = excluded.interval_d, ease = excluded.ease,
                   reps = excluded.reps, lapses = excluded.lapses, last_review = excluded.last_review,
                   state = excluded.state, priority = max(cards.priority, excluded.priority),
                   introduced_at = coalesce(cards.introduced_at, excluded.introduced_at),
                   last_severity = coalesce(excluded.last_severity, cards.last_severity)""",
                [user, a.position_id, updated["due"], updated["interval_d"], updated["ease"],
                 updated["reps"], updated["lapses"], updated["last_review"], updated["state"],
                 eq_loss, updated["last_review"], sev],
            )
        conn.execute(
            """insert into attempts (user, position_id, move, move_text, eq_loss, rank, grade, was_review, ms)
               values (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [user, a.position_id, json.dumps(chosen["move"]), chosen["text"], eq_loss, rank, g,
             was_review, a.ms],
        )
        conn.commit()

        previous = conn.execute(
            """select move_text, eq_loss, created_at from attempts
               where user = ? and position_id = ? order by id desc limit 6 offset 1""",
            [user, a.position_id],
        ).fetchall()
        return {
            "rank": rank,
            "eq_loss": eq_loss,
            "grade": g,
            "severity": sev,
            "chosen": chosen["text"],
            "moves": [
                {"rank": i + 1, "text": m["text"], "equity": m["equity"], "loss": best - m["equity"],
                 "result": result_of(board, m["move"])}
                # Only moves scored at full depth are comparable, plus the user's own.
                for i, m in enumerate(analysis)
                if i == idx or (i < 10 and m.get("ply", row["plies"] if i < 8 else 0) == row["plies"])
            ],
            "chosen_index": idx,
            "card": updated and {k: updated[k] for k in ("due", "interval_d", "reps", "lapses", "state")},
            "thresholds": {"doubtful": srs.DOUBTFUL, "error": srs.ERROR, "blunder": srs.BLUNDER},
            "history": [dict(r) for r in previous],
            "plies": row["plies"],
        }


@app.get("/api/stats")
async def stats(x_user: Optional[str] = Header(None)):
    user = user_of(x_user)
    with lock:
        q = lambda sql, *args: conn.execute(sql, [user, *args])
        now = srs.iso(srs.now())
        # Training numbers only; mistakes found in imported matches are listed separately.
        sev = srs.severity_counts_sql("eq_loss")
        tot = q(f"""select count(*) n, coalesce(sum(rank = 1), 0) best, coalesce(avg(eq_loss), 0) loss, {sev}
                    from attempts where user = ? and source = 'train'""").fetchone()
        by_kind = q(f"""select p.kind, count(*) n, sum(a.rank = 1) best, avg(a.eq_loss) loss,
                               {srs.severity_counts_sql("a.eq_loss", "a.rank")}
                        from attempts a join positions p on p.id = a.position_id
                        where a.user = ? and a.source = 'train' group by p.kind order by n desc""").fetchall()
        daily = q(f"""select date(created_at) day, count(*) n, sum(rank = 1) best, avg(eq_loss) loss, {sev}
                      from attempts where user = ? and source = 'train' and created_at >= date('now', '-30 days')
                      group by day order by day""").fetchall()
        deck = conn.execute(
            """select
                 coalesce(sum(state = 'new'), 0) queued,
                 coalesce(sum(state = 'learning'), 0) learning,
                 coalesce(sum(state = 'review' and interval_d < ?), 0) young,
                 coalesce(sum(state = 'review' and interval_d >= ?), 0) learned,
                 coalesce(sum(state != 'new' and due <= ?), 0) due
               from cards where user = ?""",
            [srs.LEARNED_DAYS, srs.LEARNED_DAYS, now, user]).fetchone()
        forecast = q("""select date(due) day, count(*) n from cards
                        where user = ? and state != 'new' and date(due) <= date('now', '+6 days')
                        group by day order by day""").fetchall()
        reviews_today, introduced_today = today_counts(user)
        mistakes = q(f"""select a.position_id, a.move_text, a.eq_loss, a.created_at, a.source, p.kind, p.dice,
                               c.due, c.lapses, c.state, c.origin, {srs.severity_sql("a.eq_loss")} severity
                        from attempts a join positions p on p.id = a.position_id
                        left join cards c on c.user = a.user and c.position_id = a.position_id
                        where a.user = ? and a.rank > 1 and a.eq_loss >= {srs.DOUBTFUL}
                        order by a.id desc limit 25""").fetchall()
        npos = conn.execute("select count(*) from positions").fetchone()[0]
        return {
            "attempts": tot["n"],
            "best": tot["best"],
            "avg_loss": tot["loss"],
            "severity": {"doubtful": tot["doubtful"], "error": tot["errors"], "blunder": tot["blunders"]},
            "positions": npos,
            "deck": dict(deck),
            "today": {"reviews": reviews_today, "max_reviews": srs.MAX_REVIEWS_PER_DAY,
                      "introduced": introduced_today, "max_new": srs.NEW_PER_DAY},
            "forecast": [dict(r) for r in forecast],
            "by_kind": [dict(r) for r in by_kind],
            "daily": [dict(r) for r in daily],
            "mistakes": [dict(r) for r in mistakes],
            "imports": [dict(r) for r in q(
                """select id, filename, players, player, length, games, decisions, mistakes, total_loss, created_at
                   from imports where user = ? order by id desc limit 20""")],
        }


@app.get("/api/explain/{position_id}")
async def explain_position(position_id: int, chosen: int):
    """Facts comparing the best play with the user's (`chosen` = its index in the
    analysis, from /api/answer), plus a Persian explanation written by Claude."""
    with lock:
        row = conn.execute("select * from positions where id = ?", [position_id]).fetchone()
        if not row:
            raise HTTPException(404)
        analysis = json.loads(row["analysis"])
        if len(analysis) < 2 or not 0 <= chosen < len(analysis):
            raise HTTPException(400, "Nothing to compare")
        board = bg.from_id(row["pid"])
        dice = tuple(int(x) for x in row["dice"].split("-"))
        f = facts.compare(board, dice, analysis, chosen, row["plies"])
        # The wording differs when the user found the best play, so that's part of the key.
        other_move = ("runner-up:" if f["user_found_best"] else "") + f["other"]["move"]
        text = explain.cached(conn, position_id, other_move)
    if text:
        return {"facts": f, "text": text, "source": "claude", "cached": True}
    try:
        # Not under the lock: this waits on the network, and other requests can run meanwhile.
        text, model = await explain.write(f)
    except explain.Unavailable as e:
        # No API key (or the API failed): sentences built from the facts with fixed templates.
        # Not cached, so a Claude explanation can replace it once a key is configured.
        return {"facts": f, "text": explain_fa.write(f), "source": "template", "note": str(e)}
    with lock:
        explain.store(conn, position_id, other_move, text, model)
    return {"facts": f, "text": text, "source": "claude", "cached": False}


class MatchUpload(BaseModel):
    filename: str
    text: str
    player: Optional[int] = None


@app.post("/api/import/preview")
async def import_preview(u: MatchUpload):
    with lock:
        try:
            return importer.preview(u.text, u.filename)
        except matchfile.MatchFileError as e:
            raise HTTPException(400, str(e))


@app.post("/api/import")
async def import_match(u: MatchUpload, x_user: Optional[str] = Header(None)):
    if u.player not in (0, 1):
        raise HTTPException(400, "Choose which player you are")
    with lock:
        try:
            return importer.import_match(conn, user_of(x_user), u.text, u.filename, u.player)
        except importer.AlreadyImported as e:
            raise HTTPException(409, str(e))
        except matchfile.MatchFileError as e:
            conn.rollback()
            raise HTTPException(400, str(e))


@app.middleware("http")
async def revalidate_static(request, call_next):
    # Always revalidate (ETag) so an edited app.js/style.css is picked up at once.
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/{path:path}")
def spa(path: str):
    return FileResponse(os.path.join(WEB_DIR, "index.html"))
