// The 4-year plan view: one school's required courses laid out by year and semester,
// with a picker to switch schools (UC first).
//
// Reads every built school's data/processed/<school>/required_courses.json (written by
// src/build_outputs.py, listed in schools.json) and draws, for the chosen school:
//   1. a heading with the school's program, college, and total credits,
//   2. a legend of subject areas with the school's credits in each,
//   3. one block per year with its term columns of course cards (height ~ credits),
//   4. a full table of the rows (an accessible view of the same data),
// plus a detail dialog with the description and canonical match for a clicked card.
//
// Co-op schools (UC, Northeastern) get a two-way switch: "Academic semesters" shows the
// 8 academic semesters in 4 years (the normalized placement, norm_semester), and "All
// terms, with co-op" shows the school's own plan years and terms, co-op work terms
// included (orig_year / orig_term). By the user's request (2026-10-20) the page doesn't
// explain how the co-op plan is normalized, and shows no calendar years, only general
// "Year 2 Spring" style labels.
//
// All text from the data is inserted with D3's .text(), which sets textContent, so
// nothing in the data is ever interpreted as HTML.

// Pixels of card height per credit hour. With 15-17 credits per semester, this keeps
// a column around 300px tall. MIN_CARD_PX keeps 1-credit cards tall enough for a line
// of text.
const PX_PER_CREDIT = 20;
const MIN_CARD_PX = 32;
// Co-op work terms are 0 credits; they get a fixed height that fits the code line and
// one line of title: 47 - 8 px of padding leaves room for two 15px lines.
const COOP_CARD_PX = 47;
// Card text metrics, matching .card in index.html: 15px lines (12px font x 1.25) and
// 6px of vertical padding. Used to work out how many title lines fit in a card.
const LINE_PX = 15;
const CARD_PAD_PX = 8;

// Page state: the chosen school and whether co-op terms are shown (co-op schools only).
// Both are kept in the URL (?school=neu&coop=1, via writeViewUrl in common.js).
const state = { school: null, coop: false };
let data = null;      // { schools, canon, rows } from loadAllSchools()
let canonById = null; // canonical_id -> canonical course

// Card height in pixels: proportional to credits, with a floor so 1-credit cards still
// fit a line of text. Range rows (science: 4-5) use the top of the range.
function cardHeight(r) {
  if (r.is_coop) return COOP_CARD_PX;
  return Math.max(MIN_CARD_PX, r.credits_max * PX_PER_CREDIT);
}

// "15" or "15–17": the credit total of a set of rows, as a range when any row is one.
// Rows with counts_toward_total = false (CMU's assumed-credit courses) are left out, so
// the totals match the school's stated degree total.
function creditSum(rows) {
  const counted = rows.filter((r) => r.counts_toward_total !== false);
  const lo = d3.sum(counted, (r) => r.credits_min); // d3.sum adds up one value per row
  const hi = d3.sum(counted, (r) => r.credits_max);
  return lo === hi ? `${lo}` : `${lo}–${hi}`;
}

// Is this school's plan a co-op plan (does it have any co-op work term)?
const isCoopSchool = (rows) => rows.some((r) => r.is_coop);

// Group one school's rows into year blocks of term columns, for the current view.
// Returns [{ label, cols: [{ head, sub, coop, rows }] }], in plan order.
//   - Academic semesters: co-op rows are left out, and rows are grouped by normalized
//     year and semester, so every school shows Years 1-4 with Semesters 1-8.
//   - All terms: rows are grouped by the school's own plan year and term, co-op terms
//     included, so UC shows its 5 years and Northeastern its Summer 1 / Summer 2 terms.
// d3.group nests the rows into Map(year -> Map(column -> rows)) and keeps plan order
// within each column; the keys are then sorted so years and terms come out in order.
function planColumns(rows, allTerms) {
  if (!allTerms) {
    const placed = rows.filter((r) => r.norm_semester !== null);
    const byYear = d3.group(placed, (r) => r.norm_year, (r) => r.norm_semester);
    return d3.sort(byYear.keys()).map((year) => ({
      label: `Year ${year}`,
      cols: d3.sort(byYear.get(year).keys()).map((sem) => {
        const semRows = byYear.get(year).get(sem);
        return { head: `Semester ${sem}`, sub: `${creditSum(semRows)} credits`, coop: false, rows: semRows };
      }),
    }));
  }
  const byYear = d3.group(rows, (r) => r.orig_year, (r) => r.orig_term);
  return d3.sort(byYear.keys()).map((year) => ({
    label: `Year ${year}`,
    // TERM_ORDER (common.js) puts Fall, Spring, and the summer terms in plan order.
    cols: d3.sort(byYear.get(year).keys(), (t) => TERM_ORDER.indexOf(t)).map((term) => {
      const termRows = byYear.get(year).get(term);
      const coop = termRows.every((r) => r.is_coop);
      return { head: term, sub: coop ? "Co-op work term" : `${creditSum(termRows)} credits`, coop, rows: termRows };
    }),
  }));
}

// Draw the heading for the chosen school: institution and program, then the college
// and the degree's total credits from the school registry (schools.json).
function drawHeading(school, rows) {
  d3.select("#school-name").text(`${school.institution}: ${school.program}`);
  const total = school.credits_min === school.credits_max ? school.credits_min : `${school.credits_min}–${school.credits_max}`;
  const courses = rows.filter((r) => !r.is_coop).length;
  d3.select("#school-facts").text(`${school.college} · ${total} credits · ${courses} courses and requirement slots`);
}

// Draw the legend: one entry per subject area the school's plan uses, with its credits
// there (the summary of how the plan divides its credits), plus keys for dashed slot
// cards and, when shown, co-op work terms. Co-op terms are 0 credits, so they don't
// change the sums.
function drawLegend(rows, showCoop) {
  const legend = d3.select("#legend");
  legend.selectAll("*").remove();
  const byArea = d3.group(rows.filter((r) => !r.is_coop), (r) => areaOf(r).key);
  for (const area of AREAS.filter((a) => byArea.has(a.key))) {
    const item = legend.append("span");
    item.append("i").style("background", area.color);
    item.append("span").text(`${area.label} · ${creditSum(byArea.get(area.key))} cr`);
  }
  const slot = legend.append("span");
  slot.append("i").attr("class", "slot-key");
  slot.append("span").text("Requirement slot (student chooses)");
  if (showCoop) {
    const coop = legend.append("span");
    coop.append("i").style("background", "var(--coop)");
    coop.append("span").text("Co-op work term");
  }
}

// Draw the year blocks and their term columns of cards.
function drawGrid(years, onSelect, allTerms) {
  const root = d3.select("#years").classed("all-terms", allTerms);
  root.selectAll("*").remove();

  for (const year of years) {
    const block = root.append("section").attr("class", "year");
    // Term count, read by the .all-terms CSS to size the block (unused in the 4-year grid).
    block.style("--cols", year.cols.length);
    block.append("h3").text(year.label);
    const sems = block.append("div").attr("class", "sems");

    for (const colData of year.cols) {
      const col = sems.append("div");
      const head = col.append("div").attr("class", "sem-head");
      head.append("b").text(colData.head);
      head.append("span").text(colData.sub);

      // The data join: one <button> per row. Buttons are focusable and respond to
      // Enter/Space, so the cards work from the keyboard too.
      const cards = col.append("div").attr("class", "stack")
        .selectAll("button").data(colData.rows).join("button")
        // A co-op card is shaded, not dashed: Northeastern's co-op rows have no course
        // code, but they aren't requirement slots.
        .attr("class", (r) => (r.is_coop ? "card coop" : r.course_code ? "card" : "card slot"))
        .style("--stripe", (r) => (r.is_coop ? "var(--axis)" : areaOf(r).color))
        // Range rows (science: 4-5) use the top of the range so the card is never too small.
        .style("height", (r) => `${cardHeight(r)}px`)
        // Native hover tooltip with the full title, since long titles are clamped.
        .attr("title", (r) => `${r.course_code || (r.is_coop ? "Co-op" : "Requirement slot")}: ${r.title} (${creditText(r)} cr)`)
        .attr("aria-label", (r) => r.is_coop
          ? `${r.course_code || ""} ${r.title}, co-op work term`
          : `${r.course_code || "Slot"} ${r.title}, ${creditText(r)} credits, ${areaOf(r).label}`)
        .on("click", (event, r) => onSelect(r));

      // .each runs a function per card with `this` bound to the DOM element, which is
      // why it uses a function() expression instead of an arrow function.
      cards.each(function (r) {
        const card = d3.select(this);
        const top = card.append("span").attr("class", "code");
        // Slots show only their credits: the dashed border and legend already mark them.
        // Co-op terms show their code (UC) or "Co-op" (Northeastern), with no credits.
        const codeText = r.is_coop ? (r.course_code || "Co-op")
          : r.course_code ? `${r.course_code} · ${creditText(r)} cr` : `${creditText(r)} cr`;
        top.append("span").text(codeText);
        if (r.description_source === "generic") appendGenericBadge(top);
        // Clamp the title to the lines left under the code line, so a long title ends in
        // an ellipsis instead of being cut through the middle of a line. 1-credit cards
        // only fit the code line, so their title is left to the hover text and dialog.
        // Northeastern's co-op title is just "Co-op", already the code line.
        const lines = Math.floor((cardHeight(r) - CARD_PAD_PX) / LINE_PX) - 1;
        const title = r.is_coop && !r.course_code ? "" : r.title;
        if (lines >= 1 && title) card.append("span").attr("class", "title").style("-webkit-line-clamp", lines).text(title);
      });
    }
  }
}

// When a row is taken, in the words of the current view: its semester in the academic
// view, its plan term ("Year 3 Fall") in the all-terms view. A school without co-op
// gets both, since there the two always agree. Co-op rows have no semester.
function whenText(r, coopSchool, allTerms) {
  if (r.is_coop) return `Co-op work term, ${origTermText(r)}`;
  if (allTerms) return origTermText(r);
  return coopSchool ? `Semester ${r.norm_semester}` : `Semester ${r.norm_semester} (${origTermText(r)})`;
}

// Draw the chosen school's rows as a plain table: the accessible, color-free view of
// the same data. It shows the same rows as the grid (no co-op rows in the academic view).
function drawTable(rows, coopSchool, allTerms) {
  const cols = [
    ["When", (r) => whenText(r, coopSchool, allTerms)],
    ["Code", (r) => r.course_code || "—"],
    ["Title", (r) => r.title],
    ["Credits", creditText],
    ["Area", (r) => (r.is_coop ? "Co-op" : areaOf(r).label)],
    ["Description", (r) => r.description_source],
    ["Canonical", (r) => r.canonical_ids || "—"],
  ];
  // Table rows in the grid's order: by semester, or by plan term when co-op is shown.
  const shown = allTerms
    ? d3.sort(rows, (a, b) => termRank(a) - termRank(b))
    : d3.sort(rows.filter((r) => r.norm_semester !== null), (r) => r.norm_semester);
  const table = d3.select("#table");
  table.selectAll("*").remove();
  table.append("thead").append("tr").selectAll("th").data(cols).join("th").text((c) => c[0]);
  table.append("tbody").selectAll("tr").data(shown).join("tr")
    .selectAll("td").data((r) => cols.map((c) => c[1](r))).join("td").text((v) => v);
}

// Fill and open the detail dialog for one row. showModal() traps focus inside the
// dialog, and Esc or the Close button closes it (a <form method="dialog"> closes its
// dialog when submitted, with no script needed).
function showDetail(row, coopSchool, allTerms) {
  const dialog = d3.select("#detail");
  dialog.selectAll("*").remove();
  const h = dialog.append("h2").text(`${row.course_code || (row.is_coop ? "Co-op" : "Requirement slot")}: ${row.title}`);
  if (row.description_source === "generic") { h.append("span").text(" "); appendGenericBadge(h); }

  const facts = [
    ["School", row.school.short_name],
    ["Credits", creditText(row)],
    ["When", whenText(row, coopSchool, allTerms)],
    ["Area", row.is_coop ? "Co-op" : areaOf(row).label],
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
    : `Description (${row.school.short_name} catalog)`);
  dialog.append("p").attr("class", "desc").text(row.description);
  if (row.description_file) {
    dialog.append("p").attr("class", "muted").text(`Source: ${row.description_file}`);
  }
  dialog.append("form").attr("method", "dialog").append("button").text("Close");
  dialog.node().showModal(); // .node() gets the underlying DOM element from the selection
}

// Draw the page for the current state. The co-op switch is shown only for a co-op
// school, and its "all terms" label gives that school's plan length (UC: 5 years,
// Northeastern: 4, since its co-ops replace summer and spring terms).
function draw() {
  const school = data.schools.find((s) => s.school_id === state.school);
  const rows = data.rows.filter((r) => r.school.school_id === state.school);
  const coopSchool = isCoopSchool(rows);
  const allTerms = coopSchool && state.coop;

  d3.select("#coop-switch").classed("hidden", !coopSchool);
  const planYears = d3.max(rows, (r) => r.orig_year);
  d3.select("#coop-on-label").text(`All terms, with co-op (${planYears} years)`);
  d3.selectAll("input[name=coop]").property("checked", function () { return this.value === (allTerms ? "1" : "0"); });

  drawHeading(school, rows);
  drawLegend(rows, allTerms);
  drawGrid(planColumns(rows, allTerms), (r) => showDetail(r, coopSchool, allTerms), allTerms);
  drawTable(rows, coopSchool, allTerms);
}

// Build the controls: the school picker (UC first, then the registry's order) and the
// co-op switch. Both start from the URL, so a view can be shared or bookmarked.
function setupControls() {
  // d3.sort is stable, so this moves UC to the top and keeps the others in order.
  const schools = d3.sort(data.schools, (s) => (s.school_id === "uc" ? 0 : 1));
  const params = new URLSearchParams(location.search);
  const fromUrl = params.get("school");
  state.school = schools.some((s) => s.school_id === fromUrl) ? fromUrl : "uc";
  state.coop = coopFromUrl();

  d3.select("#school").selectAll("option").data(schools).join("option")
    .attr("value", (s) => s.school_id).text((s) => `${s.short_name} (${s.institution})`)
    .property("selected", (s) => s.school_id === state.school);
  d3.select("#school").on("change", (event) => {
    state.school = event.target.value;
    writeViewUrl(state);
    draw();
  });

  // The switch keeps its setting across schools, so moving from UC to Northeastern
  // with co-op terms shown keeps them shown; schools without co-op ignore it.
  d3.selectAll("input[name=coop]").on("change", (event) => {
    state.coop = event.target.value === "1";
    writeViewUrl(state);
    draw();
  });
}

// Entry point: load every school's table, then build the controls and draw. Errors
// (e.g. opening the page from file://) are shown on the page instead of failing
// silently in the console.
loadAllSchools()
  .then((loaded) => {
    data = loaded;
    canonById = new Map(data.canon.map((c) => [c.canonical_id, c]));
    setupControls();
    draw();
  })
  .catch((err) => showLoadError("main", err));
