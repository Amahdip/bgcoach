"""Turn the user's own matches into review cards.

Every checker decision of the chosen player is analysed like a generated
position. Decisions that lost at least `min_error` equity are stored as an
attempt (source 'import') plus a queued card ('new' state), so they are fed into
training a few per day, biggest error first.

    python server/importer.py match.mat --player Alice
"""
import argparse
import hashlib
import json

import bg
import db
import matchfile
import srs

MIN_ERROR = 0.02


class AlreadyImported(Exception):
    def __init__(self, import_id):
        super().__init__(f"this file was already imported (import #{import_id})")
        self.import_id = import_id


def preview(text, filename):
    """Parse and fully replay the file, so problems show up before analysing."""
    match = matchfile.parse(text, filename)
    decisions = [0, 0]
    for _, _, p, board, dice, mv in matchfile.replay(match):
        if mv and len(bg.legal_moves(board, dice)) > 1:
            decisions[p] += 1
    return {
        "players": match["players"],
        "length": match["length"],
        "games": len(match["games"]),
        "decisions": decisions,
    }


def _position_id(conn, board, dice, analysis, plies):
    pid = bg.to_id(board)
    dice_s = f"{max(dice)}-{min(dice)}"
    conn.execute(
        """insert or ignore into positions
           (pid, dice, kind, pips_me, pips_opp, best_eq, gap, analysis, plies, source)
           values (?, ?, ?, ?, ?, ?, ?, ?, ?, 'import')""",
        (pid, dice_s, bg.classify(board), bg.pips(board[1]), bg.pips(board[0]),
         analysis[0]["equity"], analysis[0]["equity"] - analysis[1]["equity"],
         json.dumps(analysis), plies),
    )
    return conn.execute("select id from positions where pid = ? and dice = ?", (pid, dice_s)).fetchone()[0]


def import_match(conn, user, text, filename, player, min_error=MIN_ERROR, plies=2):
    match = matchfile.parse(text, filename)
    sha = hashlib.sha1(text.encode()).hexdigest()
    prev = conn.execute("select id from imports where user = ? and sha1 = ?", (user, sha)).fetchone()
    if prev:
        raise AlreadyImported(prev[0])
    names = match["players"]
    title = f"{names[0]} vs {names[1]}"
    import_id = conn.execute(
        """insert into imports (user, filename, sha1, players, player, length, games, decisions, mistakes, total_loss)
           values (?, ?, ?, ?, ?, ?, ?, 0, 0, 0)""",
        (user, filename, sha, json.dumps(names), player, match["length"], len(match["games"])),
    ).lastrowid

    decisions = 0
    total_loss = 0.0
    mistakes = []
    now = srs.iso(srs.now())
    turn = {}  # game -> the user's move number in it
    for gi, mi, p, board, dice, mv in matchfile.replay(match):
        if p != player:
            continue
        turn[gi] = turn.get(gi, 0) + 1
        if mv is None:
            continue
        analysis = bg.analyse(board, dice, plies)
        if len(analysis) < 2:
            continue  # forced move
        decisions += 1
        played = bg.apply_move(board, mv)
        idx = next(i for i, m in enumerate(analysis) if bg.apply_move(board, m["move"]) == played)
        idx = bg.refine(board, analysis, idx, plies)
        loss = max(0.0, analysis[0]["equity"] - analysis[idx]["equity"])
        total_loss += loss
        if loss < min_error:
            continue

        pos_id = _position_id(conn, board, dice, analysis, plies)
        conn.execute(
            """insert into attempts (user, position_id, move, move_text, eq_loss, rank, grade, was_review,
                                     source, import_id)
               values (?, ?, ?, ?, ?, ?, 'again', 0, 'import', ?)""",
            (user, pos_id, json.dumps(analysis[idx]["move"]), analysis[idx]["text"], loss, idx + 1, import_id),
        )
        origin = f"{title} · game {gi}, move {turn[gi]}"
        conn.execute(
            """insert into cards (user, position_id, due, interval_d, ease, reps, lapses, last_review,
                                  state, priority, origin)
               values (?, ?, ?, 0, 2.5, 0, 1, ?, 'new', ?, ?)
               on conflict(user, position_id) do update set
                 priority = max(cards.priority, excluded.priority),
                 origin = coalesce(cards.origin, excluded.origin)""",
            (user, pos_id, now, now, loss, origin),
        )
        mistakes.append({
            "position_id": pos_id, "game": gi, "move": turn[gi], "dice": f"{dice[0]}{dice[1]}",
            "played": analysis[idx]["text"], "best": analysis[0]["text"], "loss": loss,
            "kind": bg.classify(board),
        })

    conn.execute(
        "update imports set decisions = ?, mistakes = ?, total_loss = ? where id = ?",
        (decisions, len(mistakes), total_loss, import_id),
    )
    conn.commit()
    return {
        "import_id": import_id,
        "players": names,
        "player": player,
        "games": len(match["games"]),
        "decisions": decisions,
        "error_rate": 1000 * total_loss / decisions if decisions else 0,
        "mistakes": sorted(mistakes, key=lambda m: -m["loss"]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--player", required=True, help="your name as written in the file")
    ap.add_argument("--user", default="me")
    ap.add_argument("--min-error", type=float, default=MIN_ERROR)
    args = ap.parse_args()
    text = open(args.file, encoding="utf-8", errors="replace").read()
    info = preview(text, args.file)
    if args.player not in info["players"]:
        ap.error(f"player must be one of {info['players']}")
    res = import_match(db.connect(), args.user, text, args.file, info["players"].index(args.player),
                       args.min_error)
    print(f"{res['decisions']} decisions, {len(res['mistakes'])} mistakes, error rate {res['error_rate']:.1f}")
    for m in res["mistakes"][:10]:
        print(f"  game {m['game']} move {m['move']} {m['dice']}: played {m['played']}, best {m['best']} (-{m['loss']:.3f})")


if __name__ == "__main__":
    main()
