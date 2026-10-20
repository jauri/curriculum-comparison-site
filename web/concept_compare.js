// The concept alignment view: UC's required courses (left) next to one other school's
// (right), laid out by normalized semester as in the Alignment tab, joined by bands whose
// width is the share of a course's concepts found in the other course.
// Spec: specs/10-concept-alignment-view.md.
//
// Reads, through loadAllSchools() in common.js, schools.json and each school's
// required_courses.json; and data/processed/all_concept_tags.json and concepts.json,
// written by src/build_concepts.py. The shares are computed here in the browser from the
// tags, by the rule written in the spec ("Bands"), the way compare.js joins on
// canonical_id; the page adds no judgment of its own.
//
// All text from the data is inserted with D3's .text() (textContent), so nothing in the
// data is ever interpreted as HTML.

// Geometry, in pixels. Same node scale as the Alignment tab (compare.js), so the two tabs
// look alike and a course is the same height on both.
const PX_PER_CREDIT = 12;
const MIN_NODE_PX = 18;
const NODE_GAP = 2;
const BAND_PAD = 10;
const HEAD_H = 46;
const NODE_W = 230;
const BAR_W = 8; // the share bar on each node's inner edge
const MIN_LINK_W = 160;
const TWO_LINE_PX = 30;
const ORDER_PASSES = 6;
const MIN_BAND_PX = 1.5; // thinner bands are drawn this thick so they stay visible
const SPARSE_COURSES = 6; // warn when the other school has fewer tagged courses than this

// Page state that survives redraws. Only the CS area is on by default, since only CS
// courses are tagged (the spec's "Nodes"); every concept group is on.
// coop: whether co-op work terms are drawn in their place (the "Show co-op terms" toggle).
const state = { school: null, areas: new Set(["cs"]), groups: null, minShare: 0, pinnedId: null, coop: false };
let data = null; // { schools, canon, rows } from loadAllSchools()
let tagsByRow = null; // Map("<school_id>|<course_code>" -> [tag, ...])
let groups = null; // the concept groups, in concepts.csv order
let model = null; // the current layout, built by buildModel()

// Key for one row in tagsByRow: tags are per (school, course code), as in concept_tags.csv.
const rowKey = (r) => `${r.school.school_id}|${r.course_code}`;

// Percent text with at most one decimal, dropping a trailing ".0", so the even splits of
// the rule stay exact where they can: 0.125 -> "12.5%", 0.5 -> "50%", 1/3 -> "33.3%".
// The unary + turns toFixed's string back into a number, which drops the ".0".
function pct(x) {
  return `${+(x * 100).toFixed(1)}%`;
}

// The concepts of one row that count right now: its tags whose group is checked, one
// entry per concept (a row may have two tag lines for one concept; the first is kept for
// its evidence phrase). Returns Map(concept_id -> tag); empty for rows with no tags.
function conceptsOf(r) {
  const out = new Map();
  for (const t of tagsByRow.get(rowKey(r)) || []) {
    if (state.groups.has(t.group) && !out.has(t.concept_id)) out.set(t.concept_id, t);
  }
  return out;
}

// Why a row has no concepts to show, for its tooltip and the detail panel. The order
// follows the scope rule in specs/08-concepts.md (named CS course, official description).
function untaggedReason(r) {
  if (r.is_coop) return "a co-op work term, not a course";
  if (!r.course_code) return "a requirement slot, which has no fixed content";
  if (r.subject_area !== "cs") return "not a CS course (only CS courses are tagged)";
  if (r.description_source === "generic") return "its description is generic (written for this project), so it is not evidence";
  if (tagsByRow.has(rowKey(r))) return "all of its concepts are in unchecked groups";
  return "its description names no concept in the vocabulary";
}

// Node height for one row: proportional to credits, never below MIN_NODE_PX (as in
// compare.js). Co-op rows (0 credits) get the fixed COOP_NODE_PX.
function nodeHeight(r) {
  if (r.is_coop) return COOP_NODE_PX;
  return Math.max(MIN_NODE_PX, r.credits_max * PX_PER_CREDIT);
}

// Build the graph for UC vs one school.
//
// Nodes: one per placed row (co-op rows have no semester and are left out), each with
// its current concepts. Bands: one per pair of courses (u at UC, v at the other school)
// that share at least one concept. Shares follow the spec's rule:
//   - each concept is 1/|C(u)| of u;
//   - a concept of u found in k of the other school's courses is split evenly among them;
//   - share(u -> v) = sum over shared concepts c of 1 / (|C(u)| * k_other(c)),
// and the same the other way round for v. A course's shares plus its "unshared" part
// (concepts found nowhere on the other side) add up to 1.
//
// Shares are computed over ALL placed rows, before the subject filter, so hiding an area
// never changes a percentage (only CS rows have tags, so in practice this only matters
// when CS itself is unchecked). The filter and the slider then choose what is drawn.
//
// With the co-op toggle on, co-op rows are nodes too, in the co-op slots between
// semesters (termSlots in common.js). They have no tags, so no shares change.
function buildModel(ucRows, otherRows) {
  const { slots, slotOf } = termSlots(ucRows, otherRows, state.coop);
  const nodes = (rows, side) => rows
    .filter((r) => slotOf(r) !== null && slotOf(r) !== undefined)
    .map((r, i) => ({
      id: `${side}${i}`, side, row: r, sem: r.norm_semester, slot: slotOf(r), h: nodeHeight(r), area: areaOf(r),
      concepts: conceptsOf(r), allBands: [],
    }));
  let left = nodes(ucRows, "L");
  let right = nodes(otherRows, "R");

  // Map(concept_id -> nodes on one side that have it). Its .length is k in the rule above.
  const holders = (ns) => {
    const m = new Map();
    for (const n of ns) for (const c of n.concepts.keys()) {
      if (!m.has(c)) m.set(c, []);
      m.get(c).push(n);
    }
    return m;
  };
  const holdL = holders(left);
  const holdR = holders(right);

  // Group u's concepts by the right-side course they are found in, so each pair (u, v)
  // gets one band listing every concept they share.
  const allBands = [];
  for (const u of left) {
    const byPartner = new Map(); // v -> [concept_id, ...]
    for (const c of u.concepts.keys()) {
      for (const v of holdR.get(c) || []) {
        if (!byPartner.has(v)) byPartner.set(v, []);
        byPartner.get(v).push(c);
      }
    }
    for (const [v, shared] of byPartner) {
      const band = {
        id: `${u.id}-${v.id}`, source: u, target: v, shared,
        // d3.sum adds up the per-concept pieces; holdR/holdL give each concept's k.
        shareL: d3.sum(shared, (c) => 1 / (u.concepts.size * holdR.get(c).length)),
        shareR: d3.sum(shared, (c) => 1 / (v.concepts.size * holdL.get(c).length)),
      };
      allBands.push(band);
      u.allBands.push(band);
      v.allBands.push(band);
    }
  }
  // Unshared part of each tagged course: its concepts that no course on the other side has.
  for (const [ns, hold] of [[left, holdR], [right, holdL]]) {
    for (const n of ns) {
      n.missing = [...n.concepts.keys()].filter((c) => !hold.has(c));
      n.unshared = n.concepts.size ? n.missing.length / n.concepts.size : 0;
    }
  }

  // Apply the subject filter, then the minimum-share slider. A band is kept if both ends
  // are shown and its larger end reaches the threshold. n.bands drives drawing,
  // highlighting, and ordering; n.allBands keeps the full split for the share bar.
  // Co-op terms follow the co-op toggle only, not the subject filter.
  const shown = (n) => n.row.is_coop || state.areas.has(n.area.key);
  left = left.filter(shown);
  right = right.filter(shown);
  const bands = allBands.filter((b) => shown(b.source) && shown(b.target) &&
    Math.max(b.shareL, b.shareR) >= state.minShare);
  const bandSet = new Set(bands);
  for (const n of [...left, ...right]) n.bands = n.allBands.filter((b) => bandSet.has(b));

  // Slot bands, as in compare.js: band k is as tall as the taller side's stack, so
  // semester k lines up across the two sides; a co-op slot fits at least one co-op box.
  const stackHeight = (ns, k) => d3.sum(ns.filter((n) => n.slot === k), (n) => n.h + NODE_GAP);
  const bandH = slots.map((s, k) => Math.max(stackHeight(left, k), stackHeight(right, k),
    s.kind === "coop" ? COOP_NODE_PX : 0) + 2 * BAND_PAD);
  const bandTop = [0, ...d3.cumsum(bandH)].map((y) => y + HEAD_H);
  const groupsBySem = { L: d3.group(left, (n) => n.slot), R: d3.group(right, (n) => n.slot) };
  return { left, right, bands, slots, bandH, bandTop, groupsBySem, bySlot: groupsBySem, withCoop: state.coop,
    height: bandTop[slots.length] + 8, holdL, holdR };
}

// Stack each semester's nodes from the top of its band in their current order.
function placeNodes(m) {
  for (const side of ["L", "R"]) {
    for (const [k, ns] of m.groupsBySem[side]) {
      let y = m.bandTop[k] + BAND_PAD;
      for (const n of ns) { n.y = y; y += n.h + NODE_GAP; }
    }
  }
}

// Order nodes within each semester so that courses sharing concepts sit across from each
// other: the barycenter heuristic of compare.js, with each partner weighted by the band's
// share on the moving side, so a course is pulled hardest toward the course most of its
// concepts went to. Nodes without a band keep their place. Deterministic (stable sort).
function orderNodes(m) {
  const areaRank = new Map(AREAS.map((a, i) => [a.key, i]));
  for (const side of ["L", "R"]) {
    for (const ns of m.groupsBySem[side].values()) {
      ns.sort((a, b) => areaRank.get(a.area.key) - areaRank.get(b.area.key) ||
        a.row.canonical_ids.localeCompare(b.row.canonical_ids));
    }
  }
  placeNodes(m);

  const center = (n) => n.y + n.h / 2;
  let unchanged = 0;
  for (let pass = 0; pass < ORDER_PASSES && unchanged < 2; pass++) {
    const side = pass % 2 === 0 ? "R" : "L";
    let changed = false;
    for (const ns of m.groupsBySem[side].values()) {
      const key = new Map(ns.map((n) => {
        if (!n.bands.length) return [n, center(n)];
        // Weighted mean: sum(weight * partner center) / sum(weight).
        const w = (b) => (side === "L" ? b.shareL : b.shareR);
        const partner = (b) => (side === "L" ? b.target : b.source);
        return [n, d3.sum(n.bands, (b) => w(b) * center(partner(b))) / d3.sum(n.bands, w)];
      }));
      const before = ns.map((n) => n.id).join();
      ns.sort((a, b) => key.get(a) - key.get(b));
      if (ns.map((n) => n.id).join() !== before) changed = true;
    }
    placeNodes(m);
    unchanged = changed ? 0 : unchanged + 1;
  }
}

// Split each tagged node's share bar into segments: one per band (every band of the
// course, so the split is the same whatever the slider hides), stacked in the vertical
// order of the partner course to limit crossings, then the unshared segment last.
// Each segment is {band, y0, y1} in page coordinates; the band's end on this node uses
// that segment. Partners hidden by the subject filter go after the shown ones.
function placeSegments(m) {
  for (const n of [...m.left, ...m.right]) {
    const partner = (b) => (n.side === "L" ? b.target : b.source);
    const share = (b) => (n.side === "L" ? b.shareL : b.shareR);
    // Partner's center, or Infinity when the partner is not drawn (sorts last).
    const py = (b) => (partner(b).y === undefined || !state.areas.has(partner(b).area.key)
      ? Infinity : partner(b).y + partner(b).h / 2);
    const ordered = [...n.allBands].sort((a, b) => py(a) - py(b));
    let y = n.y;
    n.segments = ordered.map((b) => {
      const seg = { band: b, y0: y, y1: y + share(b) * n.h };
      y = seg.y1;
      return seg;
    });
    n.unsharedSeg = { y0: y, y1: n.y + n.h };
    for (const s of n.segments) {
      if (n.side === "L") s.band.endL = s; else s.band.endR = s;
    }
  }
}

// Build the SVG path of one band: a filled shape from the UC segment (x1, y0..y1) to the
// other school's segment (x2, y0..y1). Each long edge is a cubic Bézier with both control
// points at the horizontal midpoint, the same S-curve as compare.js's links. An end
// thinner than MIN_BAND_PX is widened around its center so the band stays visible.
function bandPath(b, x1, x2) {
  const widen = (s) => {
    const mid = (s.y0 + s.y1) / 2;
    const half = Math.max(MIN_BAND_PX, s.y1 - s.y0) / 2;
    return [mid - half, mid + half];
  };
  const [a0, a1] = widen(b.endL);
  const [c0, c1] = widen(b.endR);
  const xm = (x1 + x2) / 2;
  return `M${x1},${a0}C${xm},${a0} ${xm},${c0} ${x2},${c0}L${x2},${c1}C${xm},${c1} ${xm},${a1} ${x1},${a1}Z`;
}

// Draw the whole chart for the current school and settings, then the panel and tables.
function draw() {
  const ucRows = data.rows.filter((r) => r.school.school_id === "uc");
  const otherRows = data.rows.filter((r) => r.school.school_id === state.school);
  const other = data.schools.find((s) => s.school_id === state.school);
  model = buildModel(ucRows, otherRows);
  orderNodes(model);
  placeSegments(model);

  const wrap = document.querySelector(".chart-wrap");
  // Both sides always get a label gutter with the school's own terms (drawSlotBands).
  const leftGutter = COOP_LABEL_W;
  const rightGutter = COOP_LABEL_W;
  const width = Math.max(wrap.clientWidth, leftGutter + 2 * NODE_W + MIN_LINK_W + rightGutter);
  const xL = leftGutter;
  const xR = width - NODE_W - rightGutter;

  const svg = d3.select("#chart").attr("width", width).attr("height", model.height)
    .attr("viewBox", `0 0 ${width} ${model.height}`);
  svg.selectAll("*").remove();

  // Hatch pattern for the "not found at the other school" segments: diagonal lines on a
  // 4px tile. patternUnits="userSpaceOnUse" keeps the tile size in pixels, so every
  // segment gets the same density regardless of its height.
  svg.append("defs").append("pattern").attr("id", "hatch").attr("patternUnits", "userSpaceOnUse")
    .attr("width", 4).attr("height", 4).attr("patternTransform", "rotate(45)")
    .append("path").attr("d", "M0,0V4");

  const heads = [[xL, data.schools.find((s) => s.school_id === "uc")], [xR, other]];
  for (const [x, s] of heads) {
    svg.append("text").attr("class", "col-head").attr("x", x).attr("y", 18).text(s.short_name);
    fitSvgText(svg.append("text").attr("class", "col-sub").attr("x", x).attr("y", 34).node(),
      `${s.institution}, ${s.program}`, NODE_W);
  }

  // Semester (and co-op) bands: rules, labels, and empty co-op placeholders (common.js).
  drawSlotBands(svg, model, { width, xL, xR, nodeW: NODE_W, rowsL: ucRows, rowsR: otherRows });

  // Bands under the nodes. They start at the outer edge of each share bar.
  svg.append("g").selectAll("path").data(model.bands, (b) => b.id).join("path")
    .attr("class", "band").attr("d", (b) => bandPath(b, xL + NODE_W, xR))
    .on("mouseenter", (event, b) => { focus(b); showTooltipBand(event, b, other); renderDetail(b, other); })
    .on("mousemove", moveTooltip)
    .on("mouseleave", () => { hideTooltip(); focus(pinned()); renderDetail(pinned(), other); })
    .on("click", (event, b) => { event.stopPropagation(); togglePin(b); });

  const nodeSel = svg.append("g").selectAll("g").data([...model.left, ...model.right], (n) => n.id).join("g")
    // Co-op terms get their own style instead of the faded "not assessed" one.
    .attr("class", (n) => (n.row.is_coop ? "node coop"
      : ["node", n.row.course_code ? "" : "slot", n.concepts.size ? "" : "untagged"].join(" ")))
    .attr("transform", (n) => `translate(${n.side === "L" ? xL : xR},${n.y})`)
    .attr("tabindex", 0)
    .attr("role", "button")
    .attr("aria-label", (n) => `${n.row.school.short_name} ${rowLabel(n.row)}: ${n.row.title}, ${semText(n.row)}, ` +
      (n.concepts.size ? `${n.concepts.size} concepts, ${pct(1 - n.unshared)} found at the other school`
        : "not assessed"))
    .on("mouseenter", (event, n) => { focus(n); showTooltipNode(event, n, other); })
    .on("mousemove", moveTooltip)
    .on("mouseleave", () => { hideTooltip(); focus(pinned()); })
    .on("click", (event, n) => { event.stopPropagation(); togglePin(n); })
    .on("keydown", (event, n) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); togglePin(n); }
    });

  // The area stripe sits on each node's outer edge and the share bar on its inner edge
  // (facing the bands): right side of UC nodes, left side of the other school's.
  const barX = (n) => (n.side === "L" ? NODE_W - BAR_W : 0);
  const stripeX = (n) => (n.side === "L" ? 0 : NODE_W - 4);
  nodeSel.append("rect").attr("class", "box").attr("width", NODE_W).attr("height", (n) => n.h).attr("rx", 4);
  nodeSel.append("rect").attr("class", "stripe").attr("x", stripeX).attr("width", 4).attr("height", (n) => n.h)
    .attr("rx", 2).attr("fill", (n) => n.area.color);

  nodeSel.each(function (n) {
    const g = d3.select(this);
    const r = n.row;
    // Share bar segments, in node-local coordinates (subtract the node's top).
    if (n.concepts.size) {
      for (const s of n.segments) {
        g.append("rect").attr("class", "seg").attr("x", barX(n)).attr("y", s.y0 - n.y)
          .attr("width", BAR_W).attr("height", Math.max(0, s.y1 - s.y0));
      }
      const u = n.unsharedSeg;
      if (u.y1 - u.y0 > 0.01) {
        g.append("rect").attr("class", "seg-unshared").attr("x", barX(n)).attr("y", u.y0 - n.y)
          .attr("width", BAR_W).attr("height", u.y1 - u.y0);
      }
      g.append("rect").attr("class", "seg-frame").attr("x", barX(n)).attr("width", BAR_W).attr("height", n.h);
    }

    // Text, as in compare.js, inset from whichever edge holds the share bar or stripe.
    const generic = r.description_source === "generic";
    const x0 = n.side === "L" ? 10 : BAR_W + 6;
    const textW = NODE_W - BAR_W - 20 - (generic ? 50 : 0);
    const twoLines = n.h >= TWO_LINE_PX;
    const y1 = twoLines ? 13 : n.h / 2 + 4;
    const tail = n.concepts.size ? ` · ${pct(1 - n.unshared)} shared` : "";
    const first = r.course_code ? `${r.course_code}${tail}` : r.title;
    fitSvgText(g.append("text").attr("class", "code").attr("x", x0).attr("y", y1).node(), first, textW);
    if (generic) {
      g.append("text").attr("class", "generic").attr("x", n.side === "L" ? NODE_W - BAR_W - 6 : NODE_W - 10)
        .attr("y", y1).attr("text-anchor", "end").text("GENERIC");
    }
    if (twoLines) {
      const second = r.is_coop ? `${r.course_code ? `${r.title} · ` : "Work term · "}${origTermText(r)}`
        : r.course_code ? r.title : `${creditText(r)} cr, student chooses`;
      fitSvgText(g.append("text").attr("class", "title").attr("x", x0).attr("y", 27).node(), second, NODE_W - BAR_W - 20);
    }
  });

  svg.on("click", () => togglePin(null));
  if (!pinned()) state.pinnedId = null;
  focus(pinned());
  renderDetail(pinned(), other);
  renderSparse(other);
  renderTables(other);
}

// The pinned node or band in the current model, or null. Node ids look like "L3" and band
// ids like "L3-R5", so one id field covers both. A band hidden by the slider or a filter
// is no longer in the model, and draw() then unpins it.
function pinned() {
  if (!state.pinnedId || !model) return null;
  return [...model.left, ...model.right, ...model.bands].find((x) => x.id === state.pinnedId) || null;
}

// Highlight a node with its bands and partners, or a band with its two nodes; fade the
// rest. focus(null) clears it.
function focus(target) {
  const on = new Set();
  if (target && target.bands) {
    on.add(target.id);
    for (const b of target.bands) { on.add(b.id); on.add(b.source.id); on.add(b.target.id); }
  } else if (target) {
    on.add(target.id); on.add(target.source.id); on.add(target.target.id);
  }
  const svg = d3.select("#chart").classed("focusing", !!target);
  svg.selectAll(".node").classed("on", (n) => on.has(n.id)).classed("pinned", (n) => n.id === state.pinnedId);
  svg.selectAll(".band").classed("on", (b) => on.has(b.id)).classed("pinned", (b) => b.id === state.pinnedId);
}

// Pin or unpin a node or band (null unpins). Clicking the pinned one again, empty space,
// or Escape unpins it.
function togglePin(x) {
  state.pinnedId = x && x.id !== state.pinnedId ? x.id : null;
  const other = data.schools.find((s) => s.school_id === state.school);
  focus(pinned());
  renderDetail(pinned(), other);
}

// "2 of 9 concepts" for one end of a band: the count goes next to every percentage, since
// a course with few tags moves in big steps (spec, "Known problems" 3).
const ofText = (k, n) => `${k} of ${n} concept${n === 1 ? "" : "s"}`;

function showTooltipNode(event, n, other) {
  const r = n.row;
  const otherName = n.side === "L" ? other.short_name : "UC";
  const lines = [`${r.school.short_name} ${rowLabel(r)}`, r.course_code ? r.title : `${creditText(r)} cr requirement slot`,
    `${semText(r)} · ${creditText(r)} cr`];
  if (n.concepts.size) {
    const found = n.concepts.size - n.missing.length;
    lines.push(`${ofText(found, n.concepts.size)} found at ${otherName} (${pct(1 - n.unshared)})`);
    lines.push(`Shared with ${n.allBands.length} ${otherName} course${n.allBands.length === 1 ? "" : "s"}`);
  } else {
    lines.push(`Not assessed: ${untaggedReason(r)}`);
  }
  showTooltip(event, lines);
}

// A band's tooltip: the two courses and both shares. The shared concepts and the
// highlighted descriptions go in the side panel (renderBandDetail), which has more room.
function showTooltipBand(event, b, other) {
  const u = b.source;
  const v = b.target;
  showTooltip(event, [
    `UC ${rowLabel(u.row)} ↔ ${other.short_name} ${rowLabel(v.row)}`,
    `${pct(b.shareL)} of UC ${rowLabel(u.row)} · ${pct(b.shareR)} of ${other.short_name} ${rowLabel(v.row)}`,
    `${b.shared.length} shared concept${b.shared.length === 1 ? "" : "s"}: see the side panel; click to pin`,
  ]);
}

// The detail panel for a pinned node: facts, then every concept of the course with
// where its share went (or "not found"), then the description. A band (hovered or
// pinned) gets its own panel, renderBandDetail; a band is told apart by its .shared list.
function renderDetail(n, other) {
  const panel = d3.select("#detail");
  panel.selectAll("*").remove();
  if (!n) {
    panel.append("p").attr("class", "muted")
      .text("Click a course to see where each of its concepts went. Hover or click a band to see the concepts two courses share.");
    return;
  }
  if (n.shared) { renderBandDetail(panel, n, other); return; }
  const r = n.row;
  const otherName = n.side === "L" ? other.short_name : "UC";
  const h = panel.append("h3").text(`${r.school.short_name} ${rowLabel(r)}`);
  if (r.description_source === "generic") { h.append("span").text(" "); appendGenericBadge(h); }
  if (r.course_code) panel.append("p").text(r.title);
  const dl = panel.append("dl");
  const facts = [["Placement", semText(r)], ["Credits", creditText(r)], ["Area", n.area.label]];
  if (n.concepts.size) {
    facts.push(["Concepts", `${n.concepts.size} (in checked groups)`]);
    facts.push([`Found at ${otherName}`, `${ofText(n.concepts.size - n.missing.length, n.concepts.size)} (${pct(1 - n.unshared)})`]);
  }
  for (const [k, v] of facts) { dl.append("dt").text(k); dl.append("dd").text(v); }

  if (!n.concepts.size) {
    panel.append("p").attr("class", "muted").text(`Not assessed: ${untaggedReason(r)}.`);
  } else {
    panel.append("h4").text(`Where its concepts went (each is ${pct(1 / n.concepts.size)} of the course)`);
    const ul = panel.append("ul");
    const hold = n.side === "L" ? model.holdR : model.holdL;
    // Concepts found elsewhere first, then the unshared ones, each in name order.
    const entries = [...n.concepts.values()].sort((a, b) =>
      (hold.has(a.concept_id) ? 0 : 1) - (hold.has(b.concept_id) ? 0 : 1) || a.name.localeCompare(b.name));
    for (const t of entries) {
      const partners = hold.get(t.concept_id) || [];
      const li = ul.append("li");
      li.append("b").text(t.name);
      // All of the tag's evidence phrases, each quoted.
      li.append("span").text(` (${t.group}), ${t.evidence_phrases.map((ph) => `“${ph}”`).join(", ")}: `);
      li.append("span").text(partners.length
        ? `${partners.map((p) => rowLabel(p.row)).join(", ")}` +
          (partners.length > 1 ? `, ${pct(1 / (n.concepts.size * partners.length))} each` : "")
        : `not found at ${otherName}`);
    }
  }
  panel.append("h4").text(r.description_source === "generic"
    ? "Description (generic, written for this project)" : `Description (${r.school.short_name} catalog)`);
  panel.append("p").attr("class", "desc").text(r.description);
}

// The side panel for a band: both shares, the shared concepts (numbered), and both
// courses' titles and full descriptions with every evidence phrase of a shared concept
// highlighted and tagged with that concept's number, so each concept can be found in
// both texts.
function renderBandDetail(panel, b, other) {
  const ends = [[b.source, "UC", b.shareL, model.holdR], [b.target, other.short_name, b.shareR, model.holdL]];
  panel.append("h3").text(`UC ${rowLabel(b.source.row)} ↔ ${other.short_name} ${rowLabel(b.target.row)}`);
  const dl = panel.append("dl");
  for (const [n, name, share] of ends) {
    dl.append("dt").text(`${name} ${rowLabel(n.row)}`);
    dl.append("dd").text(`${pct(share)} of the course (${ofText(b.shared.length, n.concepts.size)})`);
  }

  // Shared concepts, numbered in name order; the numbers mark the highlights below.
  const shared = [...b.shared].sort((x, y) => b.source.concepts.get(x).name.localeCompare(b.source.concepts.get(y).name));
  const number = new Map(shared.map((c, i) => [c, i + 1]));
  panel.append("h4").text(`Shared concepts (${shared.length})`);
  const ul = panel.append("ul").attr("class", "shared-list");
  for (const c of shared) {
    const t = b.source.concepts.get(c);
    const li = ul.append("li");
    li.append("span").attr("class", "num").text(number.get(c));
    li.append("b").text(t.name);
    li.append("span").attr("class", "muted").text(` · ${t.group}`);
    // How each side's share of this concept was split (k courses on the other side).
    const kR = model.holdR.get(c).length;
    const kL = model.holdL.get(c).length;
    const split = [kR > 1 ? `UC's share split among ${kR} ${other.short_name} courses` : "",
      kL > 1 ? `${other.short_name}'s share split among ${kL} UC courses` : ""].filter(Boolean).join("; ");
    if (split) li.append("div").attr("class", "muted split").text(split);
  }

  // Each course's text with highlights. Evidence can come from the title or the
  // description (tag.evidence_field), so both are shown.
  for (const [n, name] of ends) {
    const r = n.row;
    panel.append("h4").text(`${name} ${rowLabel(r)} (${r.school.short_name} catalog)`);
    // Every evidence phrase of every tag line of this row for a shared concept, with
    // the concept's number. flatMap turns each tag into one mark per phrase.
    const marks = (tagsByRow.get(rowKey(r)) || []).filter((t) => number.has(t.concept_id))
      .flatMap((t) => t.evidence_phrases.map((phrase) =>
        ({ field: t.evidence_field, phrase, num: number.get(t.concept_id), name: t.name })));
    appendHighlighted(panel.append("p").attr("class", "desc title-line"), r.title, marks.filter((m) => m.field === "title"));
    appendHighlighted(panel.append("p").attr("class", "desc"), r.description, marks.filter((m) => m.field === "description"));
  }
}

// Append `text` to a D3 selection with each mark's phrase wrapped in <mark> and followed
// by its concept number. Matching ignores case and treats any run of whitespace as one
// space, the same normalization check_concepts.py uses for evidence. Text is added as
// text nodes (never innerHTML), so nothing in the data is read as HTML.
function appendHighlighted(sel, text, marks) {
  // Find every match: [start, end, mark]. RegExp special characters in the phrase are
  // escaped (the replace call), then each whitespace run becomes \s+.
  const hits = [];
  for (const m of marks) {
    const src = m.phrase.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
    // Whole words only (no letter or digit touching either end), so "sets" does not
    // light up inside "subsets"; the same rule as check_untagged.py.
    const re = new RegExp(`(?<![a-z0-9])${src}(?![a-z0-9])`, "gi"); // g: all matches, i: ignore case
    let found;
    while ((found = re.exec(text)) !== null) {
      hits.push([found.index, found.index + found[0].length, m]);
      if (found[0].length === 0) re.lastIndex++; // guard against an empty match looping forever
    }
  }
  // Earliest first (the longer one first when two start together). A phrase that
  // overlaps one already highlighted (e.g. "correctness" inside "program correctness")
  // isn't highlighted again; its concept number is added to that highlight instead, so
  // every shared concept still shows up in the text.
  hits.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
  let pos = 0;
  let last = null; // { mark, sup, nums } of the latest highlight
  for (const [start, end, m] of hits) {
    if (start < pos) {
      if (!last.nums.includes(m.num)) {
        last.nums.push(m.num);
        last.sup.text(last.nums.join(","));
        last.mark.attr("title", `${last.mark.attr("title")}; ${m.name}`);
      }
      continue;
    }
    sel.append("span").text(text.slice(pos, start));
    const mark = sel.append("mark").attr("title", m.name).text(text.slice(start, end));
    last = { mark, sup: sel.append("sup").attr("class", "num-sup").text(m.num), nums: [m.num] };
    pos = end;
  }
  sel.append("span").text(text.slice(pos));
}

// Count the other school's tagged courses (with any tag, whatever the group filter) and
// warn when there are few, since a thin view then means little evidence, not little
// overlap (spec, "Known problems" 2).
function taggedCount(schoolId) {
  return data.rows.filter((r) => r.school.school_id === schoolId && tagsByRow.has(rowKey(r))).length;
}
function renderSparse(other) {
  const n = taggedCount(other.school_id);
  d3.select("#sparse").classed("hidden", n >= SPARSE_COURSES)
    .text(`Only ${n} of ${other.short_name}'s required courses have concept tags (short or generic ` +
      "descriptions, or few CS courses in the plan). A thin view here means little evidence, not little overlap.");
}

// The two tables under the chart. "Shared concepts": one row per drawn band. "Not found":
// one row per shown tagged course with any unshared concept.
function renderTables(other) {
  const names = (ids, n) => ids.map((c) => n.concepts.get(c).name).join("; ");
  const course = (n) => `${rowLabel(n.row)} (sem ${n.sem})`;
  const bands = [...model.bands].sort((a, b) => a.source.sem - b.source.sem || a.target.sem - b.target.sem ||
    rowLabel(a.source.row).localeCompare(rowLabel(b.source.row)));
  const cols = [
    ["UC course", (b) => course(b.source)],
    [`${other.short_name} course`, (b) => course(b.target)],
    ["Shared concepts", (b) => names(b.shared, b.source)],
    ["Share of UC course", (b) => `${pct(b.shareL)} (${ofText(b.shared.length, b.source.concepts.size)})`],
    [`Share of ${other.short_name} course`, (b) => `${pct(b.shareR)} (${ofText(b.shared.length, b.target.concepts.size)})`],
  ];
  fillTable("#table", cols, bands);

  const rows = [...model.left, ...model.right].filter((n) => n.missing && n.missing.length);
  const cols2 = [
    ["School", (n) => n.row.school.short_name],
    ["Course", (n) => `${course(n)} ${n.row.title}`],
    ["Not found", (n) => `${pct(n.unshared)} (${ofText(n.missing.length, n.concepts.size)})`],
    ["Concepts not found at the other school", (n) => names(n.missing, n)],
  ];
  fillTable("#unshared", cols2, rows);
}

// Fill a <table> from column definitions [[heading, value function], ...] and data items.
function fillTable(sel, cols, items) {
  const table = d3.select(sel);
  table.selectAll("*").remove();
  table.append("thead").append("tr").selectAll("th").data(cols).join("th").text((c) => c[0]);
  table.append("tbody").selectAll("tr").data(items).join("tr")
    .selectAll("td").data((it) => cols.map((c) => c[1](it))).join("td").text((v) => v);
}

// Controls: school picker (with each school's tagged-course count), subject areas (CS
// only by default), concept groups with an "All" box, the minimum-share slider, and the
// legend. The chosen school is kept in the URL (?school=osu), as on the Alignment tab.
function setupControls() {
  const others = data.schools.filter((s) => s.school_id !== "uc");
  const fromUrl = new URLSearchParams(location.search).get("school");
  state.school = others.some((s) => s.school_id === fromUrl) ? fromUrl : others[0].school_id;
  d3.select("#school").selectAll("option").data(others).join("option")
    .attr("value", (s) => s.school_id)
    .text((s) => `${s.short_name} (${s.institution}) · ${taggedCount(s.school_id)} tagged courses`)
    .property("selected", (s) => s.school_id === state.school);
  d3.select("#school").on("change", (event) => {
    state.school = event.target.value;
    state.pinnedId = null; // node ids belong to one comparison
    writeViewUrl(state);
    draw();
  });

  // The co-op toggle (off by default, or from ?coop=1). Node ids depend on which rows
  // are drawn, so switching it unpins.
  state.coop = coopFromUrl();
  d3.select("#coop").property("checked", state.coop).on("change", (event) => {
    state.coop = event.target.checked;
    state.pinnedId = null;
    writeViewUrl(state);
    draw();
  });

  const boxes = d3.select("#area-filters").selectAll("label").data(AREAS).join("label").attr("class", "area");
  boxes.append("input").attr("type", "checkbox").property("checked", (a) => state.areas.has(a.key))
    .on("change", (event, a) => {
      if (event.target.checked) state.areas.add(a.key); else state.areas.delete(a.key);
      draw();
    });
  boxes.append("i").style("background", (a) => a.color);
  boxes.append("span").text((a) => a.label);

  // Concept groups. Turning one off removes its concepts from every course before the
  // shares are computed, so percentages are always over the concepts shown.
  const gbox = d3.select("#groups");
  const all = gbox.append("label").attr("class", "group-all");
  const allInput = all.append("input").attr("type", "checkbox").property("checked", true);
  all.append("span").text("All concept groups");
  const items = gbox.selectAll("label.g").data(groups).join("label").attr("class", "g");
  const inputs = items.append("input").attr("type", "checkbox").property("checked", true)
    .on("change", (event, g) => {
      if (event.target.checked) state.groups.add(g); else state.groups.delete(g);
      allInput.property("checked", state.groups.size === groups.length);
      draw();
    });
  items.append("span").text((g) => g);
  allInput.on("change", (event) => {
    state.groups = new Set(event.target.checked ? groups : []);
    inputs.property("checked", event.target.checked);
    draw();
  });

  // The slider is in whole percents; state.minShare is a fraction like the shares.
  d3.select("#min-share").on("input", (event) => {
    state.minShare = +event.target.value / 100;
    d3.select("#min-share-out").text(`${event.target.value}%`);
    draw();
  });

  const legend = d3.select("#legend");
  for (const [cls, text] of [["band-key", "Shared concepts (each end: share of that course)"],
    ["unshared-key", "Concepts not found at the other school"], ["untagged-key", "Not assessed (no concept tags)"],
    ["slot-key", "Requirement slot"]]) {
    const item = legend.append("span");
    item.append("i").attr("class", cls);
    item.append("span").text(text);
  }

  document.addEventListener("keydown", (event) => { if (event.key === "Escape") togglePin(null); });
  let timer = null;
  window.addEventListener("resize", () => { clearTimeout(timer); timer = setTimeout(draw, 150); });
}

// Entry point: load the schools' tables, the tags, and the vocabulary, then draw.
Promise.all([loadAllSchools(), d3.json(DATA_DIR + "all_concept_tags.json"), d3.json(DATA_DIR + "concepts.json")])
  .then(([loaded, tags, concepts]) => {
    data = loaded;
    // d3.group(...) -> Map(key -> tags of that row).
    tagsByRow = d3.group(tags, (t) => `${t.school_id}|${t.course_code}`);
    groups = [...new Set(concepts.map((c) => c.group))]; // concepts.csv order, no repeats
    state.groups = new Set(groups);
    // Tags are still proposed until the step 17 review: say so on the page.
    const nProposed = tags.filter((t) => t.tag_status === "proposed").length;
    if (nProposed) {
      d3.select("#proposed-note").text(`All counts include proposed tags (${nProposed} of ${tags.length} not yet reviewed).`);
    }
    setupControls();
    draw();
  })
  .catch((err) => showLoadError("main", err));
