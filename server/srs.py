"""Spaced repetition for missed positions (SM-2 flavoured).

A position becomes a card the first time the user does not play the best move.
After that it comes back on a schedule: missed -> tomorrow, right -> 3 days,
7 days, then the interval grows by the card's ease factor. Nothing comes back
the same day: a few minutes later the answer is still in short-term memory, so
replaying it only tests recognition.

Order of play (see app.next_position): due missed cards, then due
reviews (biggest error first, capped per day), then queued cards (capped per
day), then fresh positions.
"""
from datetime import datetime, timedelta, timezone

RELEARN = timedelta(days=1)
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


def grade(rank, ms):
    if rank != 1:
        return "again"
    if ms is not None and ms > SLOW_MS:
        return "hard"
    return "good"


def schedule(card, g, t=None):
    """Return the updated card fields after a review with grade `g`.

    `card` is a dict with interval_d, ease, reps, lapses, or None for a
    position the user has never missed (returns None if no card is needed)."""
    t = t or now()
    if card is None:
        if g != "again":
            return None
        card = {"interval_d": 0.0, "ease": 2.5, "reps": 0, "lapses": 0}
    c = dict(card)
    if g == "again":
        c.update(interval_d=0.0, reps=0, lapses=c["lapses"] + 1, ease=max(MIN_EASE, c["ease"] - 0.2))
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
    c.update(due=iso(due), last_review=iso(t), state="learning" if g == "again" else "review")
    return c
