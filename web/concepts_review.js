// The concept vocabulary review page (step 16, specs/08-concepts.md step A).
//
// Reads data/processed/concepts_preview.json (written by src/preview_concepts.py) and
// schools.json. It is read-only: the vocabulary is changed by editing
// data/reference/concepts.csv and rerunning the script, because a static page can't
// write files and the reference file must never be overwritten silently.
//
// The matches shown are plain phrase matches computed in Python, not tags; the page
// only displays them and highlights the phrases in each description.
// All text from the data is inserted with D3's .text() (textContent), never as HTML.

// Dot strip geometry, in pixels: one dot per school in registry order (UC first). UC's
// dot is larger (UC_R) and followed by a gap with a thin divider, so it reads as
// separate from the fifteen comparison schools.
const DOT_R = 4.5;
const UC_R = 6;
const DOT_STEP = 12;
const UC_GAP = 14;
// Canonical courses listed before the rest fold into "+N more".
const APPEARS_SHOWN = 4;

// Escape characters that have a meaning in regular expressions ("+" in "C++", "." in
// "P vs. NP"), so a phrase is matched literally. "$&" in the replacement means "the
// matched character", so each special character gets a backslash in front of it.
function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Build one case-insensitive regex that finds any of a concept's phrases in a
// description, with the same rules as the Python side: any run of whitespace matches a
// space, and no letter or digit may touch the phrase on either side (the lookbehind
// (?<![a-z0-9]) and lookahead (?![a-z0-9])). Longer phrases go first so the
// alternation prefers "hash tables" over "hash" when both are listed.
function phraseRegex(phrases) {
  const parts = [...phrases]
    .sort((a, b) => b.length - a.length)
    .map((p) => escapeRegex(p.trim()).replace(/\s+/g, "\\s+"));
  return new RegExp(`(?<![a-z0-9])(?:${parts.join("|")})(?![a-z0-9])`, "gi"); // g: all matches, i: any case
}

// Append `text` to a D3 selection with every match of `re` wrapped in <mark>. The text
// is split into plain and matched pieces and each piece is added with .text(), so
// nothing from the data is ever parsed as HTML.
function appendHighlighted(sel, text, re) {
  let last = 0;
  for (const m of text.matchAll(re)) { // matchAll yields every match with its index
    if (m.index > last) sel.append("span").text(text.slice(last, m.index));
    sel.append("mark").text(m[0]);
    last = m.index + m[0].length;
  }
  if (last < text.length) sel.append("span").text(text.slice(last));
}

// True if a row's notes say the school's catalog text may be cut off (set by the
// description parsers, e.g. "UC's catalog description may be cut off ...").
function isTruncated(row) {
  return /cut off/i.test(row.notes || "");
}

// Read the filter controls into one object. Empty values ("") mean "no filter".
function currentFilters() {
  return {
    group: document.getElementById("group").value,
    q: document.getElementById("q").value.trim().toLowerCase(),
    reach: document.getElementById("reach").value,
    uc: document.getElementById("uc").value,
  };
}

// True if a concept passes every active filter. `nSchools` and `atUC` are derived
// from its matches once, in the entry point, and stored on the concept.
function passes(c, f) {
  if (f.group && c.group !== f.group) return false;
  if (f.reach === "1" && c.nSchools !== 1) return false;
  if (f.reach === "le3" && c.nSchools > 3) return false;
  if (f.reach === "ge8" && c.nSchools < 8) return false;
  if (f.uc === "yes" && !c.atUC) return false;
  if (f.uc === "no" && c.atUC) return false;
  if (f.q) {
    const hay = [c.name, c.concept_id, c.definition, c.synonyms.join(" ")].join(" ").toLowerCase();
    if (!hay.includes(f.q)) return false;
  }
  return true;
}

// Draw the dot strip for one concept: a small SVG with one circle per school, filled
// when the school has an in-scope course using the concept's synonyms, hollow when not.
// Every row uses the same school order, so columns line up down the page and patterns
// (e.g. "everyone but UC") are visible. Hovering a dot shows the shared tooltip
// (common.js) with the school and its matching courses; the SVG has an aria-label with
// the count for screen readers.
function appendDotStrip(sel, c, schools, rowByKey) {
  const cy = UC_R + 1; // vertical center, room for the larger UC dot
  // Index 0 is UC; comparison schools start after UC's dot plus the gap.
  const firstX = 2 * UC_R + 2 + UC_GAP + DOT_R;
  const x = (i) => (i === 0 ? UC_R + 1 : firstX + (i - 1) * DOT_STEP);
  const width = x(schools.length - 1) + DOT_R + 1;
  const svg = sel.append("svg")
    .attr("class", "dots")
    .attr("width", width)
    .attr("height", 2 * UC_R + 2)
    .attr("role", "img")
    .attr("aria-label", `${c.nSchools} of ${schools.length} schools, UC ${c.atUC ? "included" : "not included"}`);
  // Divider halfway through the gap between UC and the first comparison school.
  const divX = 2 * UC_R + 2 + UC_GAP / 2;
  svg.append("line").attr("class", "divider")
    .attr("x1", divX).attr("x2", divX).attr("y1", 0).attr("y2", 2 * UC_R + 2);
  svg.selectAll("circle").data(schools).join("circle")
    .attr("cx", (s, i) => x(i))
    .attr("cy", cy)
    .attr("r", (s, i) => (i === 0 ? UC_R : DOT_R))
    // Two classes: on/off (mentioned or not) and uc for UC's own color.
    .attr("class", (s, i) => `${c.schoolIds.has(s.school_id) ? "on" : "off"}${i === 0 ? " uc" : ""}`)
    .on("mouseenter", (event, s) => showTooltip(event, dotTooltipLines(c, s, rowByKey)))
    .on("mousemove", moveTooltip)
    .on("mouseleave", hideTooltip);
}

// Tooltip text for one school's dot: the school name in bold (showTooltip bolds the
// first line), then each of its in-scope courses whose text contains a synonym, with
// the phrases found. A truncated catalog entry is noted, since a hollow dot there may
// only mean the text was cut off.
function dotTooltipLines(c, school, rowByKey) {
  const hits = c.matches.filter((m) => m.school_id === school.school_id);
  const lines = [school.short_name];
  if (!hits.length) lines.push("No in-scope course mentions it");
  for (const m of hits) {
    const row = rowByKey.get(`${m.school_id}|${m.course_code}`);
    const cut = isTruncated(row) ? " (catalog text may be cut off)" : "";
    lines.push(`${row.course_code}: ${row.title}, sem. ${row.norm_semester}${cut}`);
    lines.push(`↳ matched: ${m.phrases.join(", ")}`); // leading spaces would collapse in HTML
  }
  // On a hollow dot, say if any of the school's in-scope courses has cut-off text: the
  // concept may be in the missing part.
  if (!hits.length) {
    const cut = [...rowByKey.values()]
      .filter((r) => r.school_id === school.school_id && isTruncated(r))
      .map((r) => r.course_code);
    if (cut.length) lines.push(`Catalog text may be cut off for: ${cut.join(", ")}`);
  }
  return lines;
}

// List the canonical courses the concept's matching rows belong to, most schools first,
// e.g. "Data Structures 6". A row matched to two canonical courses (e.g. CMU 15-210:
// data structures and algorithms) counts under both. The number is schools, not rows.
function appendAppearsIn(sel, c, canonName) {
  const list = [...c.canonSchools].sort((a, b) => b[1].size - a[1].size); // [id, Set(school ids)]
  // Draw one "Name N" line into `target` for each entry.
  const lines = (target, entries) => {
    for (const [id, ids] of entries) {
      const line = target.append("div").attr("class", "canon-line");
      line.append("span").text(canonName.get(id) || id);
      line.append("span").attr("class", "muted").text(` ${ids.size}`);
    }
  };
  // Broad concepts can touch nine or more canonical courses; showing them all makes the
  // row very tall, so the top APPEARS_SHOWN are shown and the rest fold into "+N more".
  lines(sel, list.slice(0, APPEARS_SHOWN));
  if (list.length > APPEARS_SHOWN) {
    const more = sel.append("details").attr("class", "more");
    more.append("summary").text(`+${list.length - APPEARS_SHOWN} more`);
    lines(more, list.slice(APPEARS_SHOWN));
  }
}

// Redraw every group card for the current filters. With ~140 concepts, redrawing the
// whole list on each change is simple and fast enough.
function render(concepts, groups, rowByKey, ctx) {
  const f = currentFilters();
  const root = d3.select("#groups");
  root.selectAll("*").remove();
  let shown = 0;

  for (const g of groups) {
    // Most-mentioned concepts first within each group. d3.descending sorts by school
    // count; Array.sort is stable, so ties keep their concepts.csv order.
    const list = concepts
      .filter((c) => c.group === g && passes(c, f))
      .sort((a, b) => d3.descending(a.nSchools, b.nSchools));
    if (!list.length) continue;
    shown += list.length;
    const card = root.append("section").attr("class", "group");
    const h = card.append("h2").text(g + " ");
    h.append("span").attr("class", "muted").text(`${list.length} concept${list.length === 1 ? "" : "s"}`);

    const table = card.append("div").attr("class", "table-wrap").append("table");
    table.append("thead").append("tr").selectAll("th")
      .data(["Concept", "Definition and synonyms", "UC · 15 comparison schools", "Appears in (schools)"])
      .join("th")
      .attr("class", (d, i) => (i === 3 ? "hide-narrow" : null))
      .text((d) => d);
    // Color "UC" in the strip's header to match UC's dot (the legend for the color).
    const th = table.select("thead th:nth-child(3)").text("");
    th.append("span").attr("class", "uc-key").text("UC");
    th.append("span").text(" · 15 comparison schools");

    // .each with function() so `this` is the <tr> for each concept.
    table.append("tbody").selectAll("tr").data(list).join("tr").each(function (c) {
      const tr = d3.select(this);
      const first = tr.append("td");
      first.append("div").append("b").text(c.name);
      first.append("code").text(c.concept_id);

      const mid = tr.append("td");
      mid.append("div").attr("class", "def").text(c.definition);
      mid.append("div").attr("class", "syn").text(`Synonyms: ${c.synonyms.join("; ")}`);
      if (c.notes) mid.append("div").attr("class", "concept-note").text(c.notes);
      appendWhere(mid, c, rowByKey, ctx.schoolName);

      const strip = tr.append("td").attr("class", "strip");
      appendDotStrip(strip, c, ctx.schools, rowByKey);
      appendAppearsIn(tr.append("td").attr("class", "hide-narrow appears"), c, ctx.canonName);
    });
  }
  d3.select("#summary").text(`Showing ${shown} of ${concepts.length} concepts.`);
}

// A collapsible list of the in-scope courses where the concept's synonyms occur, each
// with its description and the matched phrases highlighted. Built only when opened
// (the "toggle" event), since most lists are never opened and some are long.
function appendWhere(sel, c, rowByKey, schoolName) {
  const det = sel.append("details").attr("class", "where");
  det.append("summary").text(`Where synonyms occur (${c.matches.length} course${c.matches.length === 1 ? "" : "s"})`);
  det.on("toggle", function () {
    if (!this.open || this.dataset.built) return; // build once, on first open
    this.dataset.built = "1";
    const box = d3.select(this);
    for (const m of c.matches) {
      const row = rowByKey.get(`${m.school_id}|${m.course_code}`);
      const hit = box.append("div").attr("class", "hit");
      hit.append("div").attr("class", "hit-head")
        .text(`${schoolName.get(m.school_id)} ${row.course_code}: ${row.title} (sem. ${row.norm_semester})`);
      if (isTruncated(row)) hit.append("div").attr("class", "flag").text("Catalog text may be cut off at the source.");
      appendHighlighted(hit.append("p"), row.description, phraseRegex(m.phrases));
    }
  });
}

// Entry point: load the preview, the school registry, and the canonical list; derive
// each concept's schools and canonical courses; fill the group filter; draw; and redraw
// on every filter change.
Promise.all([
  d3.json(DATA_DIR + "concepts_preview.json"),
  d3.json(DATA_DIR + "schools.json"),
  d3.json(DATA_DIR + "canonical_courses.json"),
])
  .then(([preview, schools, canon]) => {
    const ctx = {
      schools, // registry order: UC first, then the comparison set
      schoolName: new Map(schools.map((s) => [s.school_id, s.short_name])),
      canonName: new Map(canon.map((c) => [c.canonical_id, c.name])),
    };
    const rowByKey = new Map(preview.rows.map((r) => [`${r.school_id}|${r.course_code}`, r]));
    const concepts = preview.concepts.map((c) => {
      const schoolIds = new Set(c.matches.map((m) => m.school_id)); // a Set counts each school once
      // Map(canonical_id -> Set of school ids) over the matching rows.
      const canonSchools = new Map();
      for (const m of c.matches) {
        for (const id of rowByKey.get(`${m.school_id}|${m.course_code}`).canonical_ids) {
          if (!canonSchools.has(id)) canonSchools.set(id, new Set());
          canonSchools.get(id).add(m.school_id);
        }
      }
      return { ...c, schoolIds, canonSchools, nSchools: schoolIds.size, atUC: schoolIds.has("uc") };
    });
    // Groups in the order they first appear in concepts.csv.
    const groups = [...new Set(concepts.map((c) => c.group))];
    d3.select("#group").selectAll("option.g").data(groups).join("option")
      .attr("class", "g").attr("value", (g) => g).text((g) => g);
    render(concepts, groups, rowByKey, ctx);
    d3.select("#filters").on("input", () => render(concepts, groups, rowByKey, ctx));
  })
  .catch((err) => showLoadError("main", err));
