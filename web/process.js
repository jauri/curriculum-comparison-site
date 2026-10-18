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
// day, with an Author lane and a Claude lane of half-hour cells. The counts come
// binned from the parser (data.activity); this only shades and lays them out.
//
// Each lane is shaded on its own scale: a cell's level (1-4) is ceil(4 * sqrt(n / max)),
// where max is the busiest cell in that lane. The square root lifts small counts so a
// single message still shows, while the busiest stretches stay darkest.
function renderOverview(act) {
  const grid = document.getElementById("ov-grid");
  const readout = document.getElementById("ov-readout");
  const perDay = (24 * 60) / act.bin_minutes;
  const lanes = [
    { key: "you", name: "Author", color: "var(--you)" },
    { key: "claude", name: "Claude", color: "var(--claude)" },
  ];
  // The busiest cell per lane, over all days (flatMap joins every day's cells).
  const all = act.days.flatMap((d) => d.cells);
  const max = Object.fromEntries(lanes.map((l) => [l.key, Math.max(1, ...all.map((c) => c[l.key]))]));
  const level = (n, key) => (n ? Math.ceil(4 * Math.sqrt(n / max[key])) : 0);

  // Hour labels across the top, positioned as a share of the day's width.
  const ticks = [[0, "12a"], [6, "6a"], [12, "12p"], [18, "6p"]];
  let html = `<span></span><div class="ov-hours">` +
    ticks.map(([h, t]) => `<span style="left:${(h / 24) * 100}%">${t}</span>`).join("") + `</div>`;

  // Times for the readout: bin i of a day starts at i * bin_minutes after midnight.
  const clock = (min) => {
    const h = Math.floor(min / 60) % 24, m = min % 60;
    return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
  };

  act.days.forEach((d, di) => {
    // Look up a day's cells by bin index; bins with no activity are absent from the data.
    const byBin = new Map(d.cells.map((c) => [c.i, c]));
    html += `<div class="ov-day">${esc(d.label)}</div>`;
    lanes.forEach((l) => {
      html += `<span class="ov-lane">${l.name}</span>`;
      for (let i = 0; i < perDay; i++) {
        const c = byBin.get(i);
        const lv = c ? level(c[l.key], l.key) : 0;
        html += `<div class="ov-cell${lv ? ` on l${lv}` : ""}" style="--c:${l.color}" data-d="${di}" data-i="${i}"></div>`;
      }
    });
  });
  grid.innerHTML = html;

  // The default readout: a rough total of working time, counted as the half hours with
  // any activity at all (from either lane), so short breaks inside a session don't count.
  const hours = (all.length * act.bin_minutes) / 60;
  readout.textContent = `Active in ${all.length} half hours (about ${Math.round(hours)} hours) over ` +
    `${act.days.length} days. Hover or tap a cell for its counts.`;

  // One handler for the whole grid (event delegation): hovering a cell shows its counts
  // in the readout below; clicking or tapping keeps it selected, with a link that jumps
  // to the first entry in that half hour.
  const show = (cell, select) => {
    const d = act.days[+cell.dataset.d];
    const i = +cell.dataset.i;
    const c = d.cells.find((x) => x.i === i);
    const when = `${d.label}, ${clock(i * act.bin_minutes)}–${clock((i + 1) * act.bin_minutes)}`;
    readout.innerHTML = c
      ? `${esc(when)} · Author ${c.you} · Claude ${c.claude} · <a href="#${esc(c.first)}">Jump to this point</a>`
      : `${esc(when)} · no activity`;
    if (select) {
      grid.querySelectorAll(".sel").forEach((x) => x.classList.remove("sel"));
      cell.classList.add("sel");
    }
  };
  grid.addEventListener("pointerover", (ev) => {
    if (ev.target.classList.contains("ov-cell") && !grid.querySelector(".sel")) show(ev.target, false);
  });
  grid.addEventListener("click", (ev) => {
    if (ev.target.classList.contains("ov-cell")) show(ev.target, true);
  });
  // The jump link scrolls smoothly instead of the browser's instant hash jump.
  readout.addEventListener("click", (ev) => {
    if (ev.target.tagName !== "A") return;
    ev.preventDefault();
    document.getElementById(ev.target.getAttribute("href").slice(1))
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  });

  // The shade keys: less to more, one row of swatches per lane.
  document.getElementById("ov-keys").innerHTML = lanes.map((l) =>
    `<span class="ov-key">${l.name}&nbsp;` + [1, 2, 3, 4].map((k) =>
      `<i class="ov-cell l${k}" style="--c:${l.color}"></i>`).join("") + `</span>`).join(" ") + " less → more";
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
