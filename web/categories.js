// The category view: the timeline's strips (one per canonical course, dots at each
// school's semester, a "course not required" bin, UC's flag), grouped into major
// categories of computing courses. Each category is a shaded horizontal band with a
// heading, and each of its canonical courses is a sub-band inside it.
// Spec: specs/12-category-view.md.
//
// Reads data/processed/course_categories.json (src/build_categories.py, from the
// hand-reviewed data/reference/course_categories.csv and category_members.csv) plus the
// timeline's files. Everything about a strip (dots, share bar, UC placement, flags) is
// built by timeline.js, which this page loads first; this file only groups and orders
// the strips and draws the bands around them.

// Geometry for the bands, in pixels (the strip geometry is timeline.js's).
const BAND_HEAD_H = 46; // the category heading row above each band
const BAND_GAP = 14; // space between the end of one band and the next heading
const BAND_PAD = 4; // shaded space above the first strip and below the last

let categories = []; // [{ category, strips }] in display order, once loaded

// Group the strips by category. Each category keeps the members some school requires
// (a canonical course no school requires has no strip, so it isn't drawn), sorted by
// typical semester (earliest first), then by how many other schools require it, then
// by the order listed in category_members.csv. Returns the groups and the computing-area
// strips that no category holds, for the page note.
function groupStrips(catList) {
  const byId = new Map(strips.map((s) => [s.canon.canonical_id, s]));
  const placed = new Set(catList.flatMap((c) => c.canonical_ids)); // flatMap: every category's ids in one list
  const groups = catList.map((category) => {
    const listed = category.canonical_ids.filter((id) => byId.has(id)).map((id) => byId.get(id));
    const rank = new Map(listed.map((s, i) => [s, i])); // listed order, for the last tie-break
    // Array.prototype.sort is stable, but the explicit rank keeps the order independent
    // of that. typicalSem is Infinity for a course only ever matched as an option, so
    // those sort last.
    listed.sort((a, b) => a.typicalSem - b.typicalSem
      || otherShare(b).required - otherShare(a).required || rank.get(a) - rank.get(b));
    return { category, strips: listed };
  }).filter((g) => g.strips.length);
  const left = strips.filter((s) => s.area === "cs" && !placed.has(s.canon.canonical_id));
  return { groups, left };
}

// A one-line summary for a category heading, e.g. "6 courses · UC requires 5 · 2 UC flags".
// "Requires" counts full matches only, like the share bar; a flag is any glyph in the
// right-hand column.
function bandSummary(g) {
  const n = g.strips.length;
  const ucHas = g.strips.filter((s) => s.definite.has("uc")).length;
  const flagged = g.strips.filter((s) => s.flags.length).length;
  const parts = [`${n} course${n === 1 ? "" : "s"}`, `UC requires ${ucHas}`];
  if (flagged) parts.push(`${flagged} UC flag${flagged === 1 ? "" : "s"}`);
  return parts.join(" · ");
}

// Draw the chart: the column heads, then for each category a heading row and a shaded
// band holding one strip (sub-band) per canonical course. The band's shading goes in
// first so the strips' rules and dots draw on top of it.
function drawCategories() {
  const svg = d3.select("#chart-categories");
  svg.selectAll("*").remove();
  drawHeads(svg); // timeline.js: years, semesters, the bin and the flag column titles
  const bands = svg.append("g"); // all shading in one group under the strips
  let y = HEAD_H;
  for (const g of categories) {
    svg.append("text").attr("class", "area-head").attr("x", 12).attr("y", y + 30).text(g.category.name);
    // The summary starts where the semester columns do, so it lines up across bands.
    svg.append("text").attr("class", "band-summary").attr("x", LABEL_W).attr("y", y + 30).text(bandSummary(g));
    y += BAND_HEAD_H;
    const top = y;
    y += BAND_PAD;
    for (const s of g.strips) {
      const h = stripHeight(s); // timeline.js: tall enough for the strip's largest stack
      drawStrip(svg.append("g").attr("transform", `translate(0,${y})`), s, h);
      y += h;
    }
    y += BAND_PAD;
    // The band: a rounded, lightly shaded box behind its strips, with a thin border
    // (class band-bg, colored in categories.html from the page's tokens).
    bands.append("rect").attr("class", "band-bg").attr("x", 2).attr("y", top)
      .attr("width", CHART_W - 4).attr("height", y - top).attr("rx", 6);
    y += BAND_GAP;
  }
  svg.attr("width", CHART_W).attr("height", y).attr("viewBox", `0 0 ${CHART_W} ${y}`);
  applyFollow(); // timeline.js: keep a followed school lit after a redraw
}

// The companion table: one row per sub-band, grouped by category, with the share of
// other schools, UC's semesters, and UC's flag spelled out with its evidence.
function renderCategoryTable() {
  const table = d3.select("#table");
  table.selectAll("*").remove();
  const head = ["Category", "Canonical course", "Other schools requiring it", "UC", "UC flag"];
  table.append("thead").append("tr").selectAll("th").data(head).join("th").text((t) => t)
    .classed("num", (t) => t === "Other schools requiring it");
  const body = table.append("tbody");
  for (const g of categories) {
    for (const s of g.strips) {
      const share = otherShare(s); // timeline.js
      const tr = body.append("tr");
      tr.append("td").text(g.category.name);
      tr.append("td").text(s.canon.name + (s.canon.kind === "slot" ? " (slot)" : ""));
      tr.append("td").attr("class", "num")
        .text(`${share.required} of ${share.n} (${share.pct}%)${share.possible ? ` + ${share.possible} possible` : ""}`);
      tr.append("td").text(ucStatus(s).text.replace(/^UC: /, "")); // ^UC: : drop the "UC: " prefix in a UC column
      tr.append("td").text(s.flags.map((f) => `${FLAG_GLYPHS[f.kind].glyph} ${FLAG_GLYPHS[f.kind].word}${f.text ? ` (${f.text.trim()})` : ""}: ${f.why}`).join("; "));
    }
  }
}

// Entry point: load the timeline's data and the categories, build the strips with
// timeline.js's buildStrips, group them, set up the picker and legend, and draw.
Promise.all([loadTimelineData(), d3.json(DATA_DIR + "course_categories.json")])
  .then(([loaded, catList]) => {
    data = loaded; // timeline.js's globals, which its strip and dot functions read
    strips = buildStrips().built;
    const { groups, left } = groupStrips(catList);
    categories = groups;
    if (left.length) d3.select("#uncategorized").text(left.map((s) => s.canon.name).join(", "));
    setupFollowAndLegend(); // timeline.js
    drawCategories();
    renderCategoryTable();
  })
  .catch((err) => showLoadError("main", err));
