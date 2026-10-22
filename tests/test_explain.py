"""Facts about a play (server/facts.py) and the Persian template text (server/explain_fa.py)."""
import pytest

import bg
import explain_fa
import facts

START = bg.from_id("4HPwATDgc/ABMA")


@pytest.fixture(scope="module")
def opening_31():
    analysis = bg.analyse(START, (3, 1))
    other = next(i for i, m in enumerate(analysis) if m["text"] == "24/23 13/10")
    return analysis, other


def test_facts_opening_31(opening_31):
    analysis, other = opening_31
    f = facts.compare(START, (3, 1), analysis, other)
    best, alt = f["best"], f["other"]
    assert best["move"] == "8/5 6/5" and alt["move"] == "24/23 13/10"
    assert best["points_made"] == [5] and best["blots"] == [] and best["shots_to_hit_you"] == 0
    assert alt["blots"] == [10, 23, 24] and alt["shots_to_hit_you"] >= 30
    assert alt["points_given_up"] == [24]
    assert best["win"] > alt["win"]
    assert alt["equity_lost"] > 0.1 and not f["user_found_best"]


def test_runner_up_when_best_found(opening_31):
    analysis, _ = opening_31
    f = facts.compare(START, (3, 1), analysis, 0)
    assert f["user_found_best"] and f["other"]["rank"] == 2


def test_longest_prime():
    side = [0] * 25
    for p in (4, 5, 6, 7, 8):
        side[p - 1] = 2
    side[10] = 3
    assert facts.longest_prime(side) == (5, 4, 8)


def test_persian_text(opening_31):
    analysis, other = opening_31
    text = explain_fa.write(facts.compare(START, (3, 1), analysis, other))
    assert "8/5 6/5" in text and "24/23 13/10" in text
    assert "34 تاس" in text or "35 تاس" in text or "36 تاس" in text  # shots against the blots
    assert "{" not in text and "}" not in text


def test_persian_text_when_best_found(opening_31):
    analysis, _ = opening_31
    assert explain_fa.write(facts.compare(START, (3, 1), analysis, 0)).startswith("آفرین")
