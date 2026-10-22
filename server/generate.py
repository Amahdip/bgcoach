"""Fill the positions table by letting gnubg play itself.

Each game is played with a slightly noisy 0-ply bot so it wanders into varied
positions. Every checker decision is analysed and kept only if it is a real
decision: picking the second-best move must cost at least --min-gap equity.

    python server/generate.py --positions 2000
"""
import argparse
import json
import time

import bg
import db

START = "4HPwATDgc/ABMA"


def play_game():
    """Yield (board, dice) for every decision in one self-play money game."""
    board = bg.from_id(START)
    dice = bg.roll()
    while dice[0] == dice[1]:
        dice = bg.roll()
    for _ in range(400):
        if bg.game_over(board):
            return
        move = bg.noisy_move(board, dice)
        if move:
            yield board, dice
            board = bg.apply_move(board, move)
        board = bg.swap(board)
        dice = bg.roll()


def interesting(analysis, min_gap, max_gap):
    if len(analysis) < 2:
        return None
    gap = analysis[0]["equity"] - analysis[1]["equity"]
    return gap if min_gap <= gap <= max_gap else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--positions", type=int, default=1000, help="stop after storing this many new positions")
    ap.add_argument("--plies", type=int, default=2)
    ap.add_argument("--min-gap", type=float, default=0.02)
    ap.add_argument("--max-gap", type=float, default=0.30, help="skip trivial positions with one obvious move")
    args = ap.parse_args()

    conn = db.connect()
    stored = games = seen = 0
    t0 = time.time()
    while stored < args.positions:
        games += 1
        for board, dice in play_game():
            seen += 1
            # Cheap 0-ply pre-filter before the expensive analysis.
            quick = bg.analyse(board, dice, plies=0, top=0)
            if len(quick) < 2 or quick[0]["equity"] - quick[1]["equity"] < args.min_gap / 3:
                continue
            analysis = bg.analyse(board, dice, plies=args.plies)
            gap = interesting(analysis, args.min_gap, args.max_gap)
            if gap is None:
                continue
            cur = conn.execute(
                """insert or ignore into positions
                   (pid, dice, kind, pips_me, pips_opp, best_eq, gap, analysis, plies)
                   values (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    bg.to_id(board),
                    f"{max(dice)}-{min(dice)}",
                    bg.classify(board),
                    bg.pips(board[1]),
                    bg.pips(board[0]),
                    analysis[0]["equity"],
                    gap,
                    json.dumps(analysis),
                    args.plies,
                ),
            )
            stored += cur.rowcount
            if stored >= args.positions:
                break
        conn.commit()
        if games % 10 == 0:
            print(f"{games} games, {seen} decisions, {stored} stored, {time.time() - t0:.0f}s", flush=True)
    conn.commit()
    print(f"done: {stored} new positions from {games} games in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
