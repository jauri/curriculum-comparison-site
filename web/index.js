// The 4-year plan view: UC's required courses laid out over the 8 normalized semesters.
//
// Reads data/processed/uc/required_courses.json (written by src/build_outputs.py) and
// draws:
//   1. a legend of subject areas,
//   2. one block per year with two semester columns of course cards (height ~ credits),
//   3. a timeline mapping each original UC term to its normalized semester,
//   4. a full table of the rows (an accessible view of the same data),
// plus a detail dialog with the description and canonical match for a clicked card.
//
// All text from the data is inserted with D3's .text(), which sets textContent, so
// nothing in the data is ever interpreted as HTML.

// Pixels of card height per credit hour. With 15-17 credits per semester, this keeps
// a column around 300px tall. MIN_CARD_PX keeps 1-credit cards tall enough for a line
// of text.
const PX_PER_CREDIT = 20;
const MIN_CARD_PX = 32;
// Card text metrics, matching .card in index.html: 15px lines (12px font x 1.25) and
// 6px of vertical padding. Used to work out how many title lines fit in a card.
const LINE_PX = 15;
const CARD_PAD_PX = 8;

// Order of seasons within a calendar year, for sorting UC's original terms
// chronologically (Spring, then Summer, then Fall).
const SEASON_ORDER = { Spring: 0, Summer: 1, Fall: 2 };

// Card height in pixels: proportional to credits, with a floor so 1-credit cards still
// fit a line of text. Range rows (science: 4-5) use the top of the range.
function cardHeight(r) {
  return Math.max(MIN_CARD_PX, r.credits_max * PX_PER_CREDIT);
}

// Draw the legend: one entry per subject area, plus a key for dashed slot cards.
function drawLegend() {
  const legend = d3.select("#legend");
  for (const area of AREAS) {
    const item = legend.append("span");
    item.append("i").style("background", area.color);
    item.append("span").text(area.label);
  }
  const slot = legend.append("span");
  slot.append("i").attr("class", "slot-key");
  slot.append("span").text("Requirement slot (student chooses)");
}

// Draw the year blocks and their semester columns of cards. d3.group nests the rows
// into Map(year -> Map(semester -> rows)), keeping plan order within each semester.
// Co-op rows have no semester (null), so they are filtered out first.
function drawGrid(rows, onSelect) {
  const placed = rows.filter((r) => r.norm_semester !== null);
  const byYear = d3.group(placed, (r) => r.norm_year, (r) => r.norm_semester);
  const years = d3.select("#years");

  // d3.sort returns a new sorted array; sorting the Map's keys draws Years 1-4 in order.
  for (const year of d3.sort(byYear.keys())) {
    const block = years.append("section").attr("class", "year");
    block.append("h3").text(`Year ${year}`);
    const sems = block.append("div").attr("class", "sems");

    for (const sem of d3.sort(byYear.get(year).keys())) {
      const semRows = byYear.get(year).get(sem);
      const first = semRows[0];
      // d3.sum adds up a column; min and max differ only when a science slot is present.
      const lo = d3.sum(semRows, (r) => r.credits_min);
      const hi = d3.sum(semRows, (r) => r.credits_max);
      const col = sems.append("div");

      const head = col.append("div").attr("class", "sem-head");
      head.append("b").text(`Semester ${sem} · ${first.norm_term}`);
      head.append("span").text(`UC ${ucTermText(first)}`);
      head.append("span").text(`${lo === hi ? lo : `${lo}–${hi}`} credits`);

      // The data join: one <button> per row. Buttons are focusable and respond to
      // Enter/Space, so the cards work from the keyboard too.
      const cards = col.append("div").attr("class", "stack")
        .selectAll("button").data(semRows).join("button")
        .attr("class", (r) => (r.course_code ? "card" : "card slot"))
        .style("--stripe", (r) => areaOf(r).color)
        // Range rows (science: 4-5) use the top of the range so the card is never too small.
        .style("height", (r) => `${cardHeight(r)}px`)
        // Native hover tooltip with the full title, since long titles are clamped.
        .attr("title", (r) => `${r.course_code || "Requirement slot"}: ${r.title} (${creditText(r)} cr)`)
        .attr("aria-label", (r) => `${r.course_code || "Slot"} ${r.title}, ${creditText(r)} credits, ${areaOf(r).label}`)
        .on("click", (event, r) => onSelect(r));

      // .each runs a function per card with `this` bound to the DOM element, which is
      // why it uses a function() expression instead of an arrow function.
      cards.each(function (r) {
        const card = d3.select(this);
        const top = card.append("span").attr("class", "code");
        // Slots show only their credits: the dashed border and legend already mark them.
        top.append("span").text(r.course_code ? `${r.course_code} · ${creditText(r)} cr` : `${creditText(r)} cr`);
        if (r.description_source === "generic") appendGenericBadge(top);
        // Clamp the title to the lines left under the code line, so a long title ends in
        // an ellipsis instead of being cut through the middle of a line. 1-credit cards
        // only fit the code line, so their title is left to the hover text and dialog.
        const lines = Math.floor((cardHeight(r) - CARD_PAD_PX) / LINE_PX) - 1;
        if (lines >= 1) card.append("span").attr("class", "title").style("-webkit-line-clamp", lines).text(r.title);
      });
    }
  }
}

// Draw UC's full 5-year sequence of terms in calendar order, each labeled with its
// normalized semester or as a co-op term, so the mapping can be checked at a glance.
// Rows are reduced to one entry per term with d3.rollup (group, then keep the first row).
function drawTimeline(rows) {
  const terms = d3.rollup(rows, (g) => g[0], (r) => `${r.orig_term} ${r.orig_calendar_year}`);
  const ordered = d3.sort(terms.values(),
    (a, b) => a.orig_calendar_year - b.orig_calendar_year || SEASON_ORDER[a.orig_term] - SEASON_ORDER[b.orig_term]);

  d3.select("#timeline").selectAll("div").data(ordered).join("div")
    .attr("class", (r) => (r.is_coop ? "term coop" : "term"))
    .each(function (r) {
      const el = d3.select(this);
      el.append("b").text(ucTermText(r));
      el.append("span").text(r.is_coop ? "Co-op (removed)" : `→ Semester ${r.norm_semester}`);
    });

  const coop = rows.filter((r) => r.is_coop).map((r) => r.course_code);
  d3.select("#coop-list").text(
    `Co-op work terms (0 credits, no normalized semester): ${coop.join(", ")}. ` +
    "The 1-credit co-op prep courses PD 1011 and PD 2050 are taken in academic terms, so they stay in the plan.");
}

// Draw every row as a plain table: the accessible, color-free view of the same data.
function drawTable(rows) {
  const cols = [
    ["Semester", (r) => r.norm_semester ?? "—"], // ?? : use "—" when the value is null
    ["UC term", ucTermText],
    ["Code", (r) => r.course_code || "—"],
    ["Title", (r) => r.title],
    ["Credits", creditText],
    ["Area", (r) => areaOf(r).label],
    ["Description", (r) => r.description_source],
    ["Canonical", (r) => r.canonical_ids],
  ];
  const table = d3.select("#table");
  table.append("thead").append("tr").selectAll("th").data(cols).join("th").text((c) => c[0]);
  table.append("tbody").selectAll("tr").data(rows).join("tr")
    .selectAll("td").data((r) => cols.map((c) => c[1](r))).join("td").text((v) => v);
}

// Fill and open the detail dialog for one row. showModal() traps focus inside the
// dialog, and Esc or the Close button closes it (a <form method="dialog"> closes its
// dialog when submitted, with no script needed).
function showDetail(row, canonById) {
  const dialog = d3.select("#detail");
  dialog.selectAll("*").remove();
  const h = dialog.append("h2").text(`${row.course_code || "Requirement slot"}: ${row.title}`);
  if (row.description_source === "generic") { h.append("span").text(" "); appendGenericBadge(h); }

  const facts = [
    ["Credits", creditText(row)],
    ["Normalized", row.norm_semester ? `Semester ${row.norm_semester} (Year ${row.norm_year} ${row.norm_term})` : "Not placed (co-op)"],
    ["UC original", `${ucTermText(row)} (plan year ${row.orig_year}, ${row.orig_term_type})`],
    ["Area", areaOf(row).label],
  ];
  // One "Canonical" line per match (a row may match several canonical courses).
  for (const m of row.matches) facts.push(["Canonical", matchText(m, canonById)]);
  if (row.prerequisites) facts.push(["Prerequisites", row.prerequisites]);
  if (row.notes) facts.push(["Notes", row.notes]);
  const dl = dialog.append("dl");
  for (const [k, v] of facts) {
    dl.append("dt").text(k);
    dl.append("dd").text(v);
  }

  dialog.append("h3").text(row.description_source === "generic"
    ? "Description (generic, written for this project)"
    : "Description (UC catalog)");
  dialog.append("p").attr("class", "desc").text(row.description);
  if (row.description_file) {
    dialog.append("p").attr("class", "muted").text(`Source: ${row.description_file}`);
  }
  dialog.append("form").attr("method", "dialog").append("button").text("Close");
  dialog.node().showModal(); // .node() gets the underlying DOM element from the selection
}

// Entry point: load the data, then draw everything. Errors (e.g. opening the page from
// file://) are shown on the page instead of failing silently in the console.
loadData()
  .then(({ rows, canonById }) => {
    drawLegend();
    drawGrid(rows, (r) => showDetail(r, canonById));
    drawTimeline(rows);
    drawTable(rows);
  })
  .catch((err) => showLoadError("main", err));
