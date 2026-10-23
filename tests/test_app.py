"""API endpoints, called directly on the main thread (gnubg must not run on
another thread, which rules out FastAPI's TestClient) against a temp database."""
import asyncio
import json
import os

import pytest
from fastapi import HTTPException

import app
import bg
import explain
import importer
from conftest import FIXTURES

START = bg.from_id("4HPwATDgc/ABMA")


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module", autouse=True)
def positions():
    """A few opening positions instead of a generated database."""
    for dice in [(3, 1), (6, 4), (5, 2), (4, 2), (6, 1)]:
        a = bg.analyse(START, dice)
        app.conn.execute(
            """insert or ignore into positions (pid, dice, kind, pips_me, pips_opp, best_eq, gap, analysis, plies)
               values (?, ?, 'opening', 167, 167, ?, ?, ?, 2)""",
            (bg.to_id(START), f"{dice[0]}-{dice[1]}", a[0]["equity"], a[0]["equity"] - a[1]["equity"], json.dumps(a)),
        )
    app.conn.commit()


def test_wrong_answer_makes_a_card_due_tomorrow():
    pos = run(app.next_position(None, x_user="t1"))
    assert pos["mode"] == "new" and len(pos["legal"]) > 1
    r = run(app.answer(app.Answer(position_id=pos["id"], result=pos["legal"][-1], ms=3000), "t1"))
    assert r["rank"] > 1 and r["grade"] in ("doubtful", "error", "blunder") and r["severity"] == r["grade"]
    assert r["card"]["state"] == "learning"
    # Not shown again today: the next position is a different, new one.
    nxt = run(app.next_position(None, x_user="t1"))
    assert nxt["id"] != pos["id"] and nxt["mode"] == "new"


def test_right_answer_makes_no_card():
    pos = run(app.next_position(None, x_user="t2"))
    r = run(app.answer(app.Answer(position_id=pos["id"], result=pos["legal"][0]), "t2"))
    assert r["rank"] == 1 and r["card"] is None


def test_illegal_answer_rejected():
    pos = run(app.next_position(None, x_user="t3"))
    with pytest.raises(HTTPException) as e:
        run(app.answer(app.Answer(position_id=pos["id"], result={"me": [0] * 25, "opp": [0] * 25}), "t3"))
    assert e.value.status_code == 400


def test_explain_without_api_key_uses_templates():
    explain._client = None
    pos = run(app.next_position(None, x_user="t4"))
    r = run(app.explain_position(pos["id"], 1))
    assert r["source"] == "template" and r["text"] and r["facts"]["other"]["rank"] == 2


def test_import_queues_mistakes_once():
    with open(os.path.join(FIXTURES, "match_gnubg.mat")) as f:
        text = f.read()
    pv = run(app.import_preview(app.MatchUpload(filename="m.mat", text=text)))
    assert pv["players"] == ["Alice", "Bob"] and pv["games"] == 3
    res = run(app.import_match(app.MatchUpload(filename="m.mat", text=text, player=1), "t5"))
    assert res["decisions"] == pv["decisions"][1] and res["mistakes"]
    stats = run(app.stats("t5"))
    assert stats["deck"]["queued"] == len(res["mistakes"]) and stats["imports"][0]["mistakes"] == len(res["mistakes"])
    # Queued cards are served biggest error first.
    first = run(app.next_position(None, x_user="t5"))
    assert first["mode"] == "queued" and first["id"] == res["mistakes"][0]["position_id"]
    with pytest.raises(HTTPException) as e:
        run(app.import_match(app.MatchUpload(filename="m.mat", text=text, player=1), "t5"))
    assert e.value.status_code == 409


def test_modes():
    user = "t6"
    pos = run(app.next_position(None, "mixed", None, x_user=user))
    run(app.answer(app.Answer(position_id=pos["id"], result=pos["legal"][-1]), user))
    app.conn.execute("update cards set due = '2000-01-01T00:00:00+00:00' where user = ?", [user])
    app.conn.commit()

    assert run(app.next_position(None, "review", None, x_user=user))["id"] == pos["id"]
    new = run(app.next_position(None, "new", None, x_user=user))
    assert new["mode"] == "new" and new["id"] != pos["id"]
    # Mixed: the due card first, but right after a review comes a new position.
    assert run(app.next_position(None, "mixed", None, x_user=user))["id"] == pos["id"]
    assert run(app.next_position(None, "mixed", "learning", x_user=user))["mode"] == "new"


def test_review_mode_without_cards_says_so():
    with pytest.raises(HTTPException) as e:
        run(app.next_position(None, "review", x_user="t7"))
    assert e.value.status_code == 404 and "No reviews due" in e.value.detail
