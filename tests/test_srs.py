"""Review scheduling (server/srs.py)."""
from datetime import datetime, timezone

import pytest

import srs

T = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)


def due_days(card):
    return (datetime.fromisoformat(card["due"]) - T).total_seconds() / 86400


@pytest.mark.parametrize("loss,sev", [(0.0, None), (0.019, None), (0.02, "doubtful"), (0.039, "doubtful"),
                                      (0.04, "error"), (0.079, "error"), (0.08, "blunder"), (0.5, "blunder")])
def test_severity_thresholds(loss, sev):
    assert srs.severity(loss) == sev


def test_grade():
    assert srs.grade(1, 5000) == "good"
    assert srs.grade(1, srs.SLOW_MS + 1) == "hard"
    assert srs.grade(3, 1000, 0.05) == "error"
    assert srs.grade(2, 1000, 0.2) == "blunder"
    assert srs.grade(2, 1000, 0.01) == "hard"  # within 0.02 of the best: not a miss


def test_correct_or_close_makes_no_card():
    assert srs.schedule(None, "good", T) is None
    assert srs.schedule(None, "hard", T) is None


def test_doubtful_comes_back_in_three_days():
    c = srs.schedule(None, "doubtful", T)
    assert c["state"] == "learning" and due_days(c) == 3 and c["ease"] == pytest.approx(2.4)


def test_error_comes_back_tomorrow_not_today():
    c = srs.schedule(None, "error", T)
    assert c["state"] == "learning" and c["lapses"] == 1 and due_days(c) == 1
    assert c["ease"] == pytest.approx(2.3)


def test_blunder_needs_two_right_answers_in_a_row():
    c = srs.schedule(None, "blunder", T)
    assert due_days(c) == 1 and c["reps"] == -1 and c["ease"] == pytest.approx(2.2)
    c = srs.schedule(c, "good", T)
    assert due_days(c) == 1 and c["state"] == "learning"  # first right answer: another day
    c = srs.schedule(c, "good", T)
    assert due_days(c) == 3 and c["state"] == "review"


def test_intervals_grow():
    c = srs.schedule(None, "error", T)
    c = srs.schedule(c, "good", T)
    assert c["state"] == "review" and due_days(c) == 3
    c = srs.schedule(c, "good", T)
    assert due_days(c) == 7
    c = srs.schedule(c, "good", T)
    assert due_days(c) == pytest.approx(7 * 2.3, abs=1e-4)


def test_miss_resets_and_lowers_ease():
    c = srs.schedule(None, "error", T)
    c = srs.schedule(c, "good", T)
    c = srs.schedule(c, "blunder", T)
    assert c["reps"] == -1 and c["lapses"] == 2 and due_days(c) == 1
    assert c["ease"] == pytest.approx(2.0)


def test_ease_has_a_floor():
    c = srs.schedule(None, "blunder", T)
    for _ in range(20):
        c = srs.schedule(c, "blunder", T)
    assert c["ease"] == srs.MIN_EASE


def test_old_again_grade_still_works():
    assert srs.schedule(None, "again", T)["state"] == "learning"
