"use strict";

// Board arrays follow gnubg: index i = point i+1 from that side's view, 24 = bar.
// "me" is always the player on roll, shown at the bottom, home board bottom-right.
const BAR = 25;
const $ = (s) => document.querySelector(s);
const fmt = (x, d = 3) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(d);
const store = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch {} },
};

async function api(path, body) {
  const res = await fetch(path, body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : {});
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText);
  return res.json();
}

// ---------- rules (mirror of server/bg.py, used only to guide input) ----------

function hop(me, opp, frm, die) {
  if (me[frm - 1] === 0 || (me[24] && frm !== BAR)) return null;
  const to = frm - die;
  if (to >= 1) return opp[24 - to] < 2 ? to : null;
  if (me.slice(6, 25).some(Boolean)) return null;
  if (to === 0 || !me.slice(frm, 24).some(Boolean)) return 0;
  return null;
}

function play(me, opp, frm, to) {
  me = me.slice(); opp = opp.slice();
  me[frm - 1]--;
  let hit = false;
  if (to) {
    me[to - 1]++;
    if (opp[24 - to] === 1) { opp[24 - to] = 0; opp[24]++; hit = true; }
  }
  return { me, opp, hit };
}

const key = (me, opp) => me.join(",") + "|" + opp.join(",");
const without = (dice, d) => { const i = dice.indexOf(d); return dice.slice(0, i).concat(dice.slice(i + 1)); };
const uniq = (a) => [...new Set(a)];

// Can this partial play still be finished into one of the server's legal moves?
function completable(me, opp, dice) {
  let moved = false;
  for (const d of uniq(dice)) {
    for (let f = BAR; f >= 1; f--) {
      const to = hop(me, opp, f, d);
      if (to === null) continue;
      moved = true;
      const n = play(me, opp, f, to);
      if (completable(n.me, n.opp, without(dice, d))) return true;
    }
  }
  return !moved && S.legal.has(key(me, opp));
}

// ---------- state ----------

const S = {
  pos: null, me: [], opp: [], dice: [], legal: new Set(), hist: [],
  t0: 0, result: null, preview: null, busy: false,
};

function canPlayMore() {
  for (const d of uniq(S.dice)) for (let f = BAR; f >= 1; f--) if (hop(S.me, S.opp, f, d) !== null) return true;
  return false;
}
const isComplete = () => S.legal.has(key(S.me, S.opp));

// ---------- board drawing ----------

const G = { L: 24, W: 56, BARW: 48, TOP: 24, BOT: 572, H: 220, R: 22, TRAY: 756 };
G.RIGHT = G.L + 6 * G.W + G.BARW;
G.MID = (G.TOP + G.BOT) / 2;
G.BARX = G.L + 6 * G.W + G.BARW / 2;

function colX(p) { // left edge of the column for my point p (1..24)
  if (p <= 6) return G.RIGHT + (6 - p) * G.W;
  if (p <= 12) return G.L + (12 - p) * G.W;
  if (p <= 18) return G.L + (p - 13) * G.W;
  return G.RIGHT + (p - 19) * G.W;
}
const isTop = (p) => p >= 13;

function checker(cx, cy, mine, label, extra = "") {
  const fill = mine ? "var(--chk-me)" : "var(--chk-opp)";
  const edge = mine ? "var(--chk-me-edge)" : "var(--chk-opp-edge)";
  let s = `<g ${extra}><circle cx="${cx}" cy="${cy}" r="${G.R}" style="fill:${fill};stroke:${edge};stroke-width:1.5"/>` +
    `<circle cx="${cx}" cy="${cy}" r="${G.R - 6}" style="fill:none;stroke:${edge};stroke-opacity:.35"/>`;
  if (label) s += `<text x="${cx}" y="${cy + 5}" text-anchor="middle" style="font:700 15px ui-sans-serif,sans-serif;fill:${mine ? "#222" : "#eee"}">${label}</text>`;
  return s + "</g>";
}

function stack(p, n, mine, sel) {
  const x = colX(p) + G.W / 2;
  let s = "";
  for (let i = 0; i < Math.min(n, 5); i++) {
    const y = isTop(p) ? G.TOP + G.R + i * 2 * G.R : G.BOT - G.R - i * 2 * G.R;
    const isLast = i === Math.min(n, 5) - 1;
    s += checker(x, y, mine, isLast && n > 5 ? n : "",
      sel && isLast ? `style="filter:drop-shadow(0 0 6px var(--hl))"` : "");
    if (sel && isLast) s += `<circle cx="${x}" cy="${y}" r="${G.R + 2}" style="fill:none;stroke:var(--hl);stroke-width:3"/>`;
  }
  return s;
}

// After answering: dashed ghosts where checkers left from, rings where they arrived.
function moveMarks(before, after) {
  let s = "";
  for (let p = 1; p <= 24; p++) {
    const d = after[p - 1] - before[p - 1];
    const x = colX(p) + G.W / 2;
    const slot = (i) => (isTop(p) ? G.TOP + G.R + i * 2 * G.R : G.BOT - G.R - i * 2 * G.R);
    if (d < 0) {
      for (let k = 0; k < -d; k++) {
        const i = Math.min(after[p - 1] + k, 4);
        s += `<circle cx="${x}" cy="${slot(i)}" r="${G.R - 2}" style="fill:none;stroke:var(--hl);stroke-width:2;stroke-dasharray:5 4;opacity:.9"/>`;
      }
    } else if (d > 0) {
      for (let k = 0; k < d; k++) {
        const i = Math.min(after[p - 1] - 1 - k, 4);
        s += `<circle cx="${x}" cy="${slot(i)}" r="${G.R + 1}" style="fill:none;stroke:var(--hl);stroke-width:3"/>`;
      }
    }
  }
  return s;
}

function die(x, y, v, faded) {
  const pip = { 1: [[0, 0]], 2: [[-1, -1], [1, 1]], 3: [[-1, -1], [0, 0], [1, 1]], 4: [[-1, -1], [1, -1], [-1, 1], [1, 1]],
    5: [[-1, -1], [1, -1], [0, 0], [-1, 1], [1, 1]], 6: [[-1, -1], [1, -1], [-1, 0], [1, 0], [-1, 1], [1, 1]] }[v];
  let s = `<g opacity="${faded ? 0.3 : 1}"><rect x="${x - 20}" y="${y - 20}" width="40" height="40" rx="8" style="fill:#fbfaf6;stroke:#00000033"/>`;
  for (const [a, b] of pip) s += `<circle cx="${x + a * 10}" cy="${y + b * 10}" r="3.6" fill="#222"/>`;
  return s + "</g>";
}

function drawBoard() {
  const view = S.preview || { me: S.me, opp: S.opp };
  const { me, opp } = view;
  const interactive = !S.result;
  let s = `<rect x="0" y="0" width="828" height="596" rx="14" style="fill:var(--frame)"/>` +
    `<rect x="${G.L}" y="${G.TOP}" width="${12 * G.W + G.BARW}" height="${G.BOT - G.TOP}" style="fill:var(--felt)"/>` +
    `<rect x="${G.TRAY}" y="${G.TOP}" width="48" height="${G.BOT - G.TOP}" rx="4" style="fill:var(--felt);opacity:.75"/>` +
    `<rect x="${G.L + 6 * G.W}" y="${G.TOP}" width="${G.BARW}" height="${G.BOT - G.TOP}" style="fill:var(--frame)"/>`;

  for (let p = 1; p <= 24; p++) {
    const x = colX(p), top = isTop(p);
    const base = top ? G.TOP : G.BOT, tip = top ? G.TOP + G.H : G.BOT - G.H;
    s += `<polygon points="${x + 2},${base} ${x + G.W - 2},${base} ${x + G.W / 2},${tip}" style="fill:${p % 2 ? "var(--pt-b)" : "var(--pt-a)"}"/>`;
    s += `<text x="${x + G.W / 2}" y="${top ? 16 : 588}" text-anchor="middle" style="font:600 11px ui-sans-serif,sans-serif;fill:var(--num)">${p}</text>`;
  }

  // checkers on points
  for (let p = 1; p <= 24; p++) {
    if (me[p - 1]) s += stack(p, me[p - 1], true, false);
    const o = opp[24 - p];
    if (o) s += stack(p, o, false, false);
  }
  if (S.result && view.me !== S.pos.board.me) s += moveMarks(S.pos.board.me, me);
  // bar: mine below the middle, opponent's above
  for (let i = 0; i < me[24]; i++) {
    const y = G.MID + 40 + i * 2 * G.R;
    s += checker(G.BARX, y, true, "");
  }
  for (let i = 0; i < opp[24]; i++) s += checker(G.BARX, G.MID - 40 - i * 2 * G.R, false, "");

  // borne off
  const offMe = 15 - me.reduce((a, b) => a + b, 0), offOpp = 15 - opp.reduce((a, b) => a + b, 0);
  for (let i = 0; i < offMe; i++) s += `<rect x="${G.TRAY + 6}" y="${G.BOT - 8 - i * 11}" width="36" height="9" rx="2" style="fill:var(--chk-me);stroke:var(--chk-me-edge)"/>`;
  for (let i = 0; i < offOpp; i++) s += `<rect x="${G.TRAY + 6}" y="${G.TOP + 2 + i * 11}" width="36" height="9" rx="2" style="fill:var(--chk-opp);stroke:#000"/>`;

  // dice (right half, my side): unused dice first, in play order (a click uses
  // the leftmost), then the used ones faded.
  if (S.pos) {
    const [a, b] = S.pos.dice;
    let used = a === b ? [a, a, a, a] : [a, b];
    for (const d of S.dice) used = without(used, d);
    const shown = S.result ? (a === b ? [a, a, a, a] : [a, b]) : S.dice.concat(used);
    const cx = G.RIGHT + 3 * G.W, n = shown.length;
    shown.forEach((v, i) => {
      const x = cx + (i - (n - 1) / 2) * 48;
      s += die(x, G.MID, v, !S.result && i >= S.dice.length);
      if (!S.result && i === 0 && uniq(S.dice).length > 1)
        s += `<rect x="${x - 23}" y="${G.MID - 23}" width="46" height="46" rx="10" style="fill:none;stroke:var(--hl);stroke-width:2"/>`;
    });
  }

  // click targets
  if (interactive) {
    for (let p = 1; p <= 24; p++) {
      s += `<rect class="hit" data-p="${p}" x="${colX(p)}" y="${isTop(p) ? G.TOP : G.MID}" width="${G.W}" height="${G.BOT - G.MID}"/>`;
    }
    s += `<rect class="hit" data-p="${BAR}" x="${G.L + 6 * G.W}" y="${G.TOP}" width="${G.BARW}" height="${G.BOT - G.TOP}"/>`;
    s += `<rect class="hit" data-p="0" x="${G.TRAY}" y="${G.TOP}" width="48" height="${G.BOT - G.TOP}"/>`;
  }
  // The dice: swap their order while moving, flip to the starting position after answering.
  if (S.pos && (S.result || uniq(S.dice).length > 1)) {
    const n = S.pos.dice[0] === S.pos.dice[1] ? 4 : 2, w = (n - 1) * 48 + 48;
    const tip = S.result ? "Click to flip between the start and the shown play" : "Click to swap which die is played first";
    s += `<rect class="hit dice-hit" x="${G.RIGHT + 3 * G.W - w / 2}" y="${G.MID - 26}" width="${w}" height="52" rx="10"><title>${tip}</title></rect>`;
  }
  $("#board").innerHTML = s;
}

// ---------- train view ----------

function setHint(msg, err) { const h = $("#hint"); h.textContent = msg; h.classList.toggle("err", !!err); }

function refreshControls() {
  const done = isComplete();
  $("#submit").disabled = !done || !!S.result || S.busy;
  $("#undo").disabled = !S.hist.length || !!S.result;
  $("#submit").hidden = !!S.result;
  $("#next").hidden = !S.result;
  $("#start").hidden = !S.result;
  if (S.result) return;
  if (done) setHint(canPlayMore() ? "" : "Press Submit or Enter.");
  else if (!canPlayMore()) setHint("That play isn't legal — you must use as many dice as possible. Undo and try again.", true);
  else setHint(uniq(S.dice).length > 1
    ? `Click a checker to play the ${S.dice[0]} (right-click: the ${S.dice[1]}) · click the dice to swap.`
    : "Click a checker to move it.");
}

function render() { drawBoard(); refreshControls(); }

// Click a checker: play the leftmost unused die with it, or the other die if
// that one can't be played there. Right-click (useOther) tries the other die first.
function clickPoint(p, useOther = false) {
  if (S.result || !S.pos) return;
  const mine = p === BAR ? S.me[24] > 0 : p >= 1 && S.me[p - 1] > 0;
  if (!mine) return;
  const order = uniq(S.dice);
  if (useOther) order.reverse();
  for (const d of order) {
    const to = hop(S.me, S.opp, p, d);
    if (to === null) continue;
    const n = play(S.me, S.opp, p, to);
    const rest = without(S.dice, d);
    if (!completable(n.me, n.opp, rest)) continue;  // would break the "use both dice" rule
    S.hist.push({ me: S.me, opp: S.opp, dice: S.dice });
    Object.assign(S, { me: n.me, opp: n.opp, dice: rest });
    return render();
  }
  setHint("That checker can't move with these dice.", true);
}

function swapDice() {
  if (S.result || uniq(S.dice).length < 2) return;
  S.dice = S.dice.slice().reverse();
  render();
}

function undo() {
  if (!S.hist.length || S.result) return;
  Object.assign(S, S.hist.pop());
  render();
}

function metaHtml(pos) {
  const kinds = { opening: "Opening", middlegame: "Middlegame", backgame: "Back game", "backgame-opp": "Vs. back game", race: "Race", bearoff: "Bear-off" };
  const was = pos.card?.last_severity ? ` · last time: ${SEV[pos.card.last_severity].label.toLowerCase()}` : "";
  const modeTag = {
    learning: `<span class="tag review">Missed before · ${pos.card?.lapses}×${was}</span>`,
    review: `<span class="tag review">Review · missed ${pos.card?.lapses}×${was}</span>`,
    queued: `<span class="tag review">From your match</span>`,
    practice: `<span class="tag">Practice</span>`,
  }[pos.mode] || `<span class="tag new">New</span>`;
  const origin = pos.card?.origin ? `<span class="tag">${esc(pos.card.origin)}</span>` : "";
  return `${modeTag}${origin}<span class="tag">${kinds[pos.kind] || pos.kind}</span>` +
    `<span class="tag num">Roll ${pos.dice[0]}-${pos.dice[1]}</span>` +
    `<span class="tag num">Pips: you ${pos.pips.me} · opp ${pos.pips.opp}</span>` +
    `<span class="tag">Money game, cube centered</span>`;
}

function load(pos) {
  Object.assign(S, {
    pos, me: pos.board.me, opp: pos.board.opp,
    dice: pos.dice[0] === pos.dice[1] ? Array(4).fill(pos.dice[0]) : pos.dice.slice(),
    legal: new Set(pos.legal.map((r) => key(r.me, r.opp))), hist: [],
    t0: performance.now(), result: null, preview: null, pinned: null, busy: false,
  });
  $("#meta").innerHTML = metaHtml(pos);
  $("#panel").innerHTML = `<h2>Your move</h2><p>Find the best play for <b>${pos.dice[0]}-${pos.dice[1]}</b>. ` +
    `You are white, moving toward your home board at the bottom right.</p>` +
    `<p>Click a checker to move it with the highlighted die (right-click uses the other one). Click the dice to swap their order.</p>` +
    `<p class="sub">Keys: <span class="kbd">Space</span> swap dice · <span class="kbd">⌫</span> undo · <span class="kbd">Enter</span> submit · <span class="kbd">N</span> next</p>`;
  render();
}

// What /api/next serves: "mixed" (reviews and new positions alternate), "review", or "new".
let MODE = store.get("bgcoach-mode", "mixed");

function setMode(mode) {
  MODE = mode;
  store.set("bgcoach-mode", mode);
  document.querySelectorAll("#modes button").forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
}

async function nextPosition() {
  const params = new URLSearchParams({ mode: MODE });
  if ($("#kind").value) params.set("kind", $("#kind").value);
  if (S.pos?.mode) params.set("prev", S.pos.mode);
  try {
    load(await api("/api/next?" + params));
  } catch (e) {
    S.pos = null; $("#board").innerHTML = ""; $("#meta").innerHTML = "";
    const msg = esc(e.message).replace(/due (\d{4}-\d\d-\d\dT[\d:]+\+00:00)/, (_, iso) => "due " + dueText({ due: iso }));
    $("#panel").innerHTML = `<h2>Nothing to show</h2><p>${msg}</p>` +
      (MODE === "review" ? `<p><button class="primary" id="go-new">Play new positions</button></p>` : "");
    $("#go-new")?.addEventListener("click", () => { setMode("new"); nextPosition(); });
    refreshControls();
  }
  refreshDue();
}

function dueText(card) {
  if (!card) return "";
  if (card.state === "new") return "queued";
  const mins = Math.round((new Date(card.due) - Date.now()) / 60000);
  if (mins <= 0) return "due now";
  return mins < 60 ? `in ${mins} min` : mins < 60 * 36 ? `in ${Math.round(mins / 60)} h` : `in ${Math.round(mins / 1440)} days`;
}

const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
// Mistake severity (thresholds as in gnubg / XG, server/srs.py). Always shown as icon + word.
const SEV = {
  doubtful: { label: "Doubtful", icon: "!", range: "0.020–0.040" },
  error: { label: "Error", icon: "✕", range: "0.040–0.080" },
  blunder: { label: "Blunder", icon: "✕✕", range: "0.080 or more" },
};
const sevOf = (loss) => (loss < 0.02 ? null : loss < 0.04 ? "doubtful" : loss < 0.08 ? "error" : "blunder");
const sevPill = (sev) => (sev ? `<span class="sev ${sev}"><i></i>${SEV[sev].label}</span>` : "");
const KINDS = { opening: "Opening", middlegame: "Middlegame", backgame: "Back game", "backgame-opp": "Vs. back game", race: "Race", bearoff: "Bear-off" };

async function submit() {
  if (!isComplete() || S.result || S.busy) return;
  S.busy = true; refreshControls();
  try {
    const r = await api("/api/answer", {
      position_id: S.pos.id, result: { me: S.me, opp: S.opp }, ms: Math.round(performance.now() - S.t0),
    });
    S.result = r;
    showResult(r);
  } catch (e) { setHint(e.message, true); }
  S.busy = false; render(); refreshDue();
}

function showResult(r) {
  const sev = r.severity;
  let head;
  if (r.rank === 1) head = `<div class="verdict good"><span class="icon">✓</span>Best move${r.grade === "hard" ? " (slow)" : ""}</div>`;
  else if (!sev) head = `<div class="verdict good"><span class="icon">≈</span>Close to best: <span class="num">${r.eq_loss.toFixed(3)}</span></div>`;
  else head = `<div class="verdict sev-${sev}"><span class="icon">${SEV[sev].icon}</span>${SEV[sev].label}: <span class="num">${r.eq_loss.toFixed(3)}</span></div>`;
  let sub = r.rank === 1
    ? `You played <b>${r.chosen}</b>.`
    : `You played <b>${r.chosen}</b> (#${r.rank}). Best was <b>${r.moves[0].text}</b>.`;
  if (r.rank > 1 && !sev) sub += " Less than 0.020 behind, so it counts as right.";
  let note;
  if (r.card && sev) {
    const when = `<b>${dueText(r.card)}</b>`;
    note = {
      doubtful: `A small mistake: it comes back ${when}.`,
      error: `This position is in your review deck. It comes back ${when}.`,
      blunder: `A blunder: it comes back ${when}, and you need to get it right twice in a row before it is spaced out.`,
    }[sev];
  } else if (r.card) {
    note = r.card.reps <= 0
      ? `Right. One more right answer (<b>${dueText(r.card)}</b>) and this blunder starts being spaced out.`
      : `Review deck: next time <b>${dueText(r.card)}</b> (${r.card.reps} right in a row).`;
  } else note = "Played well on the first try, so it won't be scheduled for review.";
  if (r.history.length) {
    note += `<br>Earlier tries: ` + r.history.map((h) => `${esc(h.move_text)} <span class="num">(${h.eq_loss > 0 ? "−" + h.eq_loss.toFixed(3) : "best"})</span>`).join(", ");
  }
  let rows = `<li data-i="start" class="start"><span class="rk">↺</span><span class="mv">Start position</span><span></span><span class="ls"><span class="kbd">S</span></span></li>` +
    r.moves.map((m, i) => `<li data-i="${i}" class="${m.rank === r.rank ? "mine" : ""}">
      <span class="rk num">${m.rank}</span><span class="mv">${m.text}</span>
      <span class="eq num">${fmt(m.equity)}</span><span class="ls num">${m.rank > 1 ? fmt(-m.loss) : ""}${m.rank > 1 && sevOf(m.loss) ? ` <span class="dot ${sevOf(m.loss)}" title="${SEV[sevOf(m.loss)].label}"></span>` : ""}</span></li>`).join("");
  $("#panel").innerHTML = `${head}<div class="sub">${sub}</div>
    <h2>Engine ranking · gnubg ${r.plies}-ply</h2><ul class="moves">${rows}</ul>
    <div class="card-note">${note}</div>`;
  $("#panel").querySelectorAll(".moves li").forEach((li) => {
    li.addEventListener("mouseenter", () => previewMove(li.dataset.i));
    li.addEventListener("click", () => previewMove(li.dataset.i, true));
  });
  $("#panel .moves").addEventListener("mouseleave", () => previewMove(null));
  previewMove(null);
  loadExplanation(S.pos.id, r.chosen_index);
}

// Keep move notation left-to-right inside Persian text, or "24/22 13/10" shows up as "13/10 24/22".
const MOVE_RE = /((?:bar|\d{1,2})(?:\/(?:\d{1,2}|off)\*?)+(?:\(\d\))?(?:\s+(?:bar|\d{1,2})(?:\/(?:\d{1,2}|off)\*?)+(?:\(\d\))?)*)/g;
const ltrMoves = (html) => html.replace(MOVE_RE, '<bdi dir="ltr">$1</bdi>');

async function loadExplanation(positionId, chosen) {
  const box = document.createElement("div");
  box.className = "why";
  box.innerHTML = `<h2>Why</h2><p class="fa" dir="rtl" lang="fa">در حال نوشتن توضیح…</p>`;
  $("#panel .card-note").before(box);
  let e;
  try {
    e = await api(`/api/explain/${positionId}?chosen=${chosen}`);
  } catch (err) {
    box.querySelector(".fa").outerHTML = `<p class="sub">${esc(err.message)}</p>`;
    return;
  }
  if (S.pos?.id !== positionId) return; // moved on already
  const b = e.facts.best, o = e.facts.other;
  const pct = (x) => Math.round(x * 100) + "%";
  const blots = (f) => (f.blots.length ? `${f.blots.length} · ${f.shots_to_hit_you}/36 shots` : "none");
  const prime = (f) => (f.longest_prime ? `${f.longest_prime.length} (${f.longest_prime.from}–${f.longest_prime.to})` : "—");
  const rows = [
    ["Hits", b.hits, o.hits],
    ["Your blots", blots(b), blots(o)],
    ["Points made", b.points_made.join(", ") || "—", o.points_made.join(", ") || "—"],
    ["Home points", b.home_board_points, o.home_board_points],
    ["Longest prime", prime(b), prime(o)],
    ["Win", pct(b.win), pct(o.win)],
    ["Win gammon", pct(b.win_gammon), pct(o.win_gammon)],
    ["Lose gammon", pct(b.lose_gammon), pct(o.lose_gammon)],
  ];
  const source = e.source === "claude" ? "Written by Claude from the numbers below" : "Built from the numbers below (no AI)";
  const text = `<p class="fa" dir="rtl" lang="fa">${ltrMoves(esc(e.text))}</p><p class="src-note">${source}</p>`;
  box.innerHTML = `<h2>Why</h2>${text}
    <table class="facts"><thead><tr><th></th><th><code>${esc(b.move)}</code><br><span class="tag src">best</span></th>
      <th><code>${esc(o.move)}</code><br><span class="tag src">${e.facts.user_found_best ? "runner-up" : "yours"}</span></th></tr></thead>
      <tbody>${rows.map(([k, x, y]) => `<tr><td>${k}</td><td class="num">${x}</td><td class="num">${y}</td></tr>`).join("")}</tbody></table>`;
}

// What the board shows after answering: "start", a move index (as a string), or
// null for the user's own play. Hovering previews; clicking pins until clicked again.
function previewMove(key, pin) {
  if (!S.result) return;
  if (pin) S.pinned = S.pinned === key ? null : key;
  const k = pin ? S.pinned : (key ?? S.pinned);
  const moves = S.result.moves;
  if (k === "start") S.preview = { me: S.pos.board.me, opp: S.pos.board.opp };
  else if (k != null) S.preview = moves[+k].result;
  else S.preview = null;
  $("#panel").querySelectorAll(".moves li").forEach((li) => li.classList.toggle("preview", li.dataset.i === k));
  const btn = $("#start");
  btn.classList.toggle("on", k === "start");
  const label = k === "start" ? "the starting position"
    : k != null ? `${moves[+k].text}${+moves[+k].rank === 1 ? " (best)" : moves[+k].rank === S.result.rank ? " (yours)" : ""}`
    : `your play, ${S.result.chosen}`;
  setHint(`Board: ${label}. Hover a move to compare · click the dice or hold S for the start.`);
  drawBoard();
}

function toggleStart() { if (S.result) previewMove("start", true); }

async function refreshDue() {
  try {
    const s = await api("/api/stats");
    const el = $("#due");
    const d = s.deck, waiting = d.due + d.queued;
    el.textContent = waiting || "";
    el.title = `${d.due} due, ${d.queued} queued from matches`;
    el.classList.toggle("has", waiting > 0);
    return s;
  } catch { return null; }
}

// ---------- progress view ----------

async function renderProgress() {
  const s = await api("/api/stats");
  const pct = (a, b) => (b ? Math.round((100 * a) / b) + "%" : "—");
  const d = s.deck, t = s.today, cards = d.queued + d.learning + d.young + d.learned;
  const tiles = [
    ["Positions played", s.attempts, `${s.positions} in the database`],
    ["Best move", pct(s.best, s.attempts), `${s.best} of ${s.attempts}`],
    ["Avg. error", s.attempts ? (s.avg_loss * 1000).toFixed(1) : "—", "equity × 1000 per move (lower is better)"],
    ["Blunders", s.severity.blunder, `${pct(s.severity.blunder, s.attempts)} of moves · ${s.severity.error} errors · ${s.severity.doubtful} doubtful`],
    ["Due now", d.due, `${t.reviews} of ${t.max_reviews} reviews done today`],
    ["Review deck", cards, `${d.learned} learned · ${d.queued} queued`],
  ].map(([k, v, sub]) => `<div class="tile"><div class="k">${k}</div><div class="v num">${v}</div><div class="s">${sub}</div></div>`).join("");

  const states = [
    ["Queued", d.queued, "var(--st-1)", "from your matches, not shown yet"],
    ["Learning", d.learning, "var(--st-2)", "missed, back the next day"],
    ["Reviewing", d.young, "var(--st-3)", "right at least once, interval under 3 weeks"],
    ["Learned", d.learned, "var(--st-4)", "interval of 3 weeks or more"],
  ];
  const deckBar = cards
    ? `<div class="deck" role="img" aria-label="Review deck by state">${states.filter(([, n]) => n)
        .map(([k, n, c]) => `<span title="${k}: ${n}" style="flex:${n};background:${c}"></span>`).join("")}</div>`
    : "";
  const legend = `<div class="legend">${states.map(([k, n, c, h]) => `<span title="${h}"><i style="background:${c}"></i>${k} <b class="num">${n}</b></span>`).join("")}</div>`;
  const days = Array.from({ length: 7 }, (_, i) => new Date(Date.now() + i * 864e5).toISOString().slice(0, 10));
  const fc = Object.fromEntries(s.forecast.map((f) => [f.day, f.n]));
  // Anything overdue counts as today.
  const overdue = s.forecast.filter((f) => f.day < days[0]).reduce((a, f) => a + f.n, 0);
  const forecastRow = days.map((day, i) => `<td class="r num">${(fc[day] || 0) + (i ? 0 : overdue)}</td>`).join("");
  const deckBox = `<div class="box"><h3>Review deck</h3>
    <p class="cap">At most <b>${t.max_reviews}</b> reviews and <b>${t.max_new}</b> queued mistakes a day — past that you get fresh
      positions, so a big backlog never takes over. Today: ${t.reviews}/${t.max_reviews} reviews, ${t.introduced}/${t.max_new} new from matches.</p>
    ${deckBar}${legend}
    <table style="margin-top:14px"><thead><tr><th>Due</th>${days.map((day, i) => `<th class="r">${i ? day.slice(5) : "Today"}</th>`).join("")}</tr></thead>
      <tbody><tr><td>Cards</td>${forecastRow}</tr></tbody></table></div>`;

  // Share of each kind's moves that were doubtful / errors / blunders, as one stacked bar per row.
  const sevBar = (k) => `<div class="sevbar" title="${k.doubtful} doubtful, ${k.errors} errors, ${k.blunders} blunders of ${k.n} moves">` +
    [["doubtful", k.doubtful], ["error", k.errors], ["blunder", k.blunders]]
      .map(([c, n]) => (n ? `<span class="${c}" style="width:${(100 * n) / k.n}%"></span>` : "")).join("") + `</div>`;
  const kindRows = s.by_kind.length ? s.by_kind.map((k) => `<tr>
      <td>${KINDS[k.kind] || k.kind}</td><td class="r num">${k.n}</td><td class="r num">${pct(k.best, k.n)}</td>
      <td class="r num">${k.doubtful}</td><td class="r num">${k.errors}</td><td class="r num">${k.blunders}</td>
      <td class="r num">${(k.loss * 1000).toFixed(1)}</td><td style="width:22%">${sevBar(k)}</td></tr>`).join("")
    : `<tr><td colspan="8" class="empty">No positions played yet.</td></tr>`;
  const sevLegend = `<div class="legend">${Object.entries(SEV).map(([c, v]) =>
    `<span><i class="sw ${c}"></i>${v.label} <span class="num" style="color:var(--ink-3)">${v.range}</span></span>`).join("")}</div>`;

  const mistakeRows = s.mistakes.length ? s.mistakes.map((m) => `<tr class="link" data-id="${m.position_id}">
      <td class="num">${m.created_at.slice(5, 16).replace("T", " ")}${m.source === "import" ? ` <span class="tag src">match</span>` : ""}</td>
      <td>${KINDS[m.kind] || m.kind}</td><td class="num">${m.dice}</td><td><code>${esc(m.move_text)}</code></td>
      <td class="r num">${m.eq_loss.toFixed(3)}</td><td>${sevPill(m.severity)}</td><td class="num">${m.due ? dueText(m) : ""}</td></tr>`).join("")
    : `<tr><td colspan="7" class="empty">No mistakes yet — keep playing.</td></tr>`;

  $("#progress").innerHTML = `<div class="tiles">${tiles}</div>${deckBox}
    <div class="grid2">
      <div class="box"><h3>Average error per day</h3><p class="cap">Training positions: equity lost per move × 1000, last 30 days. Lower is better.</p>
        <div class="chart" id="chart"></div></div>
      <div class="box"><h3>Blunders per 100 moves</h3><p class="cap">Moves that lost 0.080 or more, per day. The number to get down.</p>
        <div class="chart" id="chart-blunders"></div></div>
    </div>
    <div class="box"><h3>Mistakes by position type</h3><p class="cap">Where your mistakes come from, and how bad they are.</p>
      <table><thead><tr><th>Type</th><th class="r">Played</th><th class="r">Best</th><th class="r">Doubtful</th><th class="r">Errors</th>
        <th class="r">Blunders</th><th class="r">Avg. error</th><th>Share of moves</th></tr></thead><tbody>${kindRows}</tbody></table>
      ${sevLegend}</div>
    <div class="box"><h3>Recent mistakes</h3><p class="cap">Click a row to practise that position again.</p>
      <table><thead><tr><th>When (UTC)</th><th>Type</th><th>Roll</th><th>You played</th><th class="r">Error</th><th></th><th>Next review</th></tr></thead><tbody>${mistakeRows}</tbody></table></div>`;
  drawDaily($("#chart"), s.daily, (d) => d.loss * 1000,
    (d) => `Avg. error ${(d.loss * 1000).toFixed(1)} · ${d.n} played · ${Math.round((100 * d.best) / d.n)}% best`);
  drawDaily($("#chart-blunders"), s.daily, (d) => (100 * d.blunders) / d.n,
    (d) => `${d.blunders} blunder${d.blunders === 1 ? "" : "s"} in ${d.n} moves · ${d.errors} errors · ${d.doubtful} doubtful`,
    "var(--sev-blunder)", 5);
  bindPractice($("#progress"));
}

function bindPractice(root) {
  root.querySelectorAll("tr.link").forEach((tr) => tr.addEventListener("click", async () => {
    go("train");
    load(await api(`/api/position/${tr.dataset.id}`));
  }));
}

// ---------- import view ----------

const IMP = { file: null, text: "", preview: null };

async function renderImports() {
  const s = await api("/api/stats");
  $("#new-cap").textContent = s.today.max_new;
  $("#import-list").innerHTML = s.imports.length
    ? `<table><thead><tr><th>Imported (UTC)</th><th>File</th><th>You</th><th class="r">Games</th><th class="r">Your moves</th>
        <th class="r">Mistakes</th><th class="r">Error rate</th></tr></thead><tbody>${s.imports.map((i) => {
          const names = JSON.parse(i.players);
          return `<tr><td class="num">${i.created_at.slice(0, 16)}</td><td>${esc(i.filename)}</td>
            <td>${esc(names[i.player])} <span class="tag src">vs ${esc(names[1 - i.player])}</span></td>
            <td class="r num">${i.games}</td><td class="r num">${i.decisions}</td><td class="r num">${i.mistakes}</td>
            <td class="r num">${i.decisions ? ((1000 * i.total_loss) / i.decisions).toFixed(1) : "—"}</td></tr>`;
        }).join("")}</tbody></table>`
    : `<div class="empty">Nothing imported yet.</div>`;
}

async function pickFile(file) {
  if (!file) return;
  IMP.file = file;
  IMP.text = await file.text();
  $("#import-result").innerHTML = "";
  const step = $("#import-step");
  step.innerHTML = `<p>Reading <b>${esc(file.name)}</b>…</p>`;
  try {
    IMP.preview = await api("/api/import/preview", { filename: file.name, text: IMP.text });
  } catch (e) {
    step.innerHTML = `<p class="err">Couldn't read ${esc(file.name)}: ${esc(e.message)}</p>`;
    return;
  }
  const p = IMP.preview, remembered = store.get("bgcoach-me", "");
  const guess = p.players.indexOf(remembered);
  step.innerHTML = `<p><b>${esc(p.players[0])}</b> vs <b>${esc(p.players[1])}</b> · ${p.length ? p.length + "-point match" : "money session"} · ${p.games} game${p.games > 1 ? "s" : ""}</p>
    <p class="cap" style="margin:0">Which one are you?</p>
    <div class="who">${p.players.map((n, i) => `<label><input type="radio" name="who" value="${i}" ${i === guess ? "checked" : ""}>
      ${esc(n)} <span class="tag src">${p.decisions[i]} moves</span></label>`).join("")}</div>
    <button class="primary" id="analyse" ${guess < 0 ? "disabled" : ""}>Analyse my moves</button>
    <span class="hint" id="imp-hint" style="margin-left:10px;color:var(--ink-2);font-size:14px"></span>
    <p class="cap" style="margin-top:12px">Positions are analysed by gnubg as a money game (match score and cube are not taken into account yet).</p>`;
  step.querySelectorAll("input[name=who]").forEach((r) => r.addEventListener("change", () => ($("#analyse").disabled = false)));
  $("#analyse").addEventListener("click", runImport);
}

async function runImport() {
  const who = +document.querySelector("input[name=who]:checked").value;
  const n = IMP.preview.decisions[who];
  $("#analyse").disabled = true;
  $("#imp-hint").textContent = `Analysing ${n} moves… (about ${Math.max(1, Math.round(n * 0.05))} s)`;
  let r;
  try {
    r = await api("/api/import", { filename: IMP.file.name, text: IMP.text, player: who });
  } catch (e) {
    $("#imp-hint").innerHTML = `<span class="err">${esc(e.message)}</span>`;
    $("#analyse").disabled = false;
    return;
  }
  store.set("bgcoach-me", IMP.preview.players[who]);
  $("#import-step").innerHTML = "";
  const rows = r.mistakes.map((m) => `<tr class="link" data-id="${m.position_id}">
      <td class="num">${m.game}</td><td class="num">${m.move}</td><td>${KINDS[m.kind] || m.kind}</td><td class="num">${m.dice}</td>
      <td><code>${esc(m.played)}</code></td><td><code>${esc(m.best)}</code></td><td class="r num">${m.loss.toFixed(3)}</td><td>${sevPill(m.severity)}</td></tr>`).join("");
  $("#import-result").innerHTML = `<div class="tiles">
      <div class="tile"><div class="k">Your moves</div><div class="v num">${r.decisions}</div><div class="s">checker plays with a real choice</div></div>
      <div class="tile"><div class="k">Mistakes</div><div class="v num">${r.mistakes.length}</div><div class="s">${r.by_severity.blunder} blunders · ${r.by_severity.error} errors · ${r.by_severity.doubtful} doubtful — queued for review</div></div>
      <div class="tile"><div class="k">Error rate</div><div class="v num">${r.error_rate.toFixed(1)}</div><div class="s">equity × 1000 per move</div></div>
    </div>
    <div class="box"><h3>Your mistakes in ${esc(r.players[0])} vs ${esc(r.players[1])}</h3>
      <p class="cap">Biggest first. They come up in Train, up to ${(await api("/api/stats")).today.max_new} a day, before fresh positions. Click a row to look at one now.</p>
      ${r.mistakes.length ? `<table><thead><tr><th>Game</th><th>Move</th><th>Type</th><th>Roll</th><th>You played</th><th>Best</th><th class="r">Error</th><th></th></tr></thead><tbody>${rows}</tbody></table>
        <p style="margin-top:14px"><button class="primary" id="start-review">Start reviewing →</button></p>`
        : `<div class="empty">No mistakes of 0.020 or more — nicely played.</div>`}</div>`;
  bindPractice($("#import-result"));
  $("#start-review")?.addEventListener("click", () => { go("train"); nextPosition(); });
  renderImports();
  refreshDue();
}

const drop = $("#drop");
$("#file").addEventListener("change", (e) => pickFile(e.target.files[0]));
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); pickFile(e.dataTransfer.files[0]); });

// One bar per day. value(d) -> number, tipText(d) -> HTML, color: CSS colour, floor: min axis top.
function drawDaily(el, daily, value, tipText, color = "var(--series)", floor = 10) {
  if (!daily.length) { el.innerHTML = `<div class="empty">Play some positions to see your trend.</div>`; return; }
  const W = 800, H = 180, padL = 36, padB = 22, padT = 8;
  const vals = daily.map(value);
  const max = Math.max(floor, ...vals) * 1.1;
  const bw = Math.min(28, (W - padL) / daily.length - 4);
  const step = (W - padL) / daily.length;
  const y = (v) => H - padB - (v / max) * (H - padB - padT);
  let s = "";
  for (const t of [0, max / 2, max].map((v) => Math.round(v))) {
    s += `<line x1="${padL}" x2="${W}" y1="${y(t)}" y2="${y(t)}" style="stroke:var(--line)"/>` +
      `<text x="${padL - 6}" y="${y(t) + 4}" text-anchor="end" style="font:11px ui-sans-serif;fill:var(--ink-3)">${t}</text>`;
  }
  daily.forEach((d, i) => {
    const x = padL + i * step + (step - bw) / 2, v = vals[i], top = y(v), h = H - padB - top;
    if (v > 0) s += `<path d="M${x},${H - padB} V${top + Math.min(4, h)} q0,-4 4,-4 h${bw - 8} q4,0 4,4 V${H - padB} Z" style="fill:${color}"/>`;
    s += `<rect class="hov" data-i="${i}" x="${padL + i * step}" y="${padT}" width="${step}" height="${H - padB - padT}" fill="transparent"/>`;
    if (daily.length <= 12 || i % Math.ceil(daily.length / 8) === 0)
      s += `<text x="${x + bw / 2}" y="${H - 6}" text-anchor="middle" style="font:11px ui-sans-serif;fill:var(--ink-3)">${d.day.slice(5)}</text>`;
  });
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${s}</svg><div class="tip" hidden></div>`;
  const tip = el.querySelector(".tip");
  el.querySelectorAll(".hov").forEach((r) => {
    r.addEventListener("mouseenter", () => {
      const d = daily[+r.dataset.i], box = el.getBoundingClientRect(), rb = r.getBoundingClientRect();
      tip.innerHTML = `<b>${d.day}</b><br>${tipText(d)}`;
      tip.style.left = rb.left - box.left + rb.width / 2 + "px";
      tip.style.top = y(vals[+r.dataset.i]) * (box.height / H) + "px";
      tip.hidden = false;
    });
    r.addEventListener("mouseleave", () => (tip.hidden = true));
  });
}

// ---------- routing & events ----------

const VIEWS = ["train", "progress", "import"];
const viewOf = (path) => VIEWS.find((v) => path === "/" + v) || "train";

function go(view, push = true) {
  for (const v of VIEWS) $("#" + v).hidden = view !== v;
  document.querySelectorAll("nav a").forEach((a) => a.classList.toggle("on", a.dataset.nav === view));
  if (push) history.pushState({}, "", view === "train" ? "/" : "/" + view);
  if (view === "progress") renderProgress();
  if (view === "import") renderImports();
}

document.addEventListener("click", (e) => {
  const nav = e.target.closest("[data-nav]");
  if (nav) {
    e.preventDefault();
    go(nav.dataset.nav);
    if (nav.dataset.nav === "train" && (!S.pos || S.result)) nextPosition();
  }
});
window.addEventListener("popstate", () => go(viewOf(location.pathname), false));
$("#board").addEventListener("click", (e) => {
  if (e.target.closest(".dice-hit")) return S.result ? toggleStart() : swapDice();
  const t = e.target.closest(".hit");
  if (t) clickPoint(+t.dataset.p);
});
$("#board").addEventListener("contextmenu", (e) => {
  const t = e.target.closest(".hit:not(.dice-hit)");
  if (!t || S.result) return;
  e.preventDefault();
  clickPoint(+t.dataset.p, true);
});
$("#undo").addEventListener("click", undo);
$("#submit").addEventListener("click", submit);
$("#next").addEventListener("click", nextPosition);
$("#start").addEventListener("click", toggleStart);
$("#kind").value = store.get("bgcoach-kind", "");
setMode(MODE);
document.querySelectorAll("#modes button").forEach((b) => b.addEventListener("click", () => {
  const changed = b.dataset.mode !== MODE;
  setMode(b.dataset.mode);
  if ($("#train").hidden) go("train");
  // Switching mode drops the current position (no penalty: it wasn't answered) and loads one from the new mode.
  if (changed || !S.pos || S.result) nextPosition();
}));
$("#kind").addEventListener("change", () => { store.set("bgcoach-kind", $("#kind").value); nextPosition(); });
document.addEventListener("keydown", (e) => {
  if ($("#train").hidden || e.target.tagName === "SELECT") return;
  if (e.key === "Enter") { e.preventDefault(); S.result ? nextPosition() : submit(); }
  else if (e.key === "Backspace") { e.preventDefault(); undo(); }
  else if ((e.key === "n" || e.key === " ") && S.result) { e.preventDefault(); nextPosition(); }
  else if (e.key === " ") { e.preventDefault(); swapDice(); }
  else if ((e.key === "s" || e.key === "S") && S.result && !e.repeat) previewMove("start");
});
document.addEventListener("keyup", (e) => {
  // Releasing S goes back to whatever was showing before (pinned move or your play).
  if ((e.key === "s" || e.key === "S") && S.result) previewMove(null);
});

go(viewOf(location.pathname), false);
nextPosition();
