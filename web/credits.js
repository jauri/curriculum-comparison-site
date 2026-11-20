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
function buildSchools({ schools, rows }) {
  // d3.group: Map school_id -> that school's rows.
  const bySchool = d3.group(rows, (r) => r.school_id);
  return schools.map((s) => {
    const areas = areaCredits(bySchool.get(s.school_id) ?? []);
    const total = { lo: d3.sum([...areas.values()], (a) => a.lo), hi: d3.sum([...areas.values()], (a) => a.hi) };
    return { school: s, isUc: s.school_id === "uc", areas, total };
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
    .on("mouseleave blur", hideTooltip);
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
    for (const a of AREAS) tr.append("td").attr("class", "num").text(rangeText(valueIn(r, a.key)));
    tr.append("td").attr("class", "num").text(rangeText(r.total));
  }
}

// Entry point: load every displayed school, sum credits per area, and draw one chart
// per area in AREAS order, then the table.
loadAllSchools()
  .then((loaded) => {
    const recs = buildSchools(loaded);
    for (const area of AREAS) drawAreaChart(area, recs);
    renderTable(recs);
  })
  .catch((err) => showLoadError("main", err));
