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

// Build one card's head line: "You · 10:42 PM" with the kind in its color.
function head(who, label) {
  return `<div class="head"><b>${who}</b> · ${esc(label)}</div>`;
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
    card.innerHTML = head(who + part, e.label) + `<div class="body clamped">${bodyHtml(e)}</div>` + noteHtml(e);
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
    caption: (act) => `Each cell is half an hour (U.S. Eastern). Darker means more of it was that side's turn: the author reading and writing before each message, Claude working before each reply or action. Pauses over ${act.idle_cap_minutes} minutes count as ${act.idle_cap_minutes}. Both lanes share one scale.`,
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

// Load the timeline, render it, and fill in the counts.
async function main() {
  const data = await (await fetch(DATA_DIR + "process/timeline.json")).json();
  const c = data.counts;
  document.getElementById("counts").textContent =
    ` ${c.first} to ${c.last}: ${c.sessions} working sessions, ${c.you} messages from the author ` +
    `and ${c.answers} answers to Claude's questions, ${c.claude} replies and ${c.questions} questions from Claude, ` +
    `${c.actions} actions, and ${c.commits} commits.`;

  renderOverview(data.activity);

  const root = document.getElementById("timeline");
  data.items.forEach((e) => renderItem(e, root));
  // Measure after everything is in the page, so overflow checks see the real layout.
  root.querySelectorAll(".body.clamped").forEach(addToggle);
  setupJump(data.items);
  setupExpandAll();
}

main();
