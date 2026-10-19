// The alignment view: UC's required courses (left) next to one other school's (right),
// laid out by normalized semester, with a line between two courses that map to the
// same canonical course (any of their matches; a row may match several since step 13).
// Spec: specs/06-alignment-view.md.
//
// Reads data/processed/schools.json, each school's <id>/required_courses.json, and
// canonical_courses.json through loadAllSchools() in common.js. Links are a join on
// canonical_id done here in the browser; the page adds no similarity judgment of its own.
//
// Drawing is plain SVG with D3. All text from the data is inserted with D3's .text()
// (textContent), so nothing in the data is ever interpreted as HTML.

// Geometry, in pixels. Node height is credits x PX_PER_CREDIT, with a floor so 0- and
// 1-credit courses (e.g. UIC's CS 499) still fit one line of text.
const PX_PER_CREDIT = 12;
const MIN_NODE_PX = 18;
const NODE_GAP = 2; // the 2px surface gap between adjacent boxes
const BAND_PAD = 10; // empty space at the top and bottom of each semester band
const HEAD_H = 46; // room for the two column headings
const LABEL_W = 96; // left gutter for the semester labels
const NODE_W = 230;
const MIN_LINK_W = 150; // narrowest middle area for the link curves
const RIGHT_PAD = 8;
const TWO_LINE_PX = 30; // nodes at least this tall get a second text line
const ORDER_PASSES = 6; // barycenter passes (see orderNodes)

// Page state that survives redraws: the chosen school, the checked subject areas, and
// the pinned node's id (a string, so it can be found again after a resize redraw).
const state = { school: null, areas: new Set(AREAS.map((a) => a.key)), pinnedId: null };
let data = null; // { schools, canon, rows } once loaded
let canonById = null;
let model = null; // the current layout, built by buildModel()

// Node height for one row: proportional to credits (the top of a range, as in the plan
// view), never below MIN_NODE_PX.
function nodeHeight(r) {
  return Math.max(MIN_NODE_PX, r.credits_max * PX_PER_CREDIT);
}

// Build the graph for UC vs one school: one node per placed row (co-op rows have no
// semester and are left out), one link per pair of rows sharing a canonical course
// (rows that share several get one link listing them all, see makeLink), and the
// height and top of each semester band. A band is as tall as the taller of the two
// schools' stacks for that semester, so semester k lines up on both sides.
//
// The subject filter is applied here: links are found among ALL rows first, then only
// rows in checked areas are laid out, and only links between two shown rows are kept.
// So the view closes up around the chosen areas, and a course whose only counterpart
// is in a hidden area still counts as matched (n.allLinks) rather than looking unmatched.
function buildModel(ucRows, otherRows) {
  // map with an index gives each node a stable id like "L3" or "R12".
  const nodes = (rows, side) => rows
    .filter((r) => r.norm_semester !== null)
    .map((r, i) => ({ id: `${side}${i}`, side, row: r, sem: r.norm_semester, h: nodeHeight(r), area: areaOf(r), allLinks: [] }));
  let left = nodes(ucRows, "L");
  let right = nodes(otherRows, "R");

  // Map(canonical_id -> right nodes matched to it), so each left node finds its
  // partners in one lookup per match. A right node with several matches is listed under
  // each. Many-to-many is kept as is (e.g. UC's four first-year engineering courses
  // each link to OSU's two).
  const rightByCanon = new Map();
  for (const v of right) {
    for (const m of v.row.matches) {
      if (!rightByCanon.has(m.canonical_id)) rightByCanon.set(m.canonical_id, []);
      rightByCanon.get(m.canonical_id).push(v);
    }
  }
  const allLinks = [];
  for (const u of left) {
    // A Set of partners, so two rows sharing two concepts still get only one link.
    const partners = new Set(u.row.matches.flatMap((m) => rightByCanon.get(m.canonical_id) || []));
    for (const v of partners) {
      const link = makeLink(u, v);
      allLinks.push(link);
      u.allLinks.push(link);
      v.allLinks.push(link);
    }
  }

  // Keep the rows in checked areas, and the links between two kept rows. n.links (the
  // shown links) drives layout and highlighting; n.allLinks drives "unmatched".
  const shown = (n) => state.areas.has(n.area.key);
  left = left.filter(shown);
  right = right.filter(shown);
  const links = allLinks.filter((l) => shown(l.source) && shown(l.target));
  for (const n of [...left, ...right]) n.links = n.allLinks.filter((l) => links.includes(l));

  const sems = d3.range(1, 9); // [1, 2, ..., 8]
  const stackHeight = (ns, k) => d3.sum(ns.filter((n) => n.sem === k), (n) => n.h + NODE_GAP);
  const bandH = sems.map((k) => Math.max(stackHeight(left, k), stackHeight(right, k)) + 2 * BAND_PAD);
  // d3.cumsum gives running totals; prepending 0 turns them into each band's top offset.
  const bandTop = [0, ...d3.cumsum(bandH)].map((y) => y + HEAD_H);

  // Each side's nodes grouped by semester. These arrays hold the within-band order
  // that orderNodes() rearranges.
  const bands = { L: d3.group(left, (n) => n.sem), R: d3.group(right, (n) => n.sem) };
  return { left, right, links, sems, bandH, bandTop, bands, height: bandTop[8] + 8 };
}

// One link between a UC node u and another school's node v. `shared` lists every
// canonical course the two rows have in common, with each side's match for it. Styles
// (06-alignment-view.md):
// - partial: dashed, if either end's match for a shared concept is partial;
// - possible: dotted, if every shared concept is a one_of match on at least one end,
//   i.e. a student at that school may take a different option instead;
// - group: an all_of_group match on either end (options all taken, in either order);
//   drawn like a full link, and the tooltip names the group's semesters.
function makeLink(u, v) {
  const vById = new Map(v.row.matches.map((m) => [m.canonical_id, m]));
  const shared = u.row.matches.filter((m) => vById.has(m.canonical_id))
    .map((m) => ({ id: m.canonical_id, u: m, v: vById.get(m.canonical_id) }));
  const ends = shared.flatMap((s) => [s.u, s.v]);
  return {
    id: `${u.id}-${v.id}`, source: u, target: v, shared,
    partial: ends.some((m) => m.partial_match),
    possible: shared.every((s) => s.u.match_role === "one_of" || s.v.match_role === "one_of"),
    group: ends.some((m) => m.match_role === "all_of_group"),
  };
}

// Stack each band's nodes from the top of the band in their current order, setting
// each node's y (its top edge).
function placeNodes(m) {
  for (const side of ["L", "R"]) {
    for (const [k, ns] of m.bands[side]) {
      let y = m.bandTop[k - 1] + BAND_PAD;
      for (const n of ns) {
        n.y = y;
        y += n.h + NODE_GAP;
      }
    }
  }
}

// Order nodes within each semester band so linked courses sit across from each other.
// This is the barycenter heuristic for two-layer graphs: repeatedly sort one side's
// bands by the average y of each node's partners on the other side, then the other
// side's, re-stacking after each pass. Nodes never leave their band. Nodes without a
// link keep their current position as their sort key, so they stay roughly in place.
// Array.prototype.sort is stable, so ties keep their order and the result is the same
// on every run.
function orderNodes(m) {
  const areaRank = new Map(AREAS.map((a, i) => [a.key, i]));
  for (const side of ["L", "R"]) {
    for (const ns of m.bands[side].values()) {
      // Starting order: subject area (palette order), then the row's canonical ids.
      ns.sort((a, b) => areaRank.get(a.area.key) - areaRank.get(b.area.key) ||
        a.row.canonical_ids.localeCompare(b.row.canonical_ids));
    }
  }
  placeNodes(m);

  const center = (n) => n.y + n.h / 2;
  let unchanged = 0;
  for (let pass = 0; pass < ORDER_PASSES && unchanged < 2; pass++) {
    const side = pass % 2 === 0 ? "R" : "L"; // the right side moves first, toward UC's order
    let changed = false;
    for (const ns of m.bands[side].values()) {
      const key = new Map(ns.map((n) => {
        const partners = n.links.map((l) => (side === "L" ? l.target : l.source));
        return [n, partners.length ? d3.mean(partners, center) : center(n)];
      }));
      const before = ns.map((n) => n.id).join();
      ns.sort((a, b) => key.get(a) - key.get(b));
      if (ns.map((n) => n.id).join() !== before) changed = true;
    }
    placeNodes(m);
    unchanged = changed ? 0 : unchanged + 1; // stop once neither side changes
  }
}

// The semesters of a row's all_of_group group (rows of its school sharing its
// choice_group), e.g. [4, 5] for Berkeley's ELENG 66 / ELENG 64. Empty for other rows.
function groupSems(r) {
  if (!r.choice_group) return [];
  return data.rows.filter((x) => x.school.school_id === r.school.school_id && x.choice_group === r.choice_group)
    .map((x) => x.norm_semester).sort((a, b) => a - b);
}

// "ELENG 66 or ELENG 64: one in each of semesters 4 and 5, in either order" for a
// grouped row, else "".
function groupText(r) {
  const sems = groupSems(r);
  return sems.length ? `${r.options.replaceAll("; ", " or ")}: one in each of semesters ${sems.join(" and ")}, in either order` : "";
}

// Draw the whole chart for the current school: bands, links, and nodes. Called on load,
// when the school changes, and (debounced) when the window is resized.
function draw() {
  const ucRows = data.rows.filter((r) => r.school.school_id === "uc");
  const otherRows = data.rows.filter((r) => r.school.school_id === state.school);
  const other = data.schools.find((s) => s.school_id === state.school);
  model = buildModel(ucRows, otherRows);
  orderNodes(model);

  // Width follows the container, but never so narrow that the links get squeezed; the
  // wrapper scrolls sideways on a phone instead.
  const wrap = document.querySelector(".chart-wrap");
  const width = Math.max(wrap.clientWidth, LABEL_W + 2 * NODE_W + MIN_LINK_W + RIGHT_PAD);
  const xL = LABEL_W;
  const xR = width - NODE_W - RIGHT_PAD;

  const svg = d3.select("#chart").attr("width", width).attr("height", model.height)
    .attr("viewBox", `0 0 ${width} ${model.height}`);
  svg.selectAll("*").remove();

  // Column headings: school short name, then the institution and program in small type.
  const heads = [[xL, data.schools.find((s) => s.school_id === "uc")], [xR, other]];
  for (const [x, s] of heads) {
    svg.append("text").attr("class", "col-head").attr("x", x).attr("y", 18).text(s.short_name);
    const sub = svg.append("text").attr("class", "col-sub").attr("x", x).attr("y", 34).node();
    fitSvgText(sub, `${s.institution}, ${s.program}`, NODE_W);
  }

  // Semester bands: a rule at the top of each band and a two-line label in the gutter.
  const bandG = svg.append("g");
  model.sems.forEach((k, i) => {
    const y = model.bandTop[i];
    bandG.append("line").attr("class", "band-rule").attr("x1", 0).attr("x2", width).attr("y1", y).attr("y2", y);
    const t = bandG.append("text").attr("class", "band-label").attr("x", 8).attr("y", y + 18);
    t.append("tspan").attr("class", "sem").text(`Semester ${k}`);
    // Year and Fall/Spring follow from k by the normalization rule (03-processing.md).
    t.append("tspan").attr("x", 8).attr("dy", 15).text(`Year ${Math.ceil(k / 2)} ${k % 2 ? "Fall" : "Spring"}`);
  });

  // Links first, so the nodes are drawn on top of them. A cubic Bézier from the right
  // edge of the UC node to the left edge of the other node, with both control points at
  // the horizontal midpoint, makes a smooth S-curve.
  const path = (l) => {
    const x1 = xL + NODE_W;
    const y1 = l.source.y + l.source.h / 2;
    const x2 = xR;
    const y2 = l.target.y + l.target.h / 2;
    const mid = (x1 + x2) / 2;
    return `M${x1},${y1}C${mid},${y1} ${mid},${y2} ${x2},${y2}`;
  };
  const linkG = svg.append("g");
  // Each link gets a visible line and a wide transparent twin for easier hovering.
  const linkSel = linkG.selectAll("g").data(model.links, (l) => l.id).join("g").attr("class", "link-g");
  linkSel.append("path").attr("class", (l) => ["link", l.partial ? "partial" : "", l.possible ? "possible" : ""].join(" "))
    .attr("d", path).attr("stroke", (l) => l.source.area.color);
  linkSel.append("path").attr("class", "link-hit").attr("d", path)
    .on("mouseenter", (event, l) => { focus(l); showTooltipLink(event, l, other); })
    .on("mousemove", moveTooltip)
    .on("mouseleave", () => { hideTooltip(); focus(pinnedNode()); });

  // Nodes: one <g> per row, positioned with a translate so its parts use local coordinates.
  const nodeSel = svg.append("g").selectAll("g").data([...model.left, ...model.right], (n) => n.id).join("g")
    .attr("class", (n) => ["node", n.row.course_code ? "" : "slot", n.allLinks.length ? "" : "unmatched"].join(" "))
    .attr("transform", (n) => `translate(${n.side === "L" ? xL : xR},${n.y})`)
    .attr("tabindex", 0) // focusable with Tab
    .attr("role", "button")
    .attr("aria-label", (n) => `${n.row.school.short_name} ${rowLabel(n.row)}: ${n.row.title}, ${semText(n.row)}, ` +
      `${creditText(n.row)} credits, ${n.allLinks.length} counterpart${n.allLinks.length === 1 ? "" : "s"}`)
    .on("mouseenter", (event, n) => { focus(n); showTooltipNode(event, n, other); })
    .on("mousemove", moveTooltip)
    .on("mouseleave", () => { hideTooltip(); focus(pinnedNode()); })
    .on("click", (event, n) => { event.stopPropagation(); togglePin(n); })
    .on("keydown", (event, n) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); togglePin(n); }
    });

  nodeSel.append("rect").attr("class", "box").attr("width", NODE_W).attr("height", (n) => n.h).attr("rx", 4);
  nodeSel.append("rect").attr("class", "stripe").attr("width", 4).attr("height", (n) => n.h).attr("rx", 2)
    .attr("fill", (n) => n.area.color);

  // Text inside each node. Two lines when the box is tall enough (code + credits, then
  // the title); otherwise one line with the code (or slot title). Slots get a GENERIC
  // tag at the right end of the first line, as in the plan view.
  nodeSel.each(function (n) {
    const g = d3.select(this);
    const r = n.row;
    const generic = r.description_source === "generic";
    const textW = NODE_W - 14 - (generic ? 50 : 0);
    const twoLines = n.h >= TWO_LINE_PX;
    const y1 = twoLines ? 13 : n.h / 2 + 4; // +4 roughly centers 12px text on its baseline
    const first = r.course_code ? `${r.course_code} · ${creditText(r)} cr` : `${r.title}`;
    fitSvgText(g.append("text").attr("class", "code").attr("x", 10).attr("y", y1).node(), first, textW);
    if (generic) g.append("text").attr("class", "generic").attr("x", NODE_W - 6).attr("y", y1).attr("text-anchor", "end").text("GENERIC");
    if (twoLines) {
      const second = r.course_code ? r.title : `${creditText(r)} cr, student chooses`;
      fitSvgText(g.append("text").attr("class", "title").attr("x", 10).attr("y", 27).node(), second, NODE_W - 14);
    }
  });

  // Clicking empty chart space unpins.
  svg.on("click", () => togglePin(null));

  // A pinned node in an area that was just unchecked is gone from the model: unpin it.
  if (!pinnedNode()) state.pinnedId = null;
  focus(pinnedNode());
  renderDetail(pinnedNode(), other);
  renderUnmatched(other);
  renderTable(other);
}

// The pinned node object in the current model, or null.
function pinnedNode() {
  if (!state.pinnedId || !model) return null;
  return [...model.left, ...model.right].find((n) => n.id === state.pinnedId) || null;
}

// Highlight a node (with its partners and links) or a link (with its two nodes), and
// fade everything else. focus(null) clears the highlight. Classes do the visual work
// (see "Highlighting" in compare.html).
function focus(target) {
  const on = new Set();
  if (target && target.links) { // a node
    on.add(target.id);
    for (const l of target.links) { on.add(l.id); on.add(l.source.id); on.add(l.target.id); }
  } else if (target) { // a link
    on.add(target.id); on.add(target.source.id); on.add(target.target.id);
  }
  const svg = d3.select("#chart").classed("focusing", !!target);
  svg.selectAll(".node").classed("on", (n) => on.has(n.id)).classed("pinned", (n) => n.id === state.pinnedId);
  svg.selectAll(".link").classed("on", (l) => on.has(l.id));
}

// Pin or unpin a node. Clicking the pinned node again (or empty space, or Escape)
// unpins it.
function togglePin(n) {
  state.pinnedId = n && n.id !== state.pinnedId ? n.id : null;
  const other = data.schools.find((s) => s.school_id === state.school);
  focus(pinnedNode());
  renderDetail(pinnedNode(), other);
}

function showTooltipNode(event, n, other) {
  const r = n.row;
  const otherName = n.side === "L" ? other.short_name : "UC";
  const k = n.allLinks.length;
  showTooltip(event, [
    `${r.school.short_name} ${rowLabel(r)}`,
    r.course_code ? r.title : `${creditText(r)} cr requirement slot`,
    `${semText(r)} · ${creditText(r)} cr${r.counts_toward_total ? "" : " (not counted in degree total)"}`,
    k ? `${k} counterpart${k === 1 ? "" : "s"} at ${otherName}` : `No counterpart at ${otherName}`,
  ], [{ heading: r.description_source === "generic" ? "Description" : `Description (${r.school.short_name} catalog)`, row: r }]);
}
function showTooltipLink(event, l, other) {
  const names = l.shared.map((s) => (canonById.get(s.id) || { name: s.id }).name);
  const shift = l.target.sem - l.source.sem;
  const lines = [
    names.join(" + "),
    `UC ${rowLabel(l.source.row)} (sem ${l.source.sem}) ↔ ${other.short_name} ${rowLabel(l.target.row)} (sem ${l.target.sem})`,
    shift === 0 ? "Same semester" : `${other.short_name} is ${Math.abs(shift)} semester${Math.abs(shift) === 1 ? "" : "s"} ${shift > 0 ? "later" : "earlier"}`,
    (l.partial ? "Partial match" : "Full match") + (l.possible ? "; possible (a choice: the student may take another option)" : ""),
  ];
  // Timing groups: say which semesters the grouped courses fall in.
  for (const n of [l.source, l.target]) {
    const g = groupText(n.row);
    if (g) lines.push(`${n.row.school.short_name}: ${g}`);
  }
  showTooltip(event, lines, [
    { heading: `UC ${rowLabel(l.source.row)}`, row: l.source.row },
    { heading: `${other.short_name} ${rowLabel(l.target.row)}`, row: l.target.row },
  ]);
}

// Fill the side panel for the pinned node, or show the hint when nothing is pinned.
function renderDetail(n, other) {
  const panel = d3.select("#detail");
  panel.selectAll("*").remove();
  if (!n) {
    panel.append("p").attr("class", "muted")
      .text("Click a course to pin it and see its description, canonical course, and counterparts.");
    return;
  }
  const r = n.row;
  const h = panel.append("h3").text(`${r.school.short_name} ${rowLabel(r)}`);
  if (r.description_source === "generic") { h.append("span").text(" "); appendGenericBadge(h); }
  if (r.course_code) panel.append("p").text(r.title);

  const facts = [
    ["Placement", semText(r)],
    ["Credits", creditText(r) + (r.counts_toward_total ? "" : " (not counted in degree total)")],
    ["Area", n.area.label],
  ];
  // One "Canonical" line per match (a row may match several canonical courses).
  for (const m of r.matches) facts.push(["Canonical", matchText(m, canonById)]);
  if (r.options) facts.push(["Options", r.options]);
  if (groupText(r)) facts.push(["Timing", groupText(r)]);
  const dl = panel.append("dl");
  for (const [k, v] of facts) { dl.append("dt").text(k); dl.append("dd").text(v); }
  for (const m of r.matches) {
    if (!m.match_rationale) continue;
    const who = r.matches.length > 1 ? ` (${m.canonical_id})` : "";
    panel.append("p").attr("class", "desc").text(`Why${who}: ${m.match_rationale}`);
  }

  // Counterparts on the other side, with how many semesters earlier or later they are.
  const otherName = n.side === "L" ? other.short_name : "UC";
  // All counterparts are listed, including any in a subject area that is filtered out.
  panel.append("h4").text(`Counterparts at ${otherName}`);
  if (!n.allLinks.length) {
    panel.append("p").attr("class", "muted").text(`None: no ${otherName} row maps to this canonical course.`);
  } else {
    const ul = panel.append("ul");
    for (const l of n.allLinks) {
      const p = n.side === "L" ? l.target : l.source;
      const shift = p.sem - n.sem;
      const when = shift === 0 ? "same semester" : `${Math.abs(shift)} ${shift > 0 ? "later" : "earlier"}`;
      const hidden = state.areas.has(p.area.key) ? "" : ", hidden by the filter";
      // Name the shared concept(s) when a row has more than one, so it's clear which one links.
      const via = r.matches.length > 1 || p.row.matches.length > 1 ? `, via ${l.shared.map((s) => s.id).join(" + ")}` : "";
      ul.append("li").text(`${rowLabel(p.row)}${p.row.course_code ? ` ${p.row.title}` : ""}: semester ${p.sem} (${when})` +
        (l.partial ? ", partial" : "") + (l.possible ? ", possible" : "") + via + hidden);
    }
  }

  panel.append("h4").text(r.description_source === "generic"
    ? "Description (generic, written for this project)"
    : `Description (${r.school.short_name} catalog)`);
  panel.append("p").attr("class", "desc").text(r.description);
  for (const m of r.matches) {
    const canon = canonById.get(m.canonical_id);
    if (!canon) continue;
    panel.append("h4").text(`Canonical description: ${canon.name} (written for this project)`);
    panel.append("p").attr("class", "desc").text(canon.description);
  }
}

// List the shown courses that have no counterpart, for each side.
function renderUnmatched(other) {
  const box = d3.select("#unmatched");
  box.selectAll("*").remove();
  const sides = [["UC", other.short_name, model.left], [other.short_name, "UC", model.right]];
  for (const [mine, theirs, ns] of sides) {
    const list = ns.filter((n) => !n.allLinks.length);
    box.append("p").text(`${mine} courses with no ${theirs} counterpart (${list.length}): ` +
      (list.length ? list.map((n) => `${rowLabel(n.row)}${n.row.course_code ? ` ${n.row.title}` : ""}`).join("; ") : "none") + ".");
  }
}

// The accessible companion table: one row per canonical course shown at either school,
// with each side's rows and semesters and the difference in first semester. The model
// holds only rows in checked areas, so the table follows the filter. A school row with
// several canonical courses appears under each; "possible" marks a one_of match.
function renderTable(other) {
  // Map(canonical_id -> [{n, m}]) for one side: every (node, match) pair.
  const byCanon = (ns) => d3.group(ns.flatMap((n) => n.row.matches.map((m) => ({ n, m, sem: n.sem }))), (e) => e.m.canonical_id);
  const left = byCanon(model.left);
  const right = byCanon(model.right);
  const ids = [...new Set([...left.keys(), ...right.keys()])];
  const firstSem = (ns) => (ns ? d3.min(ns, (n) => n.sem) : null);
  // Sort by UC's first semester, then the other school's (canonicals missing at UC last).
  ids.sort((a, b) => (firstSem(left.get(a)) ?? 99) - (firstSem(left.get(b)) ?? 99) ||
    (firstSem(right.get(a)) ?? 99) - (firstSem(right.get(b)) ?? 99));

  const rowsText = (es) => (es ? es.map((e) => `${rowLabel(e.n.row)} (sem ${e.sem}${e.m.match_role === "one_of" ? ", possible" : ""})`).join(", ") : "—");
  const diff = (id) => {
    const a = firstSem(left.get(id));
    const b = firstSem(right.get(id));
    if (a === null) return `${other.short_name} only`;
    if (b === null) return "UC only";
    return b === a ? "same" : `${b > a ? "+" : "−"}${Math.abs(b - a)} (${b > a ? "later" : "earlier"})`;
  };
  const cols = [
    ["Canonical course", (id) => (canonById.get(id) || { name: id }).name],
    ["UC", (id) => rowsText(left.get(id))],
    [other.short_name, (id) => rowsText(right.get(id))],
    [`${other.short_name} vs UC (first semester)`, diff],
  ];
  const table = d3.select("#table");
  table.selectAll("*").remove();
  table.append("thead").append("tr").selectAll("th").data(cols).join("th").text((c) => c[0]);
  table.append("tbody").selectAll("tr").data(ids).join("tr")
    .selectAll("td").data((id) => cols.map((c) => c[1](id))).join("td").text((v) => v);
}

// Build the controls: the school picker (every built school except UC) and one checkbox
// per subject area, colored like the plan view. The chosen school is kept in the URL
// (?school=osu) so a view can be shared or bookmarked.
function setupControls() {
  const others = data.schools.filter((s) => s.school_id !== "uc");
  const fromUrl = new URLSearchParams(location.search).get("school");
  state.school = others.some((s) => s.school_id === fromUrl) ? fromUrl : others[0].school_id;

  d3.select("#school").selectAll("option").data(others).join("option")
    .attr("value", (s) => s.school_id).text((s) => `${s.short_name} (${s.institution})`)
    .property("selected", (s) => s.school_id === state.school);
  d3.select("#school").on("change", (event) => {
    state.school = event.target.value;
    state.pinnedId = null; // node ids belong to one comparison
    history.replaceState(null, "", `?school=${state.school}`);
    draw();
  });

  const boxes = d3.select("#area-filters").selectAll("label").data(AREAS).join("label").attr("class", "area");
  boxes.append("input").attr("type", "checkbox").property("checked", true)
    .on("change", (event, a) => {
      if (event.target.checked) state.areas.add(a.key); else state.areas.delete(a.key);
      draw(); // re-lay out around the checked areas
    });
  boxes.append("i").style("background", (a) => a.color);
  boxes.append("span").text((a) => a.label);

  // Legend for the encodings that aren't color: slot boxes, link styles, faded boxes.
  const legend = d3.select("#legend");
  const keys = [["slot-key", "Requirement slot (student chooses)"], ["link-key", "Same canonical course"],
    ["partial-key", "Partial match"], ["possible-key", "Possible (one option of a choice)"],
    ["unmatched-key", "No counterpart at the other school"]];
  for (const [cls, text] of keys) {
    const item = legend.append("span");
    item.append("i").attr("class", cls);
    item.append("span").text(text);
  }

  // Escape unpins. The resize handler waits until resizing pauses (150 ms), then redraws.
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") togglePin(null); });
  let timer = null;
  window.addEventListener("resize", () => { clearTimeout(timer); timer = setTimeout(draw, 150); });
}

// Entry point: load every school's table, then build the controls and draw.
loadAllSchools()
  .then((loaded) => {
    data = loaded;
    canonById = new Map(data.canon.map((c) => [c.canonical_id, c]));
    setupControls();
    draw();
  })
  .catch((err) => showLoadError("main", err));
