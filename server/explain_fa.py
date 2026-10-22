"""Persian explanation built from the facts with fixed sentence templates.

No AI involved: each measurable difference between the two plays becomes a
sentence with an importance score, and the most important ones are kept. Used
when the Claude API isn't available (no API key).
"""


def _pct(x):
    return f"{round(x * 100)}٪"


def _points(ps):
    return "، ".join(str(p) for p in ps)


def _rolls(n):
    return "هیچ تاسی" if n == 0 else f"{n} تاس از ۳۶ تا"


def _severity(loss):
    if loss < 0.04:
        return "کمی ضعیف‌تر از"
    if loss < 0.08:
        return "به‌طور محسوسی ضعیف‌تر از"
    return "اشتباه بزرگی (blunder) در مقایسه با"


def write(f):
    b, o = f["best"], f["other"]
    B, O = b["move"], o["move"]
    found = f["user_found_best"]

    if found:
        intro = f"آفرین، بهترین حرکت را پیدا کردید: {B}. گزینهٔ دوم {O} بود."
    else:
        intro = f"حرکت شما {O} {_severity(o['equity_lost'])} بهترین حرکت {B} است."

    reasons = []  # (score, sentence)
    concessions = []  # where the weaker play looks better on one count

    # Hitting
    if b["hits"] > o["hits"]:
        n = b["hits"]
        reasons.append((0.6 + 0.2 * n, f"{B} {'یک' if n == 1 else n} مهرهٔ حریف را می‌زند و به بار می‌فرستد"
                                       + (f"، در حالی که {O} نمی‌زند." if o["hits"] == 0 else f"، بیشتر از {O}.")))
    elif o["hits"] > b["hits"]:
        concessions.append(f"{O} مهرهٔ حریف را می‌زند")

    # Exposure
    ds = o["shots_to_hit_you"] - b["shots_to_hit_you"]
    if ds >= 4:
        reasons.append((ds / 36 + 0.2, f"با {O} حریف با {_rolls(o['shots_to_hit_you'])} می‌تواند مهرهٔ تنهای شما را بزند، "
                                       f"در حالی که با {B} {_rolls(b['shots_to_hit_you'])}."))
    elif ds <= -4:
        concessions.append(f"{O} مهرهٔ تنها را کمتر در معرض زدن می‌گذارد ({_rolls(o['shots_to_hit_you'])} در برابر {b['shots_to_hit_you']} تاس)")

    # Points made / given up
    new_b = [p for p in b["points_made"] if p not in o["points_made"]]
    if new_b:
        home = [p for p in new_b if p <= 6]
        reasons.append((0.35 + 0.1 * len(home), f"{B} خانهٔ {_points(new_b)} را می‌بندد"
                                                 + (" که خانهٔ خودی شما را محکم‌تر می‌کند." if home else ".")))
    lost_o = [p for p in o["points_given_up"] if p not in b["points_given_up"]]
    if lost_o:
        reasons.append((0.3, f"{O} خانهٔ {_points(lost_o)} را که بسته بود باز می‌کند."))
    dh = b["home_board_points"] - o["home_board_points"]
    if dh >= 1 and not any(p <= 6 for p in new_b):
        reasons.append((0.2 + 0.1 * dh, f"با {B} در خانهٔ خودی {b['home_board_points']} خانهٔ بسته دارید، در برابر {o['home_board_points']}."))

    # Prime
    bp, op = b["longest_prime"], o["longest_prime"]
    bl, ol = (bp or {}).get("length", 0), (op or {}).get("length", 0)
    if bl >= 3 and bl > ol:
        reasons.append((0.15 * (bl - ol) + 0.1, f"{B} یک دیوار (prime) {bl} خانه‌ای از {bp['from']} تا {bp['to']} می‌سازد"
                                                 + (f" که با {O} فقط {ol} خانه است." if ol >= 2 else ".")))

    # Anchors
    anc = [p for p in b["anchors_in_opponent_home"] if p not in o["anchors_in_opponent_home"]]
    if anc:
        reasons.append((0.3, f"{B} لنگر (anchor) روی خانهٔ {_points(anc)} در خانهٔ حریف نگه می‌دارد که جای امنی برای مهره‌های عقب است."))

    # Race / bear-off
    if b["checkers_off"] > o["checkers_off"]:
        reasons.append((0.4, f"{B} {b['checkers_off'] - o['checkers_off']} مهرهٔ بیشتر بیرون می‌برد."))
    if b["back_checkers"] < o["back_checkers"] and f["position"] in ("race", "middlegame", "backgame"):
        reasons.append((0.15, f"{B} مهره‌های عقب را بیشتر جلو می‌آورد ({b['back_checkers']} مهره در برابر {o['back_checkers']})."))

    # Gammons
    dwg = b["win_gammon"] - o["win_gammon"]
    dlg = o["lose_gammon"] - b["lose_gammon"]
    if dwg >= 0.03:
        reasons.append((dwg * 4, f"شانس گمون بردن با {B} {_pct(b['win_gammon'])} است، در برابر {_pct(o['win_gammon'])}."))
    if dlg >= 0.03:
        reasons.append((dlg * 4, f"خطر گمون باختن با {O} به {_pct(o['lose_gammon'])} می‌رسد، ولی با {B} {_pct(b['lose_gammon'])} است."))

    reasons.sort(key=lambda r: -r[0])
    body = [s for _, s in reasons[:3]]
    if concessions and body:
        body[0] = f"هرچند {concessions[0]}، ولی " + body[0]
    if not body:
        body = [f"تفاوت این دو حرکت در آماری که این برنامه می‌شمارد دیده نمی‌شود و بیشتر به جزئیات موقعیت برمی‌گردد؛ "
                f"موتور gnubg حرکت {B} را {o['equity_lost']:.3f} بهتر ارزیابی می‌کند."]

    dw = b["win"] - o["win"]
    if abs(dw) >= 0.01:
        ending = f"در کل شانس برد با {B} {_pct(b['win'])} و با {O} {_pct(o['win'])} است."
    else:
        ending = (f"شانس برد با هر دو حرکت حدود {_pct(b['win'])} است، پس تفاوت اصلی در گمون‌هاست."
                  if (dwg >= 0.03 or dlg >= 0.03) else "")
    return " ".join([intro, *body, ending]).strip()
