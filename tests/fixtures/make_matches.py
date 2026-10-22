"""Regenerate the match fixtures: three self-play games written as gnubg .mat,
XG-style .mat and gnubg .sgf (layouts follow gnubg 1.08 export.c / sgf.c), plus
truth.json with the moves actually played, which the tests replay against.

    python tests/fixtures/make_matches.py server tests/fixtures
"""
import json, random, sys
sys.path.insert(0, sys.argv[1])
import bg

out = sys.argv[2]
random.seed(7)


def play_game():
    b = bg.from_id("4HPwATDgc/ABMA")
    sides = [b[1], b[1]]
    p = random.randint(0, 1)
    d = bg.roll()
    while d[0] == d[1]:
        d = bg.roll()
    moves = []
    while True:
        board = (sides[1 - p], sides[p])
        mv = bg.noisy_move(board, d)
        moves.append((p, d, mv, board))
        if mv:
            o, me = bg.apply_move(board, mv)
            sides[1 - p], sides[p] = o, me
            if sum(me) == 0:
                return moves, p
        p = 1 - p
        d = bg.roll()


def plain(board, mv, style):
    t = bg.move_text(board, mv) if mv else ""
    if style == "gnubg":  # FormatMovePlain uses numbers for bar/off
        t = t.replace("bar", "25").replace("off", "0")
    return t


games = [play_game() for _ in range(3)]
truth = [[[p, list(d), list(mv) if mv else None] for p, d, mv, _ in g] for g, _ in games]
json.dump(truth, open(f"{out}/truth.json", "w"))

for style in ("gnubg", "xg"):
    lines = [" 5 point match", ""]
    score = [0, 0]
    for gi, (moves, winner) in enumerate(games):
        lines.append(f" Game {gi + 1}")
        sz = f"Alice : {score[0]}"
        lines.append(f" {sz:<31}Bob : {score[1]}")
        i = 0
        cur = ""
        for p, d, mv, board in moves:
            cell = f"{d[0]}{d[1]}: {plain(board, mv, style)}"
            if i == 0 and p == 1:
                cur = "  1)                             "
                i = 1
            if i % 2 == 0:
                cur = f"{i // 2 + 1:3d}) {cell:<27} "
            else:
                lines.append(cur + cell)
                cur = ""
            i += 1
        if cur:
            lines.append(cur.rstrip())
        lines.append(("                                  " if i % 2 == 0 else "      ") + "Wins 1 point")
        lines.append("")
        score[winner] += 1
    open(f"{out}/match_{style}.mat", "w").write("\n".join(lines) + "\n")

sgf = []
score = [0, 0]
for gi, (moves, winner) in enumerate(games):
    s = f"(;FF[4]GM[6]CA[UTF-8]AP[GNU Backgammon:1.08.003]MI[length:5][game:{gi}][ws:{score[0]}][bs:{score[1]}]PW[Alice]PB[Bob]RU[Crawford]RE[{'B' if winner else 'W'}+1]"
    for p, d, mv, board in moves:
        s += f"\n;{'B' if p else 'W'}[{d[0]}{d[1]}"
        for k, x in enumerate(mv or []):
            if x == 25:
                s += "y"
            elif x == 0:
                s += "z"
            else:
                n = x - 1
                s += chr(ord("x") - n) if p else chr(ord("a") + n)
        s += "]A[0][1]"  # stand-in for analysis properties
    sgf.append(s + ")\n")
    score[winner] += 1
open(f"{out}/match.sgf", "w").write("".join(sgf))
print("games", [len(g) for g, _ in games])
