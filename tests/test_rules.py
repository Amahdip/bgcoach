"""Move generation, notation and move application (server/bg.py)."""
import random

import gnubg
import pytest

import bg

START = bg.from_id("4HPwATDgc/ABMA")


def board(me, opp):
    """Build a board from {point: count} dicts (point 25 = bar)."""
    m, o = [0] * 25, [0] * 25
    for p, n in me.items():
        m[p - 1] = n
    for p, n in opp.items():
        o[p - 1] = n
    return (tuple(o), tuple(m))


@pytest.mark.parametrize("dice,count", [((6, 4), 14), ((6, 6), 11), ((5, 5), 4), ((3, 1), 16)])
def test_opening_move_counts(dice, count):
    assert len(bg.legal_moves(START, dice)) == count


def test_matches_gnubg_move_list():
    """Same set of resulting positions as gnubg for positions without bear-offs
    (gnubg.findbestmoves truncates bear-off moves, which is why we generate our own)."""
    random.seed(11)
    checked = 0
    for _ in range(6):
        b = START
        for _ in range(60):
            if bg.game_over(b):
                break
            d = bg.roll()
            mine = bg.legal_moves(b, d)
            if not any(0 in mv[1::2] for mv, _ in mine):
                ref = {bg.apply_move(b, m["move"])
                       for m in gnubg.findbestmoves(b, bg.money_cube(), bg.ctx(0), d) if m["move"]}
                assert {res for _, res in mine} == ref, (bg.to_id(b), d)
                checked += 1
            mv = bg.noisy_move(b, d)
            if mv:
                b = bg.apply_move(b, mv)
            b = bg.swap(b)
    assert checked > 100


def test_bear_off_both_dice():
    b = board({1: 2, 3: 3, 5: 2}, {6: 15})
    texts = {bg.move_text(b, mv) for mv, _ in bg.legal_moves(b, (6, 3))}
    assert texts == {"5/off 3/off", "5/off 5/2"}


def test_bar_must_enter_first():
    b = board({25: 1, 6: 14}, {6: 15})
    assert all(mv[0] == 25 for mv, _ in bg.legal_moves(b, (4, 2)))


def test_closed_board_no_move():
    b = board({25: 1, 6: 14}, {1: 2, 2: 2, 3: 2, 4: 2, 5: 2, 6: 3, 13: 2})
    assert bg.legal_moves(b, (3, 1)) == []


def test_must_play_larger_die_when_only_one_fits():
    # One checker on 12 and my 1-point blocked: 12/6 or 12/7 can be played, but
    # never both (the second die would land on the 1-point). Only one die can be
    # used, so it has to be the 6.
    b = board({12: 1}, {24: 2})
    assert {bg.move_text(b, mv) for mv, _ in bg.legal_moves(b, (6, 5))} == {"12/6"}


def test_hit_goes_to_bar():
    b = board({24: 2, 13: 5, 8: 3, 6: 5}, {24: 2, 13: 5, 8: 3, 6: 4, 18: 1})  # opponent blot on my 7
    opp, me = bg.apply_move(b, (13, 7))
    assert opp[24] == 1 and opp[24 - 7] == 0 and me[6] == 1


@pytest.mark.parametrize("move,text", [
    ((24, 18, 18, 14), "24/14"),
    ((13, 8, 13, 8, 8, 3, 8, 3), "13/3(2)"),
    ((8, 5, 6, 5), "8/5 6/5"),
])
def test_move_text(move, text):
    assert bg.move_text(START, move) == text


def test_move_text_marks_hits():
    b = board({24: 2, 13: 5, 8: 3, 6: 5}, {24: 2, 13: 5, 8: 3, 6: 4, 18: 1})
    assert bg.move_text(b, (13, 7)) == "13/7*"


def test_analyse_ranks_best_first():
    a = bg.analyse(START, (3, 1))
    assert a[0]["text"] == "8/5 6/5"
    assert all(a[i]["equity"] >= a[i + 1]["equity"] for i in range(7))
    assert all(m["ply"] == 2 for m in a[:8])
