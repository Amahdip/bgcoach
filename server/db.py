import os
import sqlite3

DB_PATH = os.environ.get("BGCOACH_DB", os.path.join(os.path.dirname(__file__), "..", "data", "bgcoach.sqlite"))

SCHEMA = """
create table if not exists positions (
    id          integer primary key,
    pid         text not null,          -- gnubg position ID, player on roll = board[1]
    dice        text not null,          -- e.g. '6-4'
    kind        text not null,          -- opening / middlegame / race / bearoff / backgame / backgame-opp
    pips_me     integer not null,
    pips_opp    integer not null,
    best_eq     real not null,
    gap         real not null,          -- equity lost by the second-best move
    analysis    text not null,          -- JSON: [{move, text, equity}] best first
    plies       integer not null,
    source      text not null default 'selfplay',
    created_at  text not null default current_timestamp,
    unique (pid, dice)
);
create index if not exists positions_kind on positions(kind);

create table if not exists attempts (
    id          integer primary key,
    user        text not null,
    position_id integer not null references positions(id) on delete cascade,
    move        text not null,          -- JSON flat tuple
    move_text   text not null,
    eq_loss     real not null,
    rank        integer not null,       -- 1 = best move
    grade       text not null,          -- again / hard / good
    was_review  integer not null,
    ms          integer,
    created_at  text not null default current_timestamp
);
create index if not exists attempts_user on attempts(user, created_at);
create index if not exists attempts_user_pos on attempts(user, position_id);

-- One card per (user, position) the user has got wrong at least once.
create table if not exists cards (
    user        text not null,
    position_id integer not null references positions(id) on delete cascade,
    due         text not null,          -- ISO-8601 UTC
    interval_d  real not null,          -- current interval in days
    ease        real not null,
    reps        integer not null,       -- consecutive successful reviews
    lapses      integer not null,
    last_review text not null,
    primary key (user, position_id)
);
create index if not exists cards_due on cards(user, due);

-- Matches the user uploaded (.mat / .sgf); their mistakes become attempts + cards.
create table if not exists imports (
    id          integer primary key,
    user        text not null,
    filename    text not null,
    sha1        text not null,
    players     text not null,          -- JSON [name0, name1]
    player      integer not null,       -- which one is the user
    length      integer not null,
    games       integer not null,
    decisions   integer not null,       -- user's checker decisions with a real choice
    mistakes    integer not null,
    total_loss  real not null,          -- summed equity loss over all decisions
    created_at  text not null default current_timestamp,
    unique (user, sha1)
);
"""

# Persian explanations written by Claude, one per (position, play compared with the best).
EXPLANATIONS = """
create table if not exists explanations (
    position_id integer not null references positions(id) on delete cascade,
    other_move  text not null,
    lang        text not null,
    text        text not null,
    model       text not null,
    created_at  text not null default current_timestamp,
    primary key (position_id, other_move, lang)
);
"""

# Columns added after the first release; applied once to existing databases.
MIGRATIONS = [
    ("attempts", "source", ["alter table attempts add column source text not null default 'train'"]),
    ("attempts", "import_id", ["alter table attempts add column import_id integer references imports(id) on delete cascade"]),
    # new = queued (e.g. from an imported match), learning = missed and on the
    # 10-minute step, review = answered right at least once since the last miss.
    ("cards", "state", ["alter table cards add column state text not null default 'review'",
                        "update cards set state = 'learning' where reps = 0"]),
    ("cards", "priority", ["alter table cards add column priority real not null default 0",  # equity lost
                           "update cards set priority = coalesce((select max(a.eq_loss) from attempts a where a.user = cards.user and a.position_id = cards.position_id), 0)"]),
    ("cards", "introduced_at", ["alter table cards add column introduced_at text",
                                "update cards set introduced_at = last_review"]),
    ("cards", "origin", ["alter table cards add column origin text"]),  # e.g. 'Alice vs Bob · game 2, move 14'
]


def connect(path=DB_PATH):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    conn.execute("pragma journal_mode = wal")
    conn.executescript(SCHEMA + EXPLANATIONS)
    for table, column, sqls in MIGRATIONS:
        if column not in {r[1] for r in conn.execute(f"pragma table_info({table})")}:
            for sql in sqls:
                conn.execute(sql)
    conn.execute("create index if not exists cards_state on cards(user, state, due)")
    conn.commit()
    return conn
