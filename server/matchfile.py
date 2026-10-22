"""Read match files (.mat / .txt Jellyfish text, .sgf gnubg) and replay them.

Both formats write each player's checker moves from that player's own side
(24 -> 1), which is exactly our board convention, so a move can be replayed
on (opponent, mover) directly.

parse() returns:
    {"players": [name0, name1], "length": int,
     "games": [{"score": [a, b], "moves": [Move...]}]}
where a Move is {"player": 0|1, "dice": (d1, d2), "segs": [(frm, to, hit)]}
for a checker play (segs empty when the player could not move) — cube actions
are skipped. Points are 1..24, 25 = bar, 0 = off.
"""
import re

import bg


class MatchFileError(ValueError):
    pass


def parse(text, filename=""):
    if filename.lower().endswith(".sgf") or text.lstrip().startswith("(;"):
        return parse_sgf(text)
    return parse_mat(text)


# --- Jellyfish .mat ----------------------------------------------------------

_DICE_RE = re.compile(r"([1-6])([1-6]):")
_HEADER_RE = re.compile(r"^\s*(\S.*?)\s*:\s*(\d+)\s{2,}(\S.*?)\s*:\s*(\d+)\s*$")
_CUBE_WORDS = ("Doubles", "Takes", "Drops", "Beavers", "Raccoons", "Wins", "Resign")


def _point(tok):
    tok = tok.strip().lower()
    if tok in ("bar", "b", "25"):
        return 25
    if tok in ("off", "o", "0"):
        return 0
    n = int(tok)
    if not 0 <= n <= 25:
        raise MatchFileError(f"bad point {tok!r}")
    return n


def parse_move_text(s):
    """'24/18* 13/9', '13/7(2)', 'bar/22 6/off', '8/2*/1' -> [(frm, to, hit)]."""
    segs = []
    for part in s.split():
        m = re.fullmatch(r"([^()]+?)(?:\((\d)\))?", part)
        if not m or "/" not in m.group(1):
            raise MatchFileError(f"can't read move {part!r}")
        pts = [(_point(p.rstrip("*")), p.endswith("*")) for p in m.group(1).split("/")]
        chain = [(a[0], b[0], b[1]) for a, b in zip(pts, pts[1:])]
        segs += chain * int(m.group(2) or 1)
    return segs


def _entries(rest, offset):
    """Split the text after 'N)' into (column, kind, payload) entries."""
    out = []
    marks = [(m.start(), "move", m) for m in _DICE_RE.finditer(rest)]
    for w in _CUBE_WORDS:
        marks += [(m.start(), "cube", None) for m in re.finditer(w, rest)]
    marks.sort(key=lambda x: x[0])
    for i, (pos, kind, m) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(rest)
        if kind == "move":
            body = rest[m.end():end].strip()
            out.append((pos + offset, "move", ((int(m.group(1)), int(m.group(2))), body)))
        else:
            out.append((pos + offset, "cube", rest[pos:end].strip()))
    return out


def parse_mat(text):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    length, players, games, game = 0, None, [], None
    split = 33  # gnubg writes the left column as "%3d) %-27s "
    for line in lines:
        m = re.match(r"^\s*(\d+)\s+point match", line)
        if m:
            length = int(m.group(1))
            continue
        if re.match(r"^\s*Game\s+\d+", line):
            game = {"score": [0, 0], "moves": []}
            games.append(game)
            continue
        h = _HEADER_RE.match(line)
        if h and game is not None and not game["moves"]:
            players = players or [h.group(1), h.group(3)]
            game["score"] = [int(h.group(2)), int(h.group(4))]
            # The second name's column tells us where the right column starts.
            split = h.start(3)
            continue
        mv = re.match(r"^\s*\d+\)", line)
        if not mv or game is None:
            continue
        for col, kind, payload in _entries(line[mv.end():], mv.end()):
            if kind != "move":
                continue
            player = 1 if col >= split - 4 else 0
            dice, body = payload
            # A trailing 'Wins 1 point' etc. can share the cell; drop it.
            body = re.split(r"\s{2,}|\bWins\b", body)[0].strip()
            try:
                segs = parse_move_text(body) if body else []
            except MatchFileError as e:
                raise MatchFileError(f"game {len(games)}: {e} in line {line.strip()!r}")
            game["moves"].append({"player": player, "dice": dice, "segs": segs})
    if not games or not players:
        raise MatchFileError("no games found — is this a Jellyfish .mat / .txt match file?")
    return {"players": players, "length": length, "games": games}


# --- gnubg .sgf --------------------------------------------------------------

def _sgf_point(ch, player):
    if ch == "y":
        return 25
    if ch == "z":
        return 0
    n = ord(ch) - ord("a") if player == 0 else ord("x") - ord(ch)
    if not 0 <= n <= 23:
        raise MatchFileError(f"bad SGF point {ch!r}")
    return n + 1


def parse_sgf(text):
    games, players, length = [], ["Player 0", "Player 1"], 0
    for tree in re.findall(r"\(;(.*?)\)\s*(?=\(|$)", text, re.S):
        nodes = tree.split("\n;") if "\n;" in tree else tree.split(";")
        root = nodes[0]
        pw = re.search(r"PW\[([^\]]*)\]", root)
        pb = re.search(r"PB\[([^\]]*)\]", root)
        if pw and pb:
            players = [pw.group(1), pb.group(1)]
        mi = re.search(r"MI\[length:(\d+)\](?:\[game:\d+\])?(?:\[ws:(\d+)\])?(?:\[bs:(\d+)\])?", root)
        score = [0, 0]
        if mi:
            length = int(mi.group(1))
            score = [int(mi.group(2) or 0), int(mi.group(3) or 0)]
        game = {"score": score, "moves": []}
        for node in nodes[1:]:
            if re.search(r"\b(AE|AB|AW)\[", node):
                # Position was edited by hand; we can't replay past this point.
                break
            m = re.match(r"\s*([WB])\[(\d)(\d)([a-z]*)\]", node)
            if not m:
                continue  # cube action, comments, ...
            player = 0 if m.group(1) == "W" else 1
            pts = [_sgf_point(c, player) for c in m.group(4)]
            segs = [(pts[i], pts[i + 1], False) for i in range(0, len(pts) - 1, 2)]
            game["moves"].append({"player": player, "dice": (int(m.group(2)), int(m.group(3))), "segs": segs})
        games.append(game)
    if not games:
        raise MatchFileError("no games found in SGF file")
    return {"players": players, "length": length, "games": games}


# --- replay -----------------------------------------------------------------

START = "4HPwATDgc/ABMA"


def _resolve(board, dice, segs):
    """Find the legal move matching what the file says was played."""
    legal = bg.legal_moves(board, dice)
    if not segs:
        if legal:
            raise MatchFileError(f"no move recorded for {dice} but a move was possible")
        return None, None
    flat = tuple(x for f, t, _ in segs for x in (f, t))
    try:
        exact = bg.apply_move(board, flat)
    except IndexError:
        exact = None
    for mv, res in legal:  # SGF: every hop is spelled out, so the result is exact
        if res == exact:
            return mv, res
    # .mat may hide intermediate points ('24/14'), so match the mover's checkers
    # and use the '*' marks to tell hit-in-passing variants apart.
    me = list(board[1])
    for frm, to, _ in segs:
        me[frm - 1] -= 1
        if to:
            me[to - 1] += 1
    hits = {to for _, to, hit in segs if hit}
    cands = [(mv, res) for mv, res in legal if list(res[1]) == me]
    if not cands:
        raise MatchFileError(f"illegal move for {dice[0]}{dice[1]}: {bg.move_text(board, sum(([f, t] for f, t, _ in segs), []))}")

    def hit_points(mv):
        opp = list(board[0])
        pts = set()
        for frm, to in zip(mv[0::2], mv[1::2]):
            if to and opp[24 - to] == 1:
                pts.add(to)
                opp[24 - to] = 0
        return pts

    # Same final checkers for the mover; if several, pick the one hitting where the file says.
    for mv, res in cands:
        if not hits or hit_points(mv) == hits:
            return mv, res
    return cands[0]


def replay(match):
    """Yield (game_no, move_no, player, board, dice, played_move) for every
    checker decision. board is (opponent, mover) from the mover's view."""
    for gi, game in enumerate(match["games"], 1):
        start = bg.from_id(START)
        sides = [start[1], start[1]]  # each player's checkers, own perspective
        for mi, m in enumerate(game["moves"], 1):
            p = m["player"]
            board = (sides[1 - p], sides[p])
            try:
                mv, res = _resolve(board, m["dice"], m["segs"])
            except MatchFileError as e:
                raise MatchFileError(f"game {gi}, move {mi}: {e}")
            yield gi, mi, p, board, m["dice"], mv
            if res:
                sides[1 - p], sides[p] = res[0], res[1]
