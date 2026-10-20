// Process view (specs/09-process-view.md): the project's working conversation as a
// two-sided timeline. The author's entries go on the left of a center line, Claude's
// replies and action cards on the right, with session, step, and commit dividers across.
//
// Everything comes from data/processed/process/timeline.json, written by
// src/parse_transcripts.py; this script only lays it out.

// Escape text for safe insertion as HTML (the author's messages are plain text, and
// labels can contain "<" from code).
function esc(s) {
  return String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch]);
}

// Claude's replies are Markdown. marked.parse converts it to HTML; DOMPurify.sanitize
// removes scripts and event handlers, so text from the logs can't run code in the page.
function md(s) {
  return DOMPurify.sanitize(marked.parse(s));
}

// Build one card's head line: "You · 10:42 PM" with the kind in its color, plus any
// tags (the kind-of-input chips on the author's cards).
function head(who, label, tags = "") {
  return `<div class="head"><b>${who}</b> · ${esc(label)}${tags}</div>`;
}

// The CSS color token for a kind of input: "Working style" -> var(--k-working-style).
function kindColor(kind) {
  return `var(--k-${kind.toLowerCase().replace(/ /g, "-")})`;
}

// Plain-language names for the answer classes set by the parser (answer_class).
const ANSWER_NAMES = {
  recommended: "took Claude's recommendation",
  other: "chose another option",
  own: "wrote their own answer",
  no_rec: "chose with no recommendation given",
};

// The kind-of-input tags for an author entry: the main kind, then a fainter second kind
// if it has one. Answers to Claude's questions are all Decisions, tagged with how the
// author chose. Other entries (declines, interruptions) get no tag.
function kindTags(e) {
  const tag = (k, extra = "", cls = "") =>
    `<span class="kind-tag${cls}" style="--k:${kindColor(k)}">${esc(k)}${extra}</span>`;
  if (e.sub === "answer") return tag("Decision", ` · ${ANSWER_NAMES[e.answers[0].class]}`);
  if (!e.input) return "";
  return tag(e.input) + (e.input2 ? tag(e.input2, "", " second") : "");
}

// A note the author attached in curation.csv, shown under the entry for the committee.
function noteHtml(e) {
  return e.note ? `<div class="note-c"><strong>Note:</strong> ${esc(e.note)}</div>` : "";
}

// The HTML inside one entry's card, by kind. Returns the body HTML, which goes in a
// collapsible .body element (action cards use <details> instead, so they return the
// whole card content).
function bodyHtml(e) {
  if (e.kind === "you" && e.sub === "answer") {
    // Answers to Claude's questions: each question's short header and the chosen option,
    // plus any note the author typed beside the choice.
    const items = e.answers.map((a) =>
      `<dt>${esc(a.question)}</dt><dd>${esc(a.answer)}${a.notes ? `<div class="anote">${esc(a.notes)}</div>` : ""}</dd>`);
    return `<dl class="answers">${items.join("")}</dl>`;
  }
  if (e.kind === "you") return `<div class="you-text">${esc(e.text)}</div>`;
  if (e.sub === "question") {
    // Claude's multiple-choice questions: the question, then the numbered options with
    // their descriptions and, where Claude drew one, the ASCII preview.
    return e.questions.map((q) => {
      const opts = q.options.map((o) =>
        `<li><strong>${esc(o.label)}</strong> <span class="desc">${esc(o.description)}</span>` +
        (o.preview ? `<pre>${esc(o.preview)}</pre>` : "") + `</li>`);
      return `<div class="q"><div class="qtext">${esc(q.question)}${q.multi ? " (choose any)" : ""}</div><ol>${opts.join("")}</ol></div>`;
    }).join("");
  }
  return md(e.text);
}

// Turn on the "Show more" control for a body that overflows its collapsed height.
// Bodies that fit stay as they are, with no control. Called after the card is in the
// page, since scrollHeight (the full content height) is only known once laid out.
function addToggle(body) {
  if (body.scrollHeight <= body.clientHeight + 4) {
    body.classList.remove("clamped");
    return;
  }
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "more";
  btn.textContent = "Show more";
  btn.addEventListener("click", () => {
    const open = body.classList.toggle("clamped") === false; // toggle returns the new state
    btn.textContent = open ? "Show less" : "Show more";
  });
  body.after(btn);
}

// Create the DOM for one timeline item and append it to the container.
function renderItem(e, root) {
  if (e.kind === "session" || e.kind === "step" || e.kind === "commit") {
    const div = document.createElement("div");
    div.className = `divider ${e.kind}`;
    if (e.kind === "session") div.innerHTML = `<span>${esc(e.label)}</span>`;
    if (e.kind === "step") {
      const name = e.step === "0" ? e.text : `Step ${e.step}: ${e.text}`;
      div.innerHTML = `<span id="${esc(e.id)}">${esc(name)}</span>`;
    }
    if (e.kind === "commit") div.innerHTML = `<span>Saved <code>${esc(e.hash)}</code> · ${esc(e.text)} · ${esc(e.label)}</span>`;
    root.append(div);
    return;
  }

  // A row: a dot on the line plus a card on the entry's side (set by the row's class).
  const row = document.createElement("div");
  row.className = `row ${e.kind}`;
  // What the filter matches on: the author's main kind of input, or "answer".
  if (e.input) row.dataset.input = e.input;
  if (e.sub === "answer") row.dataset.input = "answer";
  const card = document.createElement("div");
  card.className = "card";
  card.id = e.id;

  if (e.kind === "actions") {
    const n = e.calls.length;
    const when = e.end_label && e.end_label !== e.label ? `${e.label}–${e.end_label}` : e.label;
    const list = e.calls.map((c) =>
      `<li${c.rejected ? ' class="rejected" title="Stopped by the author"' : ""}>${esc(c.label)}</li>`);
    card.innerHTML = head(`Claude's actions (${n})`, when) +
      `<details><summary>${esc(e.summary)}</summary><ul>${list.join("")}</ul></details>` + noteHtml(e);
  } else {
    const who = e.kind === "you" ? (e.sub === "answer" ? "Author's choice" : "Author")
                                 : (e.sub === "question" ? "Claude asks" : "Claude");
    // A form with several questions is split into one card per question, each followed
    // by the author's answer, so number the parts ("Claude asks (2 of 4)").
    const part = e.of > 1 ? ` (${e.part} of ${e.of})` : "";
    const tags = e.kind === "you" ? kindTags(e) : "";
    card.innerHTML = head(who + part, e.label, tags) + `<div class="body clamped">${bodyHtml(e)}</div>` + noteHtml(e);
  }

  row.innerHTML = `<span class="dot" aria-hidden="true"></span>`;
  // The author's card comes first in the DOM so screen readers and the phone layout
  // read the entry in a natural order; CSS grid places it on the left.
  if (e.kind === "you") row.prepend(card); else row.append(card);
  root.append(row);
}

// Fill the "Jump to step" menu from the step dividers; choosing one scrolls to it.
function setupJump(items) {
  const sel = document.getElementById("jump");
  sel.innerHTML = `<option value="">Choose…</option>` + items.filter((e) => e.kind === "step")
    .map((e) => `<option value="${esc(e.id)}">${esc(e.step === "0" ? e.text : `${e.step}: ${e.text}`)}</option>`).join("");
  sel.addEventListener("change", () => {
    if (sel.value) document.getElementById(sel.value).scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

// "Expand all" opens every collapsed message (and switches to "Collapse all").
function setupExpandAll() {
  const btn = document.getElementById("expand-all");
  let open = false;
  btn.addEventListener("click", () => {
    open = !open;
    document.querySelectorAll(".more").forEach((m) => {
      const body = m.previousElementSibling;
      body.classList.toggle("clamped", !open); // second argument forces on or off
      m.textContent = open ? "Show less" : "Show more";
    });
    btn.textContent = open ? "Collapse all messages" : "Expand all messages";
  });
}

// Activity overview (specs/09-process-view.md, "Activity overview"): one block per
// day, with an Author lane and a Claude lane of half-hour cells. The numbers come
// binned from the parser (data.activity); this only shades and lays them out.
//
// A toggle picks the measure:
// - "count": entries and actions. Each lane is shaded on its own scale, since tool calls
//   far outnumber messages: level (1-4) = ceil(4 * sqrt(n / max)), where max is the
//   lane's busiest cell. The square root lifts small counts so one message still shows.
// - "minutes": minutes of each half hour that were that side's turn. Minutes compare
//   directly, so both lanes share one fixed scale: level = ceil(4 * minutes / 30).
const OV_LANES = [
  { key: "you", name: "Author", color: "var(--you)" },
  { key: "claude", name: "Claude", color: "var(--claude)" },
];

// Text for each measure: the caption under the grid, the key's end labels, a cell's
// value in the tooltip, and the total for the whole project (ending the caption).
const OV_MODES = {
  count: {
    caption: "Each cell is half an hour (U.S. Eastern). Darker means more activity: the author's messages, and Claude's replies plus each action. Each lane has its own scale.",
    key: "less → more",
    value: (c, l) => `${c[l.key]}`,
    // The half hours with any activity at all, from either lane.
    total: (act, all) => {
      const hours = (all.length * act.bin_minutes) / 60;
      return `Active in ${all.length} half hours (about ${Math.round(hours)} hours) over ${act.days.length} days.`;
    },
  },
  minutes: {
    caption: (act) => `Each cell is half an hour (U.S. Eastern). Darker means more of it was that side's turn: the author reading and writing before each message, Claude working before each reply or action. Pauses of ${act.idle_cap_minutes}–${act.break_minutes} minutes count as ${act.idle_cap_minutes}; longer ones are breaks, counting ${act.return_minutes} for the author (coming back to read and reply) and none for Claude. Both lanes share one scale.`,
    key: "0 → 30 min",
    value: (c, l) => `${Math.round(c[l.key + "_min"])} min`,
    // Each lane's minutes summed over every cell, in hours to one decimal.
    total: (act, all) => {
      const h = (k) => (all.reduce((sum, c) => sum + c[k + "_min"], 0) / 60).toFixed(1);
      return `Author about ${h("you")} hours, Claude about ${h("claude")} hours, over ${act.days.length} days.`;
    },
  },
};

function renderOverview(act) {
  const grid = document.getElementById("ov-grid");
  const tip = document.getElementById("ov-tip");
  const box = document.querySelector(".overview"); // the tooltip is positioned inside it
  const perDay = (24 * 60) / act.bin_minutes;
  // Every non-empty cell over all days (flatMap joins the days' cell lists).
  const all = act.days.flatMap((d) => d.cells);
  // The busiest cell per lane, for the count scale. Math.max(1, ...) guards an empty lane.
  const max = Object.fromEntries(OV_LANES.map((l) => [l.key, Math.max(1, ...all.map((c) => c[l.key]))]));
  const level = {
    count: (c, l) => (c[l.key] ? Math.ceil(4 * Math.sqrt(c[l.key] / max[l.key])) : 0),
    minutes: (c, l) => Math.min(4, Math.ceil((4 * c[l.key + "_min"]) / act.bin_minutes)),
  };
  let mode = "count";

  // Hour labels across the top, positioned as a share of the day's width.
  const ticks = [[0, "12a"], [6, "6a"], [12, "12p"], [18, "6p"]];
  let html = `<span></span><div class="ov-hours">` +
    ticks.map(([h, t]) => `<span style="left:${(h / 24) * 100}%">${t}</span>`).join("") + `</div>`;

  // Times for the tooltip: bin i of a day starts at i * bin_minutes after midnight.
  const clock = (min) => {
    const h = Math.floor(min / 60) % 24, m = min % 60;
    return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
  };

  // Lay out every cell once; shade() sets the levels for the current mode.
  act.days.forEach((d, di) => {
    html += `<div class="ov-day">${esc(d.label)}</div>`;
    OV_LANES.forEach((l, li) => {
      html += `<span class="ov-lane">${l.name}</span>`;
      for (let i = 0; i < perDay; i++) {
        html += `<div class="ov-cell" style="--c:${l.color}" data-d="${di}" data-i="${i}" data-l="${li}"></div>`;
      }
    });
  });
  grid.innerHTML = html;

  // Look up a cell's data from its position (bins with no activity are absent).
  const cellData = (el) => act.days[+el.dataset.d].cells.find((x) => x.i === +el.dataset.i);


  // Shade every cell for the current mode, and update the caption and key to match.
  function shade() {
    grid.querySelectorAll(".ov-cell").forEach((el) => {
      const c = cellData(el);
      const lv = c ? level[mode](c, OV_LANES[+el.dataset.l]) : 0;
      el.className = "ov-cell" + (c ? " on" : "") + (lv ? ` l${lv}` : "") + (el.classList.contains("sel") ? " sel" : "");
    });
    const m = OV_MODES[mode];
    // The caption ends with the project total for this measure.
    document.getElementById("ov-caption").textContent =
      (typeof m.caption === "function" ? m.caption(act) : m.caption) + " " + m.total(act, all);
    document.getElementById("ov-keys").innerHTML = OV_LANES.map((l) =>
      `<span class="ov-key">${l.name}&nbsp;` + [1, 2, 3, 4].map((k) =>
        `<i class="ov-cell l${k}" style="--c:${l.color}"></i>`).join("") + `</span>`).join(" ") + " " + m.key;
  }

  // Show one cell's tooltip: its time, both lanes' values, and (for a busy cell) a link
  // to the first entry in that half hour. "pin" (a click or tap) keeps it open and
  // clickable until the reader picks another cell, clicks elsewhere, or presses Escape.
  const show = (el, pin) => {
    const d = act.days[+el.dataset.d];
    const i = +el.dataset.i;
    const c = cellData(el);
    const when = `${d.label}, ${clock(i * act.bin_minutes)}–${clock((i + 1) * act.bin_minutes)}`;
    const vals = OV_LANES.map((l) =>
      `<div><i style="background:${l.color}"></i>${l.name}: ${OV_MODES[mode].value(c, l)}</div>`).join("");
    // The link only appears once pinned: a hover tooltip can't be clicked anyway.
    const link = pin ? `<div><a href="#${esc(c.first)}">Jump to this point</a></div>` : "";
    tip.innerHTML = `<b>${esc(when)}</b>${vals}${link}`;
    tip.hidden = false;
    tip.classList.toggle("pinned", pin);
    grid.querySelectorAll(".sel").forEach((x) => x.classList.remove("sel"));
    if (pin) el.classList.add("sel");

    // Place it centered above the cell, in the overview's coordinates, kept inside the
    // overview's width; if there's no room above (the top row), put it below instead.
    const r = el.getBoundingClientRect(), o = box.getBoundingClientRect();
    const w = tip.offsetWidth, h = tip.offsetHeight;
    const left = Math.min(Math.max(0, r.left - o.left + r.width / 2 - w / 2), o.width - w);
    let top = r.top - o.top - h - 6;
    if (top < 0) top = r.bottom - o.top + 6;
    tip.style.left = `${left}px`;
    tip.style.top = `${top}px`;
  };
  const hide = () => {
    tip.hidden = true;
    tip.classList.remove("pinned");
    grid.querySelectorAll(".sel").forEach((x) => x.classList.remove("sel"));
  };
  const pinned = () => tip.classList.contains("pinned");

  // One handler for the whole grid (event delegation) instead of one per cell. Hover
  // follows the pointer unless a cell is pinned; only cells with activity ("on") show a
  // tooltip, and moving onto an empty cell or out of the grid hides an unpinned one.
  grid.addEventListener("pointerover", (ev) => {
    if (pinned() || !ev.target.classList.contains("ov-cell")) return;
    if (ev.target.classList.contains("on")) show(ev.target, false); else hide();
  });
  grid.addEventListener("pointerleave", () => { if (!pinned()) hide(); });
  grid.addEventListener("click", (ev) => {
    if (ev.target.classList.contains("on")) show(ev.target, true);
  });
  // A click anywhere outside the grid and the tooltip closes a pinned tooltip.
  document.addEventListener("click", (ev) => {
    if (pinned() && !grid.contains(ev.target) && !tip.contains(ev.target)) hide();
  });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") hide(); });
  // The jump link scrolls smoothly instead of the browser's instant hash jump.
  tip.addEventListener("click", (ev) => {
    if (ev.target.tagName !== "A") return;
    ev.preventDefault();
    hide();
    maximizeSection("section.log"); // the target is in the log, which may be minimized
    document.getElementById(ev.target.getAttribute("href").slice(1))
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  });

  // The measure toggle: re-shade (which also refreshes the caption's total) and close
  // any open tooltip, whose numbers belong to the old measure.
  document.querySelectorAll('input[name="ov-mode"]').forEach((r) => r.addEventListener("change", () => {
    mode = r.value;
    hide();
    shade();
  }));

  shade();
}

// Kinds of input (specs/09-process-view.md): the author's typed messages by their main
// kind, as totals and then per plan step, from data.inputs (counted by the parser).
// Clicking a bar or segment filters the timeline to that kind, through the "Show" menu.
function renderInputs(inp) {
  const tip = document.getElementById("in-tip");
  const box = document.querySelector(".inputs");
  const typed = inp.kinds.reduce((sum, k) => sum + inp.totals[k], 0);

  // A data-kind attribute on each bar segment carries its category for the handlers.
  const seg = (k, n, width, title) =>
    `<div class="seg" style="--k:${kindColor(k)};width:${width}%" data-kind="${esc(k)}" data-tip="${esc(title)}"></div>`;

  // Totals, longest first. Color follows the kind (not the rank), so sorting is safe.
  const order = [...inp.kinds].sort((a, b) => inp.totals[b] - inp.totals[a]);
  const maxT = Math.max(...order.map((k) => inp.totals[k]));
  document.getElementById("in-totals").innerHTML = order.map((k) => {
    const n = inp.totals[k];
    const pct = Math.round((100 * n) / typed);
    return `<span class="lab">${esc(k)}</span>` +
      `<div class="bar">${n ? seg(k, n, (100 * n) / maxT, `${k}: ${n} of ${typed} messages (${pct}%)`) : ""}</div>` +
      `<span class="num">${n}</span>`;
  }).join("");

  // The answers to Claude's questions, as one sentence (all are Decisions).
  const a = inp.answers;
  const nA = Object.values(a).reduce((x, y) => x + y, 0);
  document.getElementById("in-answers").textContent =
    `${typed} typed messages. Separately, ${nA} answers to Claude's questions (all Decisions): ` +
    `${a.recommended} ${ANSWER_NAMES.recommended}, ${a.other} ${ANSWER_NAMES.other}, ` +
    `${a.own} ${ANSWER_NAMES.own}, and ${a.no_rec} ${ANSWER_NAMES.no_rec}.`;

  // The legend for the per-step bars, in the fixed stacking order.
  document.getElementById("in-legend").innerHTML =
    inp.kinds.map((k) => `<span style="--k:${kindColor(k)}">${esc(k)}</span>`).join("");

  // Per step: segments in the fixed order, lengths on one shared scale (the busiest
  // step's total is the full width), so steps compare by volume as well as by mix.
  const sum = (st) => inp.kinds.reduce((x, k) => x + st.kinds[k], 0);
  const maxS = Math.max(...inp.steps.map(sum));
  document.getElementById("in-steps").innerHTML = inp.steps.map((st) => {
    const n = sum(st);
    const name = st.step === "0" ? st.title : `${st.step} ${st.title}`;
    const segs = inp.kinds.filter((k) => st.kinds[k]).map((k) =>
      seg(k, st.kinds[k], (100 * st.kinds[k]) / maxS, `${name}: ${k} ${st.kinds[k]} of ${n}`)).join("");
    return `<span class="lab" title="${esc(name)}">${esc(name)}</span><div class="bar">${segs}</div><span class="num">${n}</span>`;
  }).join("");

  const status = document.getElementById("in-status");
  status.textContent = inp.reviewed === inp.rows
    ? "Categories were proposed by Claude and reviewed by the author."
    : `Categories are Claude's proposal; the author has reviewed ${inp.reviewed} of ${inp.rows}.`;
  if (inp.unclassified) status.textContent += ` ${inp.unclassified} recent messages are not yet classified.`;

  // Hover tooltips on segments, placed above the segment inside the section.
  box.addEventListener("pointerover", (ev) => {
    const el = ev.target.closest(".seg");
    if (!el) { tip.hidden = true; return; }
    tip.textContent = el.dataset.tip;
    tip.hidden = false;
    const r = el.getBoundingClientRect(), o = box.getBoundingClientRect();
    const left = Math.min(Math.max(0, r.left - o.left + r.width / 2 - tip.offsetWidth / 2), o.width - tip.offsetWidth);
    tip.style.left = `${left}px`;
    tip.style.top = `${r.top - o.top - tip.offsetHeight - 6}px`;
  });
  box.addEventListener("pointerleave", () => { tip.hidden = true; });
  // A click sets the timeline filter to that kind and scrolls to the controls.
  box.addEventListener("click", (ev) => {
    const el = ev.target.closest(".seg");
    if (!el) return;
    tip.hidden = true;
    setFilter(el.dataset.kind);
    maximizeSection("section.log"); // the filtered timeline is in the log
    document.querySelector(".controls").scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

// Token usage (specs/09-process-view.md, "Token usage"): one stacked bar per plan step,
// from data.tokens (summed per step by the parser from the logs' usage records).
//
// Three parts, in stacking order. "Context added" joins the API's uncached input and its
// cache writes: both are new context sent to Claude, and uncached input is tiny (a few
// thousand tokens in all) because Claude Code caches nearly everything. "Re-read" is the
// cache reads: the whole conversation so far, read again on every reply. It is over 95%
// of all tokens, so the toggle leaves it out by default; otherwise the other two would
// be slivers. Bars share one scale per mode, so steps compare by volume.
const TK_PARTS = [
  { key: "output", name: "Written by Claude", color: "var(--t-output)", value: (s) => s.output },
  { key: "added", name: "Context added", color: "var(--t-added)", value: (s) => s.input + s.cache_write },
  { key: "read", name: "Context re-read", color: "var(--t-read)", value: (s) => s.cache_read },
];

// A token count in short form: 542K, 1.4M, 239M (toLocaleString for counts under 1,000).
function tokenLabel(n) {
  if (n >= 1e8) return `${Math.round(n / 1e6)}M`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${Math.round(n / 1e3)}K`;
  return n.toLocaleString();
}

function renderTokens(tk) {
  const tip = document.getElementById("tk-tip");
  const box = document.querySelector(".tokens");
  let mode = "new";

  // The parts shown in a mode ("new" leaves out the re-read context).
  const parts = () => TK_PARTS.filter((p) => mode === "all" || p.key !== "read");
  const total = (s) => parts().reduce((x, p) => x + p.value(s), 0);

  function draw() {
    const shown = parts();
    document.getElementById("tk-legend").innerHTML =
      shown.map((p) => `<span style="--k:${p.color}">${p.name}</span>`).join("");
    const max = Math.max(...tk.steps.map(total));
    document.getElementById("tk-steps").innerHTML = tk.steps.map((s) => {
      const name = s.step === "0" ? s.title : `${s.step} ${s.title}`;
      // The tooltip gives every part, shown or not, plus how many replies the step took.
      const tipText = `${name}: ${s.replies} replies · ` +
        TK_PARTS.map((p) => `${p.name.toLowerCase()} ${p.value(s).toLocaleString()}`).join(" · ");
      const segs = shown.filter((p) => p.value(s)).map((p) =>
        `<div class="seg" style="--k:${p.color};width:${(100 * p.value(s)) / max}%" data-tip="${esc(tipText)}"></div>`).join("");
      return `<span class="lab" title="${esc(name)}">${esc(name)}</span><div class="bar">${segs}</div>` +
        `<span class="num">${tokenLabel(total(s))}</span>`;
    }).join("");

    const t = tk.totals;
    const all = t.output + t.input + t.cache_write + t.cache_read;
    document.getElementById("tk-note").textContent =
      `Over ${t.replies.toLocaleString()} replies from Claude: ${tokenLabel(t.output)} tokens written ` +
      `(text, tool calls, and its private reasoning), ${tokenLabel(t.input + t.cache_write)} of context added ` +
      `(messages, files read, and tool results), and ${tokenLabel(t.cache_read)} of context re-read ` +
      `(${Math.round((100 * t.cache_read) / all)}% of all tokens). Each reply re-reads the conversation so far ` +
      `from a cache, so long sessions re-read the most. Counts come from the usage record of each API call ` +
      `in the session logs; a token is about three quarters of a word.`;
  }

  // Hover tooltips, placed above the segment as in the kinds-of-input chart.
  box.addEventListener("pointerover", (ev) => {
    const el = ev.target.closest(".seg");
    if (!el) { tip.hidden = true; return; }
    tip.textContent = el.dataset.tip;
    tip.hidden = false;
    const r = el.getBoundingClientRect(), o = box.getBoundingClientRect();
    const left = Math.min(Math.max(0, r.left - o.left + r.width / 2 - tip.offsetWidth / 2), o.width - tip.offsetWidth);
    tip.style.left = `${left}px`;
    tip.style.top = `${r.top - o.top - tip.offsetHeight - 6}px`;
  });
  box.addEventListener("pointerleave", () => { tip.hidden = true; });

  document.querySelectorAll('input[name="tk-mode"]').forEach((r) => r.addEventListener("change", () => {
    mode = r.value;
    tip.hidden = true;
    draw();
  }));
  draw();
}

// The timeline filter: "" shows everything; a kind shows only the author's messages with
// that main kind ("answer" shows the answers to Claude's questions). While filtering,
// each step marker stays above its matching messages so the reader can see where they
// fall, but steps with no matches, session dividers, and commit lines are hidden.
function setFilter(kind) {
  const sel = document.getElementById("filter");
  sel.value = kind;
  let shown = 0;
  let step = null, stepHasMatch = false; // the last step marker seen, and whether it has matches
  const closeStep = () => { if (step) step.style.display = !kind || stepHasMatch ? "" : "none"; };
  for (const el of document.getElementById("timeline").children) {
    // display: contents rows can't use the hidden attribute reliably, so set the style.
    if (el.classList.contains("row")) {
      const match = !kind || el.dataset.input === kind;
      el.style.display = match ? "" : "none";
      if (match && kind) { shown++; stepHasMatch = true; }
    } else if (el.classList.contains("step")) {
      closeStep();
      step = el;
      stepHasMatch = false;
    } else {
      el.style.display = kind ? "none" : ""; // session and commit dividers
    }
  }
  closeStep();
  document.getElementById("filter-count").textContent = kind ? `${shown} shown` : "";
  // Highlight the matching bar segments in the chart.
  document.querySelectorAll(".inputs .seg").forEach((s) => s.classList.toggle("sel", !!kind && s.dataset.kind === kind));
}

// Fill the "Show" menu: everything, each kind of input, and the answers.
function setupFilter(inp) {
  const sel = document.getElementById("filter");
  sel.innerHTML += inp.kinds.map((k) => `<option value="${esc(k)}">Author: ${esc(k)}</option>`).join("") +
    `<option value="answer">Author: answers to Claude's questions</option>`;
  sel.addEventListener("change", () => setFilter(sel.value));
}

// Load the timeline, render it, and fill in the counts.
async function main() {
  const data = await (await fetch(DATA_DIR + "process/timeline.json")).json();
  const c = data.counts;
  document.getElementById("counts").textContent =
    ` ${c.first} to ${c.last}: ${c.sessions} working sessions, ${c.you} messages from the author ` +
    `and ${c.answers} answers to Claude's questions, ${c.claude} replies and ${c.questions} questions from Claude, ` +
    `${c.actions} actions, and ${c.commits} commits.`;

  // The count lines under each role card ("Who did what"). The answer classes come from
  // the parser's rule (did the author pick the option Claude marked as recommended?).
  const a = data.inputs.answers;
  document.getElementById("role-author").textContent =
    `${c.you} messages typed; ${c.answers} answers to Claude's questions: ` +
    `${a.recommended} took Claude's recommendation, ${a.other} chose another option, ` +
    `${a.own} wrote their own answer, and ${a.no_rec} chose where Claude made no recommendation.`;
  document.getElementById("role-claude").textContent =
    `${c.claude} replies, ${c.questions} questions, ${c.actions} actions ` +
    `(tool calls: fetching pages, reading and editing files, running scripts), and ${c.commits} commits.`;

  renderOverview(data.activity);
  renderInputs(data.inputs);
  renderTokens(data.tokens);

  const root = document.getElementById("timeline");
  data.items.forEach((e) => renderItem(e, root));
  // Measure after everything is in the page, so overflow checks see the real layout.
  root.querySelectorAll(".body.clamped").forEach(addToggle);
  setupJump(data.items);
  setupFilter(data.inputs);
  setupExpandAll();
  // Last, so the "Show more" measuring above sees every section open (a minimized
  // section has no height, so its long messages would look short).
  setupSections();
}

// ---- Minimize / maximize sections -----------------------------------------------
//
// Each <section> with an h2.sec heading can be minimized to just its heading. The
// heading's text is wrapped in a button (so it works from the keyboard and tells screen
// readers its state through aria-expanded), and everything after the heading is moved
// into one .sec-body wrapper that the `hidden` attribute hides. (Hiding the children one
// by one would also un-hide the hover tooltips, which use `hidden` themselves.) Which sections are minimized is remembered in this
// browser (localStorage), as a convenience; the page works the same without it.

const SEC_KEY = "process-page.minimized.v1";

// Read / write the set of minimized sections (by their aria-label). Storage can be
// blocked (private windows), so every access is in try/catch.
function loadMinimized() {
  try { return new Set(JSON.parse(localStorage.getItem(SEC_KEY) || "[]")); } catch (e) { return new Set(); }
}
function saveMinimized(set) {
  try { localStorage.setItem(SEC_KEY, JSON.stringify([...set])); } catch (e) { /* not remembered; fine */ }
}

// Minimize (open = false) or maximize one section: hide or show its body, and update
// the button. `remember` is false while restoring saved state.
function setSection(sec, open, remember = true) {
  sec.classList.toggle("minimized", !open);
  sec.querySelector(":scope > .sec-body").hidden = !open;
  const btn = sec.querySelector(".sec-toggle");
  btn.setAttribute("aria-expanded", String(open));
  btn.querySelector(".hint").textContent = open ? "Minimize" : "Maximize";
  if (!remember) return;
  const set = loadMinimized();
  if (open) set.delete(sec.getAttribute("aria-label")); else set.add(sec.getAttribute("aria-label"));
  saveMinimized(set);
}

// Open a minimized section (used before scrolling to something inside it).
function maximizeSection(sel) {
  const sec = document.querySelector(sel);
  if (sec && sec.classList.contains("minimized")) setSection(sec, true);
}

// Turn each section heading into a toggle, restore the saved state, and wire up the
// "Minimize all / Maximize all" buttons.
function setupSections() {
  const sections = [...document.querySelectorAll("main > section")].filter((sec) => sec.querySelector(":scope > h2.sec"));
  const saved = loadMinimized();
  for (const sec of sections) {
    const h2 = sec.querySelector(":scope > h2.sec");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sec-toggle";
    btn.innerHTML = `<span class="chev" aria-hidden="true">▾</span><span>${esc(h2.textContent)}</span><span class="hint"></span>`;
    h2.replaceChildren(btn); // the heading keeps its level; the button holds its text
    const body = document.createElement("div");
    body.className = "sec-body";
    body.id = `${sec.className.split(" ")[0]}-body`;
    btn.setAttribute("aria-controls", body.id);
    body.append(...[...sec.children].filter((el) => el !== h2)); // moves them, keeping order and listeners
    sec.append(body);
    btn.addEventListener("click", () => setSection(sec, sec.classList.contains("minimized")));
    setSection(sec, !saved.has(sec.getAttribute("aria-label")), false);
  }
  document.getElementById("sec-min-all").addEventListener("click", () => sections.forEach((sec) => setSection(sec, false)));
  document.getElementById("sec-max-all").addEventListener("click", () => sections.forEach((sec) => setSection(sec, true)));
}

main();
