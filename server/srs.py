"""Spaced repetition for missed positions (SM-2 flavoured).

A position becomes a card the first time the user's play loses 0.02 equity or
more. How hard it comes back depends on how bad the play was (the gnubg / XG
thresholds):

    doubtful  0.02-0.04   back in 3 days, ease -0.1
    error     0.04-0.08   back tomorrow, ease -0.2
    blunder   >= 0.08     back tomorrow, ease -0.3, and it takes two right
                          answers in a row before the interval starts growing

A right answer then gives 3 days, 7 days, and the interval times the ease
after that. Nothing comes back the same day: a few minutes later the answer is
still in short-term memory, so replaying it only tests recognition.

Order of play (see app.next_position): due missed cards, then due
reviews (biggest error first, capped per day), then queued cards (capped per
day), then fresh positions.
"""
from datetime import datetime, timedelta, timezone

RELEARN = timedelta(days=1)
DOUBTFUL_RELEARN = timedelta(days=3)
SLOW_MS = 30_000  # a correct answer slower than this counts as "hard"
MIN_EASE = 1.3
LEARNED_DAYS = 21  # interval at which a card counts as learned

# Daily caps so a big backlog (say 1000 mistakes) never takes over a session:
# past the caps you just get fresh positions, and the rest waits for tomorrow.
MAX_REVIEWS_PER_DAY = 100
NEW_PER_DAY = 20  # queued cards (from imported matches) introduced per day


def now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.isoformat(timespec="seconds")


# Equity-loss thresholds, as in gnubg / eXtreme Gammon.
DOUBTFUL, ERROR, BLUNDER = 0.02, 0.04, 0.08
SEVERITIES = ("doubtful", "error", "blunder")
MISSES = SEVERITIES  # grades that count as a miss
EASE_DROP = {"doubtful": 0.1, "error": 0.2, "blunder": 0.3}


def severity(eq_loss):
    """None for the best play or one within 0.02 of it, else doubtful / error / blunder."""
    if eq_loss < DOUBTFUL:
        return None
    if eq_loss < ERROR:
        return "doubtful"
    if eq_loss < BLUNDER:
        return "error"
    return "blunder"


def grade(rank, ms, eq_loss=None):
    """good / hard for a right answer, or the severity of the miss.

    A play within 0.02 of the best counts as right (but "hard"): the engine
    can't really tell those apart at 2-ply."""
    if rank != 1:
        sev = severity(eq_loss) if eq_loss is not None else "error"
        if sev:
            return sev
        return "hard"
    if ms is not None and ms > SLOW_MS:
        return "hard"
    return "good"



def severity_sql(col):
    """SQL counterpart of severity() for an equity-loss column."""
    return (f"case when {col} < {DOUBTFUL} then null when {col} < {ERROR} then 'doubtful' "
            f"when {col} < {BLUNDER} then 'error' else 'blunder' end")


def severity_counts_sql(col, rank="rank"):
    """SQL columns doubtful, errors, blunders counting the misses in a group."""
    miss = f"{rank} > 1 and {col}"
    return (f"coalesce(sum({miss} >= {DOUBTFUL} and {col} < {ERROR}), 0) doubtful, "
            f"coalesce(sum({miss} >= {ERROR} and {col} < {BLUNDER}), 0) errors, "
            f"coalesce(sum({miss} >= {BLUNDER}), 0) blunders")


def schedule(card, g, t=None):
    """Return the updated card fields after a review with grade `g`.

    `card` is a dict with interval_d, ease, reps, lapses, or None for a
    position the user has never missed (returns None if no card is needed).
    `reps` is negative after a blunder: right answers count up to 0 one day
    apart before the normal 3 / 7 / x ease intervals start."""
    t = t or now()
    if g == "again":  # older callers: an unspecified miss
        g = "error"
    if card is None:
        if g not in MISSES:
            return None
        card = {"interval_d": 0.0, "ease": 2.5, "reps": 0, "lapses": 0}
    c = dict(card)
    if g in MISSES:
        c.update(interval_d=0.0, reps=-1 if g == "blunder" else 0, lapses=c["lapses"] + 1,
                 ease=max(MIN_EASE, c["ease"] - EASE_DROP[g]))
        due = t + (DOUBTFUL_RELEARN if g == "doubtful" else RELEARN)
    elif c["reps"] < 0:
        # Still proving a blunder: another day, and one step closer to normal.
        c.update(interval_d=1.0, reps=c["reps"] + 1)
        due = t + RELEARN
    else:
        if c["reps"] == 0:
            ivl = 3.0 if g == "good" else 2.0
        elif c["reps"] == 1:
            ivl = 7.0 if g == "good" else 4.0
        else:
            ivl = c["interval_d"] * (c["ease"] if g == "good" else 1.2)
        if g == "hard":
            c["ease"] = max(MIN_EASE, c["ease"] - 0.15)
        c.update(interval_d=ivl, reps=c["reps"] + 1)
        due = t + timedelta(days=ivl)
    state = "learning" if g in MISSES or c["reps"] <= 0 else "review"
    c.update(due=iso(due), last_review=iso(t), state=state)
    return c
