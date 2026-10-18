// The match review view: each canonical course with every school's rows matched to it.
//
// Reads data/processed/schools.json, each school's <id>/required_courses.json, and
// canonical_courses.json (all written by src/build_outputs.py). It is read-only.
// Approvals are recorded by editing data/reference/<id>/matches.csv, because a static
// page can't write files, and the reference file must never be overwritten silently
// (04-outputs.md).
//
// All text from the data is inserted with D3's .text() (textContent), never as HTML.

// Rows that share a match key within a school (e.g. UC's two "Directed Elective" slots
// in semesters 7 and 8) are one match decision, so they are shown as one line listing
// both semesters. The key is the course code, or the title for slots, the same rule as
// src/check_canonical.py, prefixed with the school so equal titles at two schools
// ("Technical Elective") stay separate decisions.
function matchKey(r) {
  return `${r.school.school_id}|${r.course_code || r.title}`;
}

// Collapse rows into one entry per (match key, canonical course): a row that matches
// several canonical courses (step 13) is one line under each, since each match is its
// own review decision. Each line has the key's semesters and summed credits.
// d3.groups returns [key, rows] pairs in first-seen order, so plan order is kept.
// For an all_of_group match (options all taken, in either order), the group's credits
// are split evenly across its canonical courses, so they are never counted twice
// (03-processing.md: Berkeley's 2 rows x 4 units -> 4 units per course).
function matchLines(rows) {
  return d3.groups(rows, matchKey).flatMap(([key, g]) => {
    const row = g[0]; // the matches are identical across the group
    const share = (m) => (m.match_role === "all_of_group" ? row.matches.length : 1);
    return row.matches.map((m) => ({
      key,
      row,
      m,
      sems: g.map((r) => r.norm_semester).filter((s) => s !== null),
      creditsMin: d3.sum(g, (r) => r.credits_min) / share(m),
      creditsMax: d3.sum(g, (r) => r.credits_max) / share(m),
    }));
  });
}

// Read the filter controls. Search is case-insensitive and matches the code, title,
// canonical id, or canonical name.
function currentFilters() {
  return {
    q: document.getElementById("q").value.trim().toLowerCase(),
    conf: document.getElementById("conf").value,
    status: document.getElementById("status").value,
    kind: document.getElementById("kind").value,
    school: document.getElementById("school").value,
  };
}

// True if a match line passes every active filter. Empty filters ("") match all.
function passes(line, canon, f) {
  const r = line.row;
  if (f.conf && line.m.match_confidence !== f.conf) return false;
  if (f.status && line.m.match_status !== f.status) return false;
  if (f.kind && canon.kind !== f.kind) return false;
  if (f.school && r.school.school_id !== f.school) return false;
  if (f.q) {
    const hay = [line.key, r.title, r.options, canon.canonical_id, canon.name].join(" ").toLowerCase();
    if (!hay.includes(f.q)) return false;
  }
  return true;
}

// Redraw the groups for the current filters. Each canonical course is a card whose
// table lists its matching lines from every school. Canonical courses with no lines left after
// filtering are hidden. Redrawing everything is simple, and with ~30 groups it is fast.
function render(canon, linesById) {
  const f = currentFilters();
  const root = d3.select("#groups");
  root.selectAll("*").remove();
  let shownGroups = 0;
  let shownLines = 0;

  for (const c of canon) {
    const lines = (linesById.get(c.canonical_id) || []).filter((l) => passes(l, c, f));
    if (!lines.length) continue;
    shownGroups += 1;
    shownLines += lines.length;

    const g = root.append("section").attr("class", "group");
    const head = g.append("div").attr("class", "group-head");
    head.append("h3").text(c.name);
    head.append("code").text(c.canonical_id);
    head.append("span").attr("class", "kind").text(c.kind);
    head.append("span").attr("class", "muted").text(`typical ${c.typical_credits} cr`);
    g.append("p").attr("class", "canon-desc").text(c.description);
    if (c.notes) g.append("p").attr("class", "muted").style("font-size", "13px").text(`Note: ${c.notes}`);

    const wrap = g.append("div").attr("class", "table-wrap");
    const table = wrap.append("table");
    table.append("thead").append("tr").selectAll("th")
      .data(["School", "Course or slot", "Sem.", "Cr.", "Confidence", "Status", "Rationale"])
      .join("th").attr("class", (d) => (d === "Sem." || d === "Cr." ? "num" : null)).text((d) => d);
    const tr = table.append("tbody").selectAll("tr").data(lines).join("tr");

    // .each with function() so `this` is the <tr> element for each line.
    tr.each(function (l) {
      const row = d3.select(this);
      const r = l.row;
      row.append("td").text(r.school.short_name);
      const first = row.append("td");
      first.append("div").append("b").text(r.course_code || (r.options ? "Choice" : "Slot"));
      first.append("div").text(r.title);
      // Rows in the plan whose credits don't count toward the degree total (e.g. UIC's
      // ENGR 100) are flagged, since their credits would otherwise look odd.
      if (!r.counts_toward_total) first.append("div").attr("class", "muted").text("not counted in degree total");
      row.append("td").attr("class", "num").text(l.sems.length ? l.sems.join(", ") : "co-op");
      row.append("td").attr("class", "num").text(l.creditsMin === l.creditsMax ? l.creditsMin : `${l.creditsMin}–${l.creditsMax}`);
      const m = l.m;
      const conf = row.append("td").attr("class", "conf").text(m.match_confidence + (m.partial_match ? " (partial)" : ""));
      if (ROLE_TEXT[m.match_role]) conf.append("div").attr("class", "muted").text(ROLE_TEXT[m.match_role]);
      row.append("td").append("span").attr("class", `status ${m.match_status}`).text(m.match_status);

      // Rationale, plus a collapsible side-by-side comparison of the school's
      // description and the canonical description, for judging the match. A row with
      // several canonical courses names the others, so the split is visible here too.
      const last = row.append("td");
      last.append("div").text(m.match_rationale);
      const others = r.matches.filter((o) => o.canonical_id !== m.canonical_id).map((o) => o.canonical_id);
      if (others.length) last.append("div").attr("class", "muted").text(`Also matched to: ${others.join(", ")}`);
      const det = last.append("details").attr("class", "compare");
      det.append("summary").text("Compare descriptions");
      const grid = det.append("div").attr("class", "compare-grid");
      const sc = grid.append("div");
      const name = r.school.short_name;
      const h = sc.append("h4").text(r.description_source === "generic" ? `${name} slot ` : `${name} catalog`);
      if (r.description_source === "generic") appendGenericBadge(h);
      sc.append("p").text(r.description);
      if (r.options) sc.append("p").style("margin-top", "6px").text(`Options: ${r.options}`);
      if (r.prerequisites) sc.append("p").style("margin-top", "6px").text(`Prerequisites: ${r.prerequisites}`);
      const cd = grid.append("div");
      cd.append("h4").text("Canonical (written for this project)");
      cd.append("p").text(c.description);
    });
  }

  d3.select("#summary").text(`Showing ${shownLines} match${shownLines === 1 ? "" : "es"} ` +
    `across ${shownGroups} of ${canon.length} canonical courses.`);
}

// Entry point: load data, index the match lines by canonical_id, draw, and redraw on
// every filter change. "input" fires on each keystroke in the search box and on each
// change of a <select>.
loadAllSchools()
  .then(({ rows, canon, schools }) => {
    // One <option> per built school in the school filter.
    d3.select("#school").selectAll("option.s").data(schools).join("option")
      .attr("class", "s").attr("value", (s) => s.school_id).text((s) => s.short_name);
    // d3.group with a key function gives Map(canonical_id -> lines).
    const linesById = d3.group(matchLines(rows), (l) => l.m.canonical_id);
    render(canon, linesById);
    d3.select("#filters").on("input", () => render(canon, linesById));
  })
  .catch((err) => showLoadError("main", err));
