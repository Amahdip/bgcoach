"""Measurable facts about a checker play, for explaining it.

Everything here is computed from the board and gnubg, so an explanation built
on these numbers can't invent anything. Points are from the mover's side
(1..24, 25 = bar).
"""
import gnubg

import bg

ROLLS = [((a, b), 1 if a == b else 2) for a in range(1, 7) for b in range(a, 7)]  # 21 rolls, weight out of 36


def made_points(side):
    return [i + 1 for i in range(24) if side[i] >= 2]


def longest_prime(side):
    """(length, from_point, to_point) of the longest run of made points."""
    best, run, start = (0, 0, 0), 0, 0
    for p in range(1, 25):
        if side[p - 1] >= 2:
            if run == 0:
                start = p
            run += 1
            if run > best[0]:
                best = (run, start, p)
        else:
            run = 0
    return best


def shots(result):
    """How many of the opponent's 36 rolls hit at least one of the mover's
    blots, counting only plays the opponent can legally make."""
    opp_view = bg.swap(result)  # opponent on roll; the mover is now board[0]
    if not any(result[1][i] == 1 for i in range(24)):
        return 0
    bar_before = opp_view[0][24]
    total = 0
    for roll, weight in ROLLS:
        if any(res[0][24] > bar_before for _, res in bg.legal_moves(opp_view, roll)):
            total += weight
    return total


def probabilities(result, plies=2):
    """Cubeless chances for the mover after the play, from gnubg."""
    if sum(result[1]) == 0:
        return {"win": 1.0, "win_gammon": 0.0, "lose_gammon": 0.0}
    p = gnubg.evaluate(bg.swap(result), bg.money_cube(), bg.ctx(plies))
    # p is from the opponent's side: (win, win_g, win_bg, lose_g, lose_bg, equity)
    return {"win": 1 - p[0], "win_gammon": p[3], "lose_gammon": p[1]}


def play_facts(board, move, plies=2):
    result = bg.apply_move(board, move)
    opp, me = result
    before_me = board[1]
    made_before, made_after = set(made_points(before_me)), set(made_points(me))
    prime = longest_prime(me)
    return {
        "move": bg.move_text(board, move),
        "hits": opp[24] - board[0][24],
        "blots": [p for p in range(1, 25) if me[p - 1] == 1],
        "shots_to_hit_you": shots(result),
        "points_made": sorted(made_after - made_before),
        "points_given_up": sorted(made_before - made_after),
        "home_board_points": sum(1 for p in range(1, 7) if me[p - 1] >= 2),
        "longest_prime": {"length": prime[0], "from": prime[2], "to": prime[1]} if prime[0] >= 2 else None,
        "anchors_in_opponent_home": [p for p in range(19, 25) if me[p - 1] >= 2],
        "back_checkers": sum(me[18:25]),
        "checkers_off": 15 - sum(me),
        "opponent_on_bar": opp[24],
        "your_pips": bg.pips(me),
        "opponent_pips": bg.pips(opp),
        **{k: round(v, 3) for k, v in probabilities(result, plies).items()},
    }


def compare(board, dice, analysis, chosen_index, plies=2):
    """Facts for the best play and the play to compare it with: the user's
    play, or the runner-up when the user found the best one."""
    other = chosen_index if chosen_index > 0 else 1
    best, alt = analysis[0], analysis[other]
    return {
        "dice": f"{dice[0]}-{dice[1]}",
        "position": bg.classify(board),
        "before": {
            "your_pips": bg.pips(board[1]),
            "opponent_pips": bg.pips(board[0]),
            "you_on_bar": board[1][24],
            "opponent_on_bar": board[0][24],
        },
        "user_found_best": chosen_index == 0,
        "best": {**play_facts(board, best["move"], plies), "equity": round(best["equity"], 3)},
        "other": {**play_facts(board, alt["move"], plies), "equity": round(alt["equity"], 3),
                  "rank": other + 1, "equity_lost": round(best["equity"] - alt["equity"], 3)},
    }
