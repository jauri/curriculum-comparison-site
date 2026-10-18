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
