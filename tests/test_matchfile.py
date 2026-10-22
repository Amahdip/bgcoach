"""Match file parsing and replay (server/matchfile.py)."""
import json
import os

import pytest

import bg
import matchfile
from conftest import FIXTURES


def load(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


@pytest.mark.parametrize("name", ["match_gnubg.mat", "match_xg.mat", "match.sgf"])
def test_replay_matches_the_real_games(name):
    truth = [m for game in json.loads(load("truth.json")) for m in game]
    match = matchfile.parse(load(name), name)
    assert match["players"] == ["Alice", "Bob"]
    assert match["length"] == 5
    assert [g["score"] for g in match["games"]] == [[0, 0], [1, 0], [2, 0]]
    rows = list(matchfile.replay(match))
    assert len(rows) == len(truth)
    for (_, _, p, board, dice, mv), (tp, td, tmv) in zip(rows, truth):
        assert p == tp and list(dice) == td
        if tmv is None:
            assert mv is None
        else:
            assert bg.apply_move(board, mv) == bg.apply_move(board, tuple(tmv))


@pytest.mark.parametrize("text,segs", [
    ("24/18* 13/9", [(24, 18, True), (13, 9, False)]),
    ("13/7(2)", [(13, 7, False), (13, 7, False)]),
    ("bar/22 6/off", [(25, 22, False), (6, 0, False)]),
    ("25/22 6/0", [(25, 22, False), (6, 0, False)]),
    ("8/2*/1", [(8, 2, True), (2, 1, False)]),
])
def test_parse_move_text(text, segs):
    assert matchfile.parse_move_text(text) == segs


def test_rejects_non_match_file():
    with pytest.raises(matchfile.MatchFileError):
        matchfile.parse("hello world", "notes.mat")


def test_illegal_move_is_reported():
    text = load("match_xg.mat").replace("31: 8/5 6/5", "31: 8/4 6/5", 1)
    with pytest.raises(matchfile.MatchFileError, match="illegal move"):
        list(matchfile.replay(matchfile.parse(text, "x.mat")))
