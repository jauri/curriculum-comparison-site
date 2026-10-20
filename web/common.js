// Shared helpers for the web views (index.html and review.html).
//
// Data comes only from data/processed/ (CLAUDE.md: the Python and JavaScript halves meet
// through those files). The pages live in web/, so the data is one directory up. Browsers
// block fetch() on file:// URLs, so the pages must be served over HTTP. The README's
// command runs `python -m http.server` from the repo root.
//
// This file is a plain script, not an ES module, so it defines globals the page scripts
// use. That keeps the project build-free and works with a simple static server.

const DATA_DIR = "../data/processed/";

// Subject areas used to color the cards. Order matters: the colors are the reference
// palette's categorical slots in fixed order (--area-1 ... --area-6 in style.css), and
// that order is what was validated for colorblind separation. This grouping is
// presentation only. It isn't stored in the data, and it is derived from each row by
// areaOf() below.
// Since step 14 the key itself is stored in the data (`subject_area`); the labels and
// colors here are still presentation only.
const AREAS = [
  { key: "cs", label: "Computer science", color: "var(--area-1)" },
  { key: "math", label: "Math & statistics", color: "var(--area-2)" },
  { key: "science", label: "Lab science", color: "var(--area-3)" },
  { key: "eng", label: "Engineering & co-op prep", color: "var(--area-4)" },
  { key: "writing", label: "Writing", color: "var(--area-5)" },
  { key: "gened", label: "General education & free electives", color: "var(--area-6)" },
];

// Return the AREAS entry for one row. Since step 14 the area is stored on each row as
// `subject_area`, written by build_outputs.py from data/reference/subject_areas.csv, so
// the Python steps and the pages share one answer. (The subject maps that used to live
// here moved to that file.) An unknown key falls back to the first area rather than
// crashing, though build_outputs.py already refuses rows with no rule.
function areaOf(row) {
  return AREAS.find((a) => a.key === row.subject_area) ?? AREAS[0];
}

// Since step 13 a row may match several canonical courses. Each row carries them as a
// `matches` list (written by build_outputs.py), one object per canonical course with
// canonical_id, match_role, match_confidence, match_rationale, partial_match,
// match_status, and notes. The first match is the row's main one.

// Short phrase for a match's role, shown next to the canonical course's name. Plain
// "covers" matches need no label.
const ROLE_TEXT = { one_of: "possible: one of the options", all_of_group: "all options taken, in either order" };

// One line describing a match, e.g. "Databases (databases), high, possible: one of the
// options, approved". canonById maps canonical_id -> canonical course.
function matchText(m, canonById) {
  const c = canonById.get(m.canonical_id);
  const parts = [c ? `${c.name} (${m.canonical_id})` : m.canonical_id, m.match_confidence];
  if (m.partial_match) parts.push("partial");
  if (ROLE_TEXT[m.match_role]) parts.push(ROLE_TEXT[m.match_role]);
  parts.push(m.match_status);
  return parts.join(", ");
}

// Credits as text: "4" for a fixed-credit row, "4–5" for a range (an en dash).
function creditText(row) {
  return row.credits_min === row.credits_max ? `${row.credits_min}` : `${row.credits_min}–${row.credits_max}`;
}

// UC's original term as a short label, e.g. "Spring 2028".
function ucTermText(row) {
  return `${row.orig_term} ${row.orig_calendar_year}`;
}

// Load the main table and the canonical list together. Promise.all starts both
// requests at once and resolves when both finish. d3.json rejects on HTTP errors, and
// the caller shows that on the page.
function loadData() {
  return Promise.all([
    d3.json(DATA_DIR + "uc/required_courses.json"),
    d3.json(DATA_DIR + "canonical_courses.json"),
  ]).then(([rows, canon]) => ({ rows, canon, canonById: new Map(canon.map((c) => [c.canonical_id, c])) }));
}

// Load every built school's table (listed in schools.json, written by build_outputs.py)
// plus the canonical list. Each row gets a `school` field (the registry entry) so pages
// can label and filter rows by school.
function loadAllSchools() {
  return Promise.all([d3.json(DATA_DIR + "schools.json"), d3.json(DATA_DIR + "canonical_courses.json")])
    .then(([schools, canon]) =>
      Promise.all(schools.map((s) => d3.json(`${DATA_DIR}${s.school_id}/required_courses.json`)))
        .then((tables) => ({
          schools,
          canon,
          // flatMap: one flat array of rows from all tables, each tagged with its school.
          rows: tables.flatMap((rows, i) => rows.map((r) => ({ ...r, school: schools[i] }))),
        })));
}

// Show a load failure in place of the page content. The most common cause is opening
// the file directly (file://) instead of through the local server, so say so.
function showLoadError(container, err) {
  d3.select(container).append("p").attr("class", "error")
    .text(`Could not load data (${err.message}). Serve the repo over HTTP: run ` +
          "`python -m http.server` in the repo root, then open http://localhost:8000/web/.");
}

// Append the "generic" badge to a D3 selection. The title attribute shows a hover hint;
// the page also explains "generic" in a visible note, because a tooltip alone isn't
// enough (04-outputs.md: generic descriptions must be visibly marked and explained).
function appendGenericBadge(sel) {
  sel.append("span").attr("class", "badge-generic")
    .attr("title", "A typical description written for this project, not UC's own catalog text")
    .text("generic");
}

// Tooltip helpers, shared by the alignment and timeline views (moved here from
// compare.js in step 15). Each page needs a `<div class="tooltip hidden" id="tooltip">`.
// Longest description shown in a tooltip, in characters. Longer text is cut at a word
// boundary and ends in "…"; the full text is in the detail panel (click to pin).
const TIP_DESC_CHARS = 320;

// Shorten a description for the tooltip: line breaks (UC's numbered topic lists)
// become spaces, then the text is cut at the last space before the limit.
function shortDesc(text) {
  const flat = text.replace(/\s+/g, " ").trim(); // \s+ : any run of whitespace, incl. newlines
  if (flat.length <= TIP_DESC_CHARS) return flat;
  const cut = flat.slice(0, TIP_DESC_CHARS);
  return cut.slice(0, cut.lastIndexOf(" ")) + "…";
}

// Tooltip helpers. The tooltip is position: fixed, so clientX/clientY (viewport
// coordinates) place it next to the pointer. It flips left near the right edge and
// up near the bottom, so a tall tooltip (with descriptions) stays on screen.
// `descs` is a list of {heading, row} whose descriptions are shown under the lines.
function showTooltip(event, lines, descs = []) {
  const tip = d3.select("#tooltip").classed("hidden", false);
  tip.selectAll("*").remove();
  tip.append("b").text(lines[0]);
  for (const s of lines.slice(1)) tip.append("span").text(s);
  for (const { heading, row } of descs) {
    const h = tip.append("div").attr("class", "tip-head").text(heading);
    // Generic text is always labeled (04-outputs.md), in the tooltip too.
    if (row.description_source === "generic") { h.append("span").text(" "); appendGenericBadge(h); }
    tip.append("p").attr("class", "tip-desc").text(shortDesc(row.description));
  }
  moveTooltip(event);
}
function moveTooltip(event) {
  const tip = document.getElementById("tooltip");
  const flipX = event.clientX + tip.offsetWidth + 24 > window.innerWidth;
  const flipY = event.clientY + tip.offsetHeight + 24 > window.innerHeight;
  tip.style.left = `${Math.max(4, flipX ? event.clientX - tip.offsetWidth - 12 : event.clientX + 12)}px`;
  tip.style.top = `${Math.max(4, flipY ? event.clientY - tip.offsetHeight - 12 : event.clientY + 12)}px`;
}
function hideTooltip() {
  d3.select("#tooltip").classed("hidden", true);
}

// SVG text and row-label helpers shared by the alignment view and the concept alignment
// view (moved here from compare.js for specs/10-concept-alignment-view.md). The timeline
// keeps its own fitText, which also adds a hover title.
// Shorten an SVG <text> element's content with "…" until it fits maxWidth. It measures
// the rendered width with getComputedTextLength(), so the element must already be in
// the page. Binary search over the length keeps it fast for long titles.
function fitSvgText(textEl, str, maxWidth) {
  textEl.textContent = str;
  if (textEl.getComputedTextLength() <= maxWidth) return;
  let lo = 0;
  let hi = str.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    textEl.textContent = str.slice(0, mid).trimEnd() + "…";
    if (textEl.getComputedTextLength() <= maxWidth) lo = mid;
    else hi = mid - 1;
  }
  textEl.textContent = str.slice(0, lo).trimEnd() + "…";
}

// Short label for a row: its course code, or its title for slots (which have no code).
function rowLabel(r) {
  return r.course_code || r.title;
}

// "Semester 3 · Year 2 Fall" for a row. A co-op row has no normalized semester, so it
// gets its plan placement instead ("Co-op term · Year 2 Fall").
function semText(r) {
  if (r.norm_semester === null) return `Co-op term · Year ${r.orig_year} ${r.orig_term}`;
  return `Semester ${r.norm_semester} · Year ${r.norm_year} ${r.norm_term}`;
}


// Co-op terms in the alignment views (compare.js and concept_compare.js). With the
// "Show co-op terms" toggle off, both views show the 8 normalized semesters, as before.
// With it on, each school's co-op work terms are drawn in their real place between
// academic semesters, and a school with no co-op term at that point gets an empty slot,
// so semester k still lines up across the two sides. Spec: 06-alignment-view.md, "Co-op terms".

// Order of terms within one plan year (the plans' orig_term values), used to put co-op
// terms in chronological order among the academic ones.
const TERM_ORDER = ["Fall", "Spring", "Summer", "Summer 1", "Summer 2"];
// One sortable number per term: plan year first, then the term's place in the year.
const termRank = (r) => r.orig_year * 10 + TERM_ORDER.indexOf(r.orig_term);
// "Year 2 Spring", a row's original placement in its school's plan.
const origTermText = (r) => `Year ${r.orig_year} ${r.orig_term}`;
// Co-op rows are 0 credits, so they get a fixed height that fits two lines of text.
const COOP_NODE_PX = 34;
// Label gutter width on each side (with or without co-op terms): wide enough for "Year 2 Summer 1".
const COOP_LABEL_W = 118;

// Where each of one school's co-op rows goes: Map(row -> {gap, i}), where gap is the
// number of normalized semesters finished before the co-op term (the highest
// norm_semester among academic rows earlier in the plan) and i numbers the co-op terms
// in the same gap (Northeastern's Spring + Summer 1 co-op is two terms in one gap).
// The gap uses norm_semester, not the term index, so half-term pairs (03-processing.md,
// rule 6) count once.
function coopGaps(rows) {
  const academic = rows.filter((r) => r.norm_semester !== null);
  const coops = rows.filter((r) => r.is_coop).sort((a, b) => termRank(a) - termRank(b));
  const out = new Map();
  const used = new Map(); // gap -> co-op terms already placed in it
  for (const c of coops) {
    // d3.max returns undefined when no academic term comes first; ?? makes that gap 0.
    const gap = d3.max(academic.filter((a) => termRank(a) < termRank(c)), (a) => a.norm_semester) ?? 0;
    const i = used.get(gap) || 0;
    used.set(gap, i + 1);
    out.set(c, { gap, i });
  }
  return out;
}

// The vertical slots of an alignment view: semesters 1-8, plus (when withCoop) co-op
// slots after semester k, as many as the side with more co-op terms there needs.
// Returns { slots, slotOf }: slots is the top-to-bottom list of
// {kind: "sem", sem} or {kind: "coop", gap, i}, and slotOf(row) is a row's slot index,
// or null for a row that is not drawn (a co-op row when withCoop is off).
function termSlots(leftRows, rightRows, withCoop) {
  const gaps = new Map([...(withCoop ? coopGaps(leftRows) : []), ...(withCoop ? coopGaps(rightRows) : [])]);
  // Co-op slots needed after each semester: the larger of the two sides' counts.
  const need = d3.rollup([...gaps.values()], (v) => d3.max(v, (g) => g.i + 1), (g) => g.gap);
  const slots = [];
  const index = new Map(); // "s3" or "c3.0" -> slot index
  for (let k = 0; k <= 8; k++) {
    if (k > 0) { index.set(`s${k}`, slots.length); slots.push({ kind: "sem", sem: k }); }
    for (let i = 0; i < (need.get(k) || 0); i++) {
      index.set(`c${k}.${i}`, slots.length);
      slots.push({ kind: "coop", gap: k, i });
    }
  }
  const slotOf = (r) => {
    if (r.norm_semester !== null) return index.get(`s${r.norm_semester}`);
    const g = gaps.get(r);
    return g ? index.get(`c${g.gap}.${g.i}`) : null;
  };
  return { slots, slotOf };
}

// Draw the slot bands of an alignment view: a rule at the top of each slot, a shaded
// background behind co-op slots, the slot labels, and a dashed "No co-op term" box where
// one side has no co-op term in a co-op slot.
// Each side gets its own gutter (UC left, the other school right), labeled with that
// school's own term ("Semester 3 / Year 2 Spring" at UC, "Year 2 Fall" at a school
// without co-op), since the same row can be a different term at each. This holds with the
// co-op toggle off too (the user's choice, 2026-10-20), so UC's real term is always shown
// and a later-than-expected year doesn't look like a data error. With co-op terms hidden,
// a semester that comes right after a co-op term gets a third line, "after co-op".
// m holds slots, bandTop, bandH, withCoop, and the drawn nodes by side and slot
// (m.bySlot.L / .R, Maps from slot index to nodes); rowsL / rowsR are both schools'
// rows, so a semester is labeled even when the subject filter hides all its courses.
function drawSlotBands(svg, m, { width, xL, xR, nodeW, rowsL, rowsR }) {
  const g = svg.append("g");
  m.slots.forEach((s, i) => {
    const y = m.bandTop[i];
    if (s.kind === "coop") {
      g.append("rect").attr("class", "coop-band").attr("x", 0).attr("width", width).attr("y", y).attr("height", m.bandH[i]);
    }
    g.append("line").attr("class", "band-rule").attr("x1", 0).attr("x2", width).attr("y1", y).attr("y2", y);
  });

  // A two-or-more-line label: a bold first line, then the others, each fitted to its
  // gutter (the space between the chart edge and the nodes, less 8px of margin at each
  // end). <tspan> supports getComputedTextLength, so fitSvgText works on each line.
  const gutterW = (anchor) => (anchor === "start" ? xL : width - xR - nodeW) - 16;
  const label = (x, y, anchor, head, lines) => {
    const t = g.append("text").attr("class", "band-label").attr("x", x).attr("y", y + 18).attr("text-anchor", anchor);
    fitSvgText(t.append("tspan").attr("class", "sem").node(), head, gutterW(anchor));
    for (const line of lines) fitSvgText(t.append("tspan").attr("x", x).attr("dy", 15).node(), line, gutterW(anchor));
  };

  const gapsL = coopGaps(rowsL);
  const gapsR = coopGaps(rowsR);
  const sides = [["L", rowsL, gapsL, 8, "start", xL], ["R", rowsR, gapsR, width - 8, "end", xR]];
  m.slots.forEach((s, i) => {
    const y = m.bandTop[i];
    for (const [side, rows, gaps, x, anchor, xNode] of sides) {
      if (s.kind === "sem") {
        // The school's own term(s) for this semester, in plan order without repeats:
        // usually one, two for a pair of half-terms (e.g. Northeastern's summers).
        const terms = [...new Set(rows.filter((r) => r.norm_semester === s.sem)
          .sort((a, b) => termRank(a) - termRank(b)).map(origTermText))];
        // Co-op terms hidden: say when a co-op term comes just before this semester (a
        // co-op gap k sits after semester k, so semester s follows gap s - 1).
        const afterCoop = !m.withCoop && s.sem > 1 && [...gaps.values()].some((p) => p.gap === s.sem - 1);
        label(x, y, anchor, `Semester ${s.sem}`, afterCoop ? [...terms, "after co-op"] : terms);
        continue;
      }
      // [...gaps] lists [row, {gap, i}] pairs; find() picks this slot's co-op row, if any.
      const hit = [...gaps].find(([, p]) => p.gap === s.gap && p.i === s.i);
      if (hit) {
        label(x, y, anchor, "Co-op", [origTermText(hit[0])]);
      } else {
        // No co-op term here at this school: an empty, dashed placeholder box.
        const boxY = y + (m.bandH[i] - COOP_NODE_PX) / 2;
        g.append("rect").attr("class", "coop-empty").attr("x", xNode).attr("y", boxY)
          .attr("width", nodeW).attr("height", COOP_NODE_PX).attr("rx", 4);
        g.append("text").attr("class", "coop-empty-text").attr("x", xNode + nodeW / 2).attr("y", boxY + COOP_NODE_PX / 2 + 4)
          .attr("text-anchor", "middle").text("No co-op term");
      }
    }
  });
}

// Read the co-op toggle from the URL (?coop=1) and keep the URL in step with the page
// state, so a view with co-op terms on can be shared or bookmarked like ?school=osu.
const coopFromUrl = () => new URLSearchParams(location.search).get("coop") === "1";
function writeViewUrl(state) {
  history.replaceState(null, "", `?school=${state.school}${state.coop ? "&coop=1" : ""}`);
}
