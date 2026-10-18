// The concept tag review page (step 17, specs/08-concepts.md step B).
//
// Reads data/processed/concepts_preview.json (written by src/preview_concepts.py, which
// copies each school's data/reference/<id>/concept_tags.csv onto its rows) and
// schools.json. Read-only, like the other review pages: tags are approved or rejected
// by editing the CSV, because a static page can't write files and reference data must
// never be overwritten silently.
// All text from the data is inserted with D3's .text() (textContent), never as HTML.

// Escape characters that have a meaning in regular expressions, so an evidence phrase
// like "C++" or "(GUIs)" is matched literally. "$&" in the replacement is the matched
// character, so each special character gets a backslash in front of it.
function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Find every place a tag's evidence occurs in `text`: case-insensitive, and any run of
// whitespace in the phrase matches any run in the text, the same rule check_concepts.py
// uses (it lowercases and collapses whitespace). Returns [start, end) index pairs.
function spans(text, phrase) {
  const re = new RegExp(escapeRegex(phrase.trim()).replace(/\s+/g, "\\s+"), "gi"); // g: all, i: any case
  return [...text.matchAll(re)].map((m) => [m.index, m.index + m[0].length]);
}

// Append `text` to a D3 selection with each tag's evidence wrapped in <mark>. Phrases of
// different tags can overlap ("dynamic memory" inside "dynamic memory allocation"), so
// the text is cut at every span boundary and each piece records which concepts cover
// it (data-cids), letting a hovered tag light up exactly its own phrase.
function appendHighlighted(sel, text, tags) {
  const marks = []; // {start, end, cid}
  for (const t of tags) for (const [s, e] of spans(text, t.evidence)) marks.push({ start: s, end: e, cid: t.concept_id });
  // Every position where some highlight starts or ends, plus the text's ends, in order.
  const cuts = [...new Set([0, text.length, ...marks.flatMap((m) => [m.start, m.end])])].sort((a, b) => a - b);
  for (let i = 0; i < cuts.length - 1; i++) {
    const [a, b] = [cuts[i], cuts[i + 1]];
    const cids = marks.filter((m) => m.start <= a && m.end >= b).map((m) => m.cid);
    const piece = text.slice(a, b);
    if (cids.length) sel.append("mark").attr("data-cids", cids.join(" ")).text(piece);
    else sel.append("span").text(piece);
  }
}

// True if a row's notes say the school's catalog text may be cut off (set by the
// description parsers); a concept may then be missing only because the text is.
function isTruncated(row) {
  return /cut off/i.test(row.notes || "");
}

// Read the filter controls into one object. Empty values mean "no filter".
function currentFilters() {
  return {
    school: document.getElementById("school").value,
    conf: document.getElementById("conf").value,
    q: document.getElementById("q").value.trim().toLowerCase(),
  };
}

// True if a tag passes the confidence filter and, when there is a search, matches it
// (the course's own code and title count too, so searching "CS 2028C" shows its tags).
function tagPasses(t, row, f, conceptById) {
  if (f.conf === "ml" && t.tag_confidence === "high") return false;
  if (f.conf === "low" && t.tag_confidence !== "low") return false;
  if (f.q) {
    const c = conceptById.get(t.concept_id) || {};
    const hay = [t.concept_id, c.name, c.group, t.evidence, t.notes, row.course_code, row.title].join(" ").toLowerCase();
    if (!hay.includes(f.q)) return false;
  }
  return true;
}

// Toggle the "active" class on the marks of one concept inside a course card. A mark
// may cover several concepts, so data-cids is a space-separated list; ~= in a CSS
// attribute selector matches one word of such a list.
function setActive(card, cid, on) {
  card.selectAll(`mark[data-cids~="${cid}"]`).classed("active", on);
}

// Redraw the page for the current filters: one card per in-scope course of the chosen
// school, in plan order. With a confidence filter or search active, only courses with a
// passing tag are shown (and only those tags), so the page becomes a review queue.
function render(rows, conceptById, schoolName) {
  const f = currentFilters();
  const root = d3.select("#courses");
  root.selectAll("*").remove();
  const schoolRows = rows.filter((r) => r.school_id === f.school);
  const filtering = f.conf || f.q;
  let nShown = 0;

  for (const row of schoolRows) {
    const real = row.tags.filter((t) => t.concept_id); // "no concept" lines have an empty id
    const shown = real.filter((t) => tagPasses(t, row, f, conceptById));
    if (filtering && !shown.length) continue;
    nShown += shown.length;

    const card = root.append("section").attr("class", "course");
    const h = card.append("h2");
    // Highlight evidence taken from the title in the heading itself.
    appendHighlighted(h.append("span"), `${row.course_code}: ${row.title}`, real.filter((t) => t.evidence_field === "title"));
    h.append("span").attr("class", "muted").text(` · sem. ${row.norm_semester}`);
    if (isTruncated(row)) card.append("div").attr("class", "flag").text("Catalog text may be cut off at the source.");
    appendHighlighted(card.append("p").attr("class", "desc"), row.description, real.filter((t) => t.evidence_field === "description"));

    if (!real.length) {
      const why = row.tags.length ? row.tags[0].notes : "Not tagged yet.";
      card.append("div").attr("class", "none").text(`No concept: ${why}`);
      continue;
    }
    const table = card.append("div").attr("class", "table-wrap").append("table");
    table.append("thead").append("tr").selectAll("th")
      .data(["Concept", "Group", "Evidence", "Confidence", "Status", "Note"]).join("th")
      .attr("class", (d) => (d === "Group" || d === "Note" ? "hide-narrow" : null))
      .text((d) => d);
    // .each with function() so `this` is the <tr> of each tag.
    table.append("tbody").selectAll("tr").data(shown).join("tr").attr("class", "tag").each(function (t) {
      const tr = d3.select(this);
      const c = conceptById.get(t.concept_id) || { name: t.concept_id, group: "" };
      const first = tr.append("td");
      first.append("div").append("b").text(c.name);
      first.append("code").text(t.concept_id);
      tr.append("td").attr("class", "hide-narrow").text(c.group);
      tr.append("td").attr("class", "ev").text(`"${t.evidence}"${t.evidence_field === "title" ? " (title)" : ""}`);
      tr.append("td").append("span").attr("class", `conf-${t.tag_confidence}`).text(t.tag_confidence);
      tr.append("td").text(t.tag_status);
      tr.append("td").attr("class", "hide-narrow note").text(t.notes);
    })
      .on("mouseenter", (event, t) => setActive(card, t.concept_id, true))
      .on("mouseleave", (event, t) => setActive(card, t.concept_id, false));
  }

  // Counts for the whole school (not just what the filters show), by confidence and status.
  const all = schoolRows.flatMap((r) => r.tags.filter((t) => t.concept_id));
  const count = (key, v) => all.filter((t) => t[key] === v).length;
  const untagged = schoolRows.filter((r) => !r.tags.length).length;
  d3.select("#summary").text(
    `${schoolName.get(f.school)}: ${schoolRows.length} in-scope courses, ${all.length} tags ` +
    `(high ${count("tag_confidence", "high")}, medium ${count("tag_confidence", "medium")}, low ${count("tag_confidence", "low")}; ` +
    `proposed ${count("tag_status", "proposed")}, approved ${count("tag_status", "approved")}, rejected ${count("tag_status", "rejected")})` +
    (untagged ? `; ${untagged} courses not tagged yet` : "") +
    (filtering ? `. Showing ${nShown} tags.` : "."));
}

// Entry point: load the preview and the registry, fill the school menu (registry order,
// UC first), remember the last school in the URL hash (#osu) so a reload keeps it, draw,
// and redraw on every filter change.
Promise.all([d3.json(DATA_DIR + "concepts_preview.json"), d3.json(DATA_DIR + "schools.json")])
  .then(([preview, schools]) => {
    const conceptById = new Map(preview.concepts.map((c) => [c.concept_id, c]));
    const schoolName = new Map(schools.map((s) => [s.school_id, s.short_name]));
    const sel = d3.select("#school");
    sel.selectAll("option").data(schools).join("option")
      .attr("value", (s) => s.school_id).text((s) => s.short_name);
    const fromHash = location.hash.slice(1); // drop the leading "#"
    if (schoolName.has(fromHash)) sel.property("value", fromHash);
    const draw = () => {
      history.replaceState(null, "", `#${sel.property("value")}`); // update the hash without a new history entry
      render(preview.rows, conceptById, schoolName);
    };
    draw();
    d3.select("#filters").on("input", draw);
  })
  .catch((err) => showLoadError("main", err));
