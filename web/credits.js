// Credits view (specs/13-credits-view.md): one vertical bar chart per subject area,
// each column one school's required credits in that area. UC is always the first
// column; the other schools follow from most credits to fewest.
//
// Reads, through loadAllSchools() in common.js, data/processed/schools.json (only the
// displayed schools) and each school's <id>/required_courses.json. No new data step:
// the sums are computed here from the rows' subject_area and credits, by the same rule
// as the Course Plans legend.

// Chart geometry, in pixels. COL_W is one column's slot; the drawn column is narrower
// so a 2px+ surface gap separates neighbors. UC_GAP is the extra space after UC's
// column that sets it apart from the sorted schools.
const COL_W = 24;
const COL_GAP = 4;
const UC_GAP = 18;
const PLOT_H = 170;
const MARGIN = { top: 22, right: 76, bottom: 92, left: 34 };

// Sum one school's credits per area. Returns a Map area key -> {lo, hi, n}, where lo/hi
// are the low and high ends of the credit range and n counts the rows behind them.
// Co-op rows are left out (they are 0 credits anyway), and so are rows that are in the
// plan but not in the stated degree total (counts_toward_total = false, e.g. UIC's
// ENGR 100), so the areas add up to the school's stated total.
function areaCredits(rows) {
  const counted = rows.filter((r) => !r.is_coop && r.counts_toward_total !== false);
  // d3.rollup groups the rows by area and reduces each group to one summary object.
  return d3.rollup(counted, (g) => ({
    lo: d3.sum(g, (r) => r.credits_min),
    hi: d3.sum(g, (r) => r.credits_max),
    n: g.length,
  }), (r) => r.subject_area);
}

// Build one record per school: its registry entry, its per-area sums, and its degree
// total (the sum over areas, which equals the stated total in schools.csv).
// Each record also keeps the school's rows and its sources.json entry, which the
// evidence box reads.
function buildSchools({ schools, rows }, sources) {
  // d3.group: Map school_id -> that school's rows. The per-school JSON rows carry no
  // school_id of their own; loadAllSchools() tags each with its registry entry as
  // `school`, so the id is read from there.
  const bySchool = d3.group(rows, (r) => r.school.school_id);
  return schools.map((s) => {
    const schoolRows = bySchool.get(s.school_id) ?? [];
    const areas = areaCredits(schoolRows);
    const total = { lo: d3.sum([...areas.values()], (a) => a.lo), hi: d3.sum([...areas.values()], (a) => a.hi) };
    return { school: s, isUc: s.school_id === "uc", areas, total, rows: schoolRows, sources: sources[s.school_id] };
  });
}

// Credits as text: "8" or "8–10" (en dash) for a range.
const rangeText = (v) => (v.lo === v.hi ? `${v.lo}` : `${v.lo}–${v.hi}`);

// One area's value for a school, with zeros for an area the plan doesn't use (so a
// school with no writing course still gets a column position, at 0).
const valueIn = (rec, key) => rec.areas.get(key) ?? { lo: 0, hi: 0, n: 0 };

// The chart order for one area: UC first, then the other schools by the low end of
// their credits, most first; ties by short name so the order is stable.
function orderFor(recs, key) {
  const uc = recs.filter((r) => r.isUc);
  const others = recs.filter((r) => !r.isUc).sort((a, b) =>
    d3.descending(valueIn(a, key).lo, valueIn(b, key).lo) || d3.ascending(a.school.short_name, b.school.short_name));
  return [...uc, ...others];
}

// Draw one area's chart into a new section of #charts.
function drawAreaChart(area, recs) {
  const order = orderFor(recs, area.key);
  const others = order.filter((r) => !r.isUc);
  // Median of the other schools' low ends, the "typical school" reference line.
  const median = d3.median(others, (r) => valueIn(r, area.key).lo);

  // x position of each column's slot. UC (index 0) sits alone; every later column is
  // shifted right by UC_GAP to leave the gap where the separator rule goes.
  const xOf = (i) => i * COL_W + (i > 0 ? UC_GAP : 0);
  const plotW = xOf(order.length - 1) + COL_W;
  const width = MARGIN.left + plotW + MARGIN.right;
  const height = MARGIN.top + PLOT_H + MARGIN.bottom;

  // y scale from 0 to the largest high end in this area; .nice() rounds the top to a
  // tick value so the gridlines end on a round number.
  const maxV = d3.max(order, (r) => valueIn(r, area.key).hi) || 1;
  const y = d3.scaleLinear().domain([0, maxV]).nice().range([PLOT_H, 0]);

  const section = d3.select("#charts").append("section");
  const h2 = section.append("h2");
  h2.append("span").attr("class", "swatch").style("background", area.color);
  h2.append("span").text(area.label);
  const uc = order.find((r) => r.isUc);
  section.append("p").attr("class", "muted").text(
    `UC: ${rangeText(valueIn(uc, area.key))} credits. Median of the other ${others.length} schools: ${median}.`);

  const svg = section.append("div").attr("class", "chart-wrap").append("svg")
    .attr("width", width).attr("height", height)
    .attr("role", "img").attr("aria-label", `${area.label}: credits required by each school`);
  const g = svg.append("g").attr("transform", `translate(${MARGIN.left},${MARGIN.top})`);

  // Horizontal gridlines with tick values on the left; few ticks keep the grid quiet.
  const ticks = y.ticks(4);
  const grid = g.append("g").attr("class", "grid");
  grid.selectAll("line").data(ticks).join("line")
    .attr("x1", 0).attr("x2", plotW).attr("y1", (t) => y(t)).attr("y2", (t) => y(t));
  g.selectAll("text.axis-label").data(ticks).join("text").attr("class", "axis-label")
    .attr("x", -6).attr("y", (t) => y(t)).attr("dy", "0.32em").attr("text-anchor", "end").text((t) => t);

  // Dotted rule in the gap between UC and the sorted schools.
  const ruleX = COL_W + UC_GAP / 2;
  g.append("line").attr("class", "uc-rule").attr("x1", ruleX).attr("x2", ruleX).attr("y1", -12).attr("y2", PLOT_H);

  // One group per column. A transparent full-height rect is the hover/focus target, so
  // short columns (2 credits) are still easy to point at.
  const cols = g.selectAll("g.col").data(order).join("g").attr("class", "col")
    .attr("transform", (r, i) => `translate(${xOf(i)},0)`)
    .attr("tabindex", 0)
    .attr("aria-label", (r) => `${r.school.short_name}: ${rangeText(valueIn(r, area.key))} credits`);
  cols.append("rect").attr("class", "hit").attr("x", 0).attr("y", -12).attr("width", COL_W).attr("height", PLOT_H + 12);

  // The column itself is a path with 4px rounded top corners, square at the baseline
  // (rounded data end, anchored base). colPath draws it from y0 (bottom) to y1 (top).
  const barW = COL_W - COL_GAP;
  const colPath = (y0, y1, rounded) => {
    const h = y0 - y1;
    if (h <= 0) return "";
    const r = rounded ? Math.min(4, h, barW / 2) : 0;
    return `M0,${y0}V${y1 + r}Q0,${y1} ${r},${y1}H${barW - r}Q${barW},${y1} ${barW},${y1 + r}V${y0}Z`;
  };
  const inner = cols.append("g").attr("transform", `translate(${COL_GAP / 2},0)`);
  // Solid part, to the low end. Rounded only when there is no range cap above it.
  inner.append("path").attr("fill", area.color)
    .attr("d", (r) => { const v = valueIn(r, area.key); return colPath(y(0), y(v.lo), v.lo === v.hi); });
  // Lighter cap from the low end to the high end of a range, with the rounded top. It
  // starts 2px above the solid part, a surface gap between the two fills.
  inner.append("path").attr("class", "cap").attr("fill", area.color)
    .attr("d", (r) => { const v = valueIn(r, area.key); return v.hi > v.lo ? colPath(y(v.lo) - 2, y(v.hi), true) : ""; });

  // UC's value printed above its column (the one direct label; others are in the
  // tooltip and the table).
  g.append("text").attr("class", "value").attr("x", COL_W / 2).attr("y", y(valueIn(uc, area.key).hi) - 5)
    .attr("text-anchor", "middle").text(rangeText(valueIn(uc, area.key)));

  // Median of the other schools, across their columns only, labeled at the right end.
  if (median !== undefined) {
    g.append("line").attr("class", "median")
      .attr("x1", xOf(1) - 2).attr("x2", plotW + 4).attr("y1", y(median)).attr("y2", y(median));
    g.append("text").attr("class", "median-label").attr("x", plotW + 8).attr("y", y(median)).attr("dy", "0.32em")
      .text(`median ${median}`);
  }

  g.append("line").attr("class", "baseline").attr("x1", 0).attr("x2", plotW).attr("y1", PLOT_H).attr("y2", PLOT_H);

  // School names under the axis, rotated -50° and anchored at their end, so each name
  // runs down-left from its column's center.
  cols.append("text").attr("class", (r) => (r.isUc ? "school-label uc" : "school-label"))
    .attr("text-anchor", "end")
    .attr("transform", `translate(${COL_W / 2 + 3},${PLOT_H + 8}) rotate(-50)`)
    .text((r) => r.school.short_name);

  // Tooltip: school, credits, share of the degree, and how many rows make up the sum.
  cols.on("mouseenter focus", (event, r) => {
    const v = valueIn(r, area.key);
    const pct = r.total.lo ? Math.round((100 * v.lo) / r.total.lo) : 0;
    const rank = r.isUc ? "" : `, ${others.indexOf(r) + 1} of ${others.length} other schools`;
    showTooltip(event, [
      r.school.institution,
      `${area.label}: ${rangeText(v)} credits${rank}`,
      `${pct}% of the degree's ${rangeText(r.total)} credits`,
      `${v.n} course${v.n === 1 ? "" : "s"} and slots in the plan`,
    ]);
  })
    .on("mousemove", moveTooltip)
    .on("mouseleave blur", hideTooltip)
    // Click, tap, Enter, or Space opens the evidence for this school and area.
    .on("click", (event, r) => showEvidence(area, r))
    .on("keydown", (event, r) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); showEvidence(area, r); }
    });

  // The evidence box sits under the chart, empty and hidden until a column is chosen.
  // Its id lets the table's cells find it. aria-live announces the new content.
  section.append("div").attr("class", "evidence").attr("id", `evidence-${area.key}`)
    .attr("aria-live", "polite").property("hidden", true);
  // The chart's columns are kept on the section's node so showEvidence can mark the
  // chosen one.
  section.node().__cols = cols;
}

// ---- Evidence (specs/13-credits-view.md, "Evidence") ----

// Only http(s) links are drawn as links; anything else in the data shows as plain text,
// so a malformed sources.csv entry can never become a javascript: link.
const safeUrl = (u) => (/^https?:\/\//.test(u ?? "") ? u : null);

// Append a link to one source file's page, with its description and retrieval date.
// Links open in a new tab; rel="noopener" stops the opened page from reaching back
// into this one through window.opener.
function appendSource(sel, rec) {
  const url = safeUrl(rec?.url);
  const a = url ? sel.append("a").attr("href", url).attr("target", "_blank").attr("rel", "noopener noreferrer")
    : sel.append("span");
  a.text(rec?.description || "source");
  if (rec?.retrieved_date) sel.append("span").attr("class", "muted").text(` (retrieved ${rec.retrieved_date})`);
}

// Merge identical rows (same code, title, and kind) into one line with a count, so six
// "Technical Elective" slots read as one line "×6" instead of six. Order of first
// appearance is kept, which is the plan's own order.
function mergeRows(rows) {
  const lines = new Map();
  for (const r of rows) {
    const k = [r.course_code, r.title, r.requirement_type].join("|");
    const line = lines.get(k) ?? { row: r, count: 0, lo: 0, hi: 0 };
    line.count += 1; line.lo += r.credits_min; line.hi += r.credits_max;
    lines.set(k, line);
  }
  return [...lines.values()];
}

// Words for a row's kind in the evidence list.
const KIND_TEXT = { required: "required course", elective_slot: "elective / choice slot", gen_ed: "gen-ed slot" };

// Fill an area's evidence box for one school: where the plan came from, how the count
// is made, and every row behind it with its credits.
function showEvidence(area, rec) {
  const box = d3.select(`#evidence-${area.key}`).property("hidden", false);
  box.selectAll("*").remove();
  // Mark the chosen column in this chart (and clear the mark from the others).
  const section = box.node().parentNode;
  section.__cols.classed("chosen", (r) => r === rec);

  const v = valueIn(rec, area.key);
  const s = rec.school;
  const src = rec.sources ?? { files: {}, plan_files: [] };
  const inArea = rec.rows.filter((r) => r.subject_area === area.key && !r.is_coop);
  const counted = inArea.filter((r) => r.counts_toward_total !== false);
  const notCounted = inArea.filter((r) => r.counts_toward_total === false);

  const head = box.append("div").attr("class", "ev-head");
  head.append("strong").text(`${s.institution} · ${area.label}: ${rangeText(v)} credits`);
  head.append("button").attr("class", "ev-close").attr("aria-label", "Close evidence").text("×")
    .on("click", () => { box.property("hidden", true); section.__cols.classed("chosen", false); });

  // Sources: the plan file(s) these rows were read from, and the page that states the
  // degree total (often the same page).
  const dl = box.append("dl");
  const planFiles = [...new Set(counted.map((r) => r.source_file.split("/").pop()))];
  dl.append("dt").text(planFiles.length > 1 ? "Plan sources" : "Plan source");
  for (const f of planFiles.length ? planFiles : src.plan_files) appendSource(dl.append("dd"), src.files[f]);
  dl.append("dt").text("Degree total");
  const totalDd = dl.append("dd");
  // schools.json carries the stated total as text, so + converts it to a number.
  const stated = `${rangeText({ lo: +s.credits_min, hi: +s.credits_max })} credits, stated in `;
  if (planFiles.length === 1 && planFiles[0] === src.total_file) {
    totalDd.text(stated + "the same plan."); // one page gives both; don't repeat the link
  } else {
    totalDd.append("span").text(stated);
    appendSource(totalDd, src.files[src.total_file]);
  }
  dl.append("dt").text("Program");
  dl.append("dd").text(`${s.program}, ${s.catalog_year} catalog${s.notes ? `. ${s.notes}` : ""}`);

  // How the count is made, in one sentence, then the rows themselves.
  const pct = rec.total.lo ? Math.round((100 * v.lo) / rec.total.lo) : 0;
  box.append("p").attr("class", "ev-reason").text(counted.length
    ? `${rangeText(v)} = the sum of the ${counted.length} row${counted.length === 1 ? "" : "s"} below: every course and requirement slot in ${s.short_name}'s plan that falls in ${area.label.toLowerCase()} and counts toward the degree total, at the credits the plan gives it. That is ${pct}% of the degree's ${rangeText(rec.total)} credits.`
    : `0: ${s.short_name}'s plan has no row in ${area.label.toLowerCase()}.`);

  if (counted.length) {
    const table = box.append("div").attr("class", "table-wrap").append("table").attr("class", "ev-rows");
    const hr = table.append("thead").append("tr");
    for (const h of ["Course or slot", "Kind", "Credits"]) hr.append("th").attr("class", h === "Credits" ? "num" : null).text(h);
    const tb = table.append("tbody");
    for (const line of mergeRows(counted)) {
      const r = line.row;
      const tr = tb.append("tr");
      const td = tr.append("td");
      td.append("span").text([r.course_code, r.title].filter(Boolean).join(" ") + (line.count > 1 ? ` ×${line.count}` : ""));
      // The plan's own detail: the options of a choice slot, or the row's note.
      const detail = r.options ? `Options: ${r.options.split("; ").join(", ")}` : r.notes;
      if (detail) td.append("div").attr("class", "muted ev-note").text(detail);
      tr.append("td").text(KIND_TEXT[r.requirement_type] ?? r.requirement_type);
      tr.append("td").attr("class", "num").text(rangeText({ lo: line.lo, hi: line.hi }));
    }
    const tf = table.append("tfoot").append("tr");
    tf.append("td").attr("colspan", 2).text("Total");
    tf.append("td").attr("class", "num").text(rangeText(v));
  }

  // Rows in this area the plan lists but the stated total leaves out (e.g. a course
  // students can place out of), named so the gap between plan and count is visible.
  for (const r of notCounted) {
    box.append("p").attr("class", "muted").text(
      `Not counted: ${[r.course_code, r.title].filter(Boolean).join(" ")} (${rangeText({ lo: r.credits_min, hi: r.credits_max })}), which is not part of the stated total. ${r.notes}`);
  }

  // The area rule, so a reader can see why a course sits in this area.
  const rule = box.append("p").attr("class", "muted");
  rule.append("span").text("Courses are placed in areas by subject code and title, by the written rules in ");
  rule.append("a").attr("href", "../data/reference/subject_areas.csv").attr("target", "_blank").attr("rel", "noopener").text("subject_areas.csv");
  rule.append("span").text(".");
}

// The table under the charts: one row per school (UC first, then alphabetical by
// short name), one column per area, and the degree total.
function renderTable(recs) {
  const table = d3.select("#table");
  const head = table.append("thead").append("tr");
  head.append("th").text("School");
  for (const a of AREAS) head.append("th").attr("class", "num").text(a.label);
  head.append("th").attr("class", "num").text("Total");
  const sorted = [...recs].sort((a, b) => d3.descending(a.isUc, b.isUc) || d3.ascending(a.school.short_name, b.school.short_name));
  const body = table.append("tbody");
  for (const r of sorted) {
    const tr = body.append("tr");
    tr.append("td").append(r.isUc ? "strong" : "span").text(r.school.short_name);
    // Each cell is a button that opens that area's evidence box for this school and
    // scrolls to it, so every number in the table can be checked too.
    for (const a of AREAS) {
      tr.append("td").attr("class", "num").append("button").attr("class", "cell-link")
        .attr("aria-label", `${r.school.short_name}, ${a.label}: ${rangeText(valueIn(r, a.key))} credits. Show evidence.`)
        .text(rangeText(valueIn(r, a.key)))
        .on("click", () => { showEvidence(a, r); document.getElementById(`evidence-${a.key}`).scrollIntoView({ behavior: "smooth", block: "nearest" }); });
    }
    tr.append("td").attr("class", "num").text(rangeText(r.total));
  }
}

// Entry point: load every displayed school, sum credits per area, and draw one chart
// per area in AREAS order, then the table.
// sources.json (from src/build_sources.py) gives each plan file's URL for the evidence.
Promise.all([loadAllSchools(), d3.json(DATA_DIR + "sources.json")])
  .then(([loaded, sources]) => {
    const recs = buildSchools(loaded, sources);
    for (const area of AREAS) drawAreaChart(area, recs);
    renderTable(recs);
  })
  .catch((err) => showLoadError("main", err));
