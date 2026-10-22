"""Backgammon rules + a thin layer over the gnubg engine.

Board convention (same as gnubg): a pair (opp, me) of 25-int tuples, each seen
from that side's own perspective. Index i is point i+1; index 24 is the bar.
board[1] is the player on roll.

We generate legal moves ourselves and only ask gnubg to evaluate positions:
gnubg.findbestmoves() truncates move tuples at the first bear-off (to == 0),
so "5/off 3/off" comes back as (5,).
"""
import random
from collections import Counter

import gnubg

BAR = 25


def money_cube():
    return gnubg.cubeinfo(1, -1, 0, 0, (0, 0), 0)


def ctx(plies, noise=0.0):
    return gnubg.evalcontext(1, plies, 0 if noise else 1, 1, noise)


def from_id(pid):
    return tuple(tuple(side) for side in gnubg.positionfromid(pid))


def to_id(board):
    return gnubg.positionid(board)


def swap(board):
    return (board[1], board[0])


def pips(side):
    return sum((i + 1) * n for i, n in enumerate(side))


def game_over(board):
    return sum(board[0]) == 0 or sum(board[1]) == 0


# --- rules -----------------------------------------------------------------

def _hop(opp, me, frm, die):
    """Destination of one checker moved `die` pips from point `frm`, or None."""
    if me[frm - 1] == 0 or (me[24] and frm != BAR):
        return None
    to = frm - die
    if to >= 1:
        return to if opp[24 - to] < 2 else None
    if any(me[6:25]):
        return None  # not everything is home yet
    if to == 0 or not any(me[frm:24]):
        return 0  # exact bear-off, or the highest checker with a bigger die
    return None


def _play(opp, me, frm, to):
    me[frm - 1] -= 1
    hit = False
    if to:
        me[to - 1] += 1
        if opp[24 - to] == 1:
            opp[24 - to] = 0
            opp[24] += 1
            hit = True
    return hit


def apply_move(board, move):
    """Play `move` (flat tuple of from/to pairs, to == 0 is off) for the side on
    roll. The orientation is unchanged: the mover is still board[1]."""
    opp, me = list(board[0]), list(board[1])
    for frm, to in zip(move[0::2], move[1::2]):
        _play(opp, me, frm, to)
    return (tuple(opp), tuple(me))


def legal_moves(board, dice):
    """Every legal play for `dice`, one per distinct resulting position.

    Applies the "use as many dice as possible, else the larger die" rule.
    Returns [(move, result_board)]."""
    seqs = [list(dice) * 2] if dice[0] == dice[1] else [list(dice), list(dice[::-1])]
    found = {}  # result -> move
    best_len = 0

    doubles = dice[0] == dice[1]

    def walk(opp, me, rest, hops):
        nonlocal best_len
        moved = False
        if rest:
            # With doubles the order of hops doesn't matter, so only try
            # non-increasing start points.
            top = hops[-1][0] if doubles and hops else BAR
            for frm in range(top, 0, -1):
                to = _hop(opp, me, frm, rest[0])
                if to is None:
                    continue
                o2, m2 = list(opp), list(me)
                _play(o2, m2, frm, to)
                walk(o2, m2, rest[1:], hops + [(frm, to)])
                moved = True
        if not moved and hops:
            n = len(hops)
            if n > best_len:
                best_len = n
                found.clear()
            if n == best_len:
                key = (tuple(opp), tuple(me))
                found.setdefault(key, (tuple(x for h in hops for x in h), hops[0]))

    for rest in seqs:
        walk(list(board[0]), list(board[1]), rest, [])

    moves = [(mv, res) for res, (mv, _) in found.items()]
    if best_len == 1 and dice[0] != dice[1]:
        # Only one die can be played: it must be the larger one if possible.
        big = max(dice)
        with_big = [(mv, res) for mv, res in moves if mv[0] - (mv[1] or 0) == big
                    or (mv[1] == 0 and _uses(board, mv, big))]
        if with_big:
            moves = with_big
    return moves


def _uses(board, mv, die):
    """For a single bear-off hop, could it have been played with `die`?"""
    return _hop(board[0], board[1], mv[0], die) == 0


def move_text(board, move):
    """gnubg-style notation: '24/18* 13/9', '13/3(2)', 'bar/22 6/off'."""
    opp, me = list(board[0]), list(board[1])
    hops = []
    for frm, to in zip(move[0::2], move[1::2]):
        hops.append([frm, to, _play(opp, me, frm, to)])
    # Join hops by the same checker (a/b b/c -> a/c), keeping hit marks.
    chains = []
    for frm, to, hit in hops:
        for ch in chains:
            if ch[-1][0] == frm and frm != 0:
                ch.append((to, hit))
                break
        else:
            chains.append([(frm, False), (to, hit)])
    name = lambda p: "bar" if p == BAR else ("off" if p == 0 else str(p))
    # Intermediate points are only shown when something was hit there.
    parts = ["/".join(name(p) + ("*" if h else "") for i, (p, h) in enumerate(ch)
                      if h or i in (0, len(ch) - 1)) for ch in chains]
    order = {p: max(ch[0][0] for ch, s in zip(chains, parts) if s == p) for p in parts}
    out = []
    for p, n in sorted(Counter(parts).items(), key=lambda kv: -order[kv[0]]):
        out.append(p + (f"({n})" if n > 1 else ""))
    return " ".join(out)


# --- evaluation --------------------------------------------------------------

def equity_after(result, plies, noise=0.0):
    """Cubeful money equity for the player who just moved into `result`."""
    if sum(result[1]) == 0:
        return 1.0  # won (centered cube + Jacoby: gammons don't count)
    return -gnubg.evaluate(swap(result), money_cube(), ctx(plies, noise))[5]


def analyse(board, dice, plies=2, top=8):
    """Rank every legal move. All moves get a 0-ply score; the best `top` are
    re-scored at `plies` so the candidates are compared at the same depth.

    Returns [{move, text, equity}] best first; empty when nothing is legal."""
    moves = legal_moves(board, dice)
    scored = [(equity_after(res, 0), 0, mv) for mv, res in moves]
    scored.sort(key=lambda s: -s[0])
    if plies > 0:
        head = [(equity_after(apply_move(board, mv), plies), plies, mv) for _, _, mv in scored[:top]]
        scored = sorted(head, key=lambda s: -s[0]) + scored[top:]
    return [{"move": list(mv), "text": move_text(board, mv), "equity": eq, "ply": ply}
            for eq, ply, mv in scored]


def refine(board, analysis, i, plies):
    """Re-score analysis[i] at `plies` if it was only scored shallower, and
    re-rank. Returns the new index of that move."""
    m = analysis[i]
    if m.get("ply", plies if i < 8 else 0) < plies:
        m["equity"] = equity_after(apply_move(board, m["move"]), plies)
        m["ply"] = plies
    for j, x in enumerate(analysis):
        x.setdefault("ply", plies if j < 8 else 0)
    analysis.sort(key=lambda x: (x["ply"] != plies, -x["equity"]))
    return analysis.index(m)


def noisy_move(board, dice, noise=0.04):
    """A plausible-but-imperfect move, so self-play visits varied positions."""
    moves = legal_moves(board, dice)
    if not moves:
        return None
    return max(moves, key=lambda m: equity_after(m[1], 0) + random.gauss(0, noise))[0]


def classify(board):
    opp, me = board
    my_back = max((i for i in range(25) if me[i]), default=-1) + 1
    opp_back = max((i for i in range(25) if opp[i]), default=-1) + 1
    if my_back + opp_back <= 25:  # no contact left
        return "bearoff" if not any(me[6:]) else "race"
    if sum(me[18:]) >= 4:
        return "backgame"
    if sum(opp[18:]) >= 4:
        return "backgame-opp"
    if pips(me) > 140 and pips(opp) > 140:
        return "opening"
    return "middlegame"


def roll():
    return (random.randint(1, 6), random.randint(1, 6))
