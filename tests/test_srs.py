"""Review scheduling (server/srs.py)."""
from datetime import datetime, timedelta, timezone

import pytest

import srs

T = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def due_days(card):
    return (datetime.fromisoformat(card["due"]) - T).total_seconds() / 86400


def test_grade():
    assert srs.grade(1, 5000) == "good"
    assert srs.grade(1, srs.SLOW_MS + 1) == "hard"
    assert srs.grade(3, 1000) == "again"


def test_correct_first_try_makes_no_card():
    assert srs.schedule(None, "good", T) is None


def test_miss_comes_back_tomorrow_not_today():
    c = srs.schedule(None, "again", T)
    assert c["state"] == "learning" and c["lapses"] == 1
    assert due_days(c) == 1


def test_intervals_grow():
    c = srs.schedule(None, "again", T)
    c = srs.schedule(c, "good", T)
    assert c["state"] == "review" and due_days(c) == 3
    c = srs.schedule(c, "good", T)
    assert due_days(c) == 7
    c = srs.schedule(c, "good", T)
    assert due_days(c) == pytest.approx(7 * 2.3, abs=1e-4)  # ease 2.5, lowered once by the miss


def test_miss_resets_and_lowers_ease():
    c = srs.schedule(None, "again", T)
    c = srs.schedule(c, "good", T)
    c = srs.schedule(c, "again", T)
    assert c["reps"] == 0 and c["lapses"] == 2 and due_days(c) == 1
    assert c["ease"] < 2.5


def test_ease_has_a_floor():
    c = srs.schedule(None, "again", T)
    for _ in range(20):
        c = srs.schedule(c, "again", T)
    assert c["ease"] == srs.MIN_EASE
