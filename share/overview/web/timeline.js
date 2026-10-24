// The timeline view: one strip per canonical course, spanning the 8 normalized
// semesters, with one dot per school row matched to that course, placed at the row's
// semester. Dots in one semester stack; schools with no matched row sit in a "no
// course" bin on the right. UC is highlighted. Spec: specs/07-timeline-view.md.
//
// Reads data/processed/all_required_courses.json (step 14: every school's rows in one
// file, each with a school_id, a subject_area, and its nested matches),
// canonical_courses.json, and schools.json. Every dot is one (row, match) pair from
// those files; the page counts and places them but adds no judgment of its own.
//
// Drawing is plain SVG with D3. All text from the data is inserted with D3's .text()
// (textContent), so nothing in the data is ever interpreted as HTML.

// Geometry, in pixels. Each semester column holds up to DOTS_PER_ROW dots side by side;
// more dots wrap into another row above, so a crowded semester grows upward (a stack)
// without widening the column.
const LABEL_W = 290; // left gutter for the canonical course name and counts
const COL_W = 82; // one semester column; 22px wider than its 5 dots, so neighboring semesters stay apart
const DOTS_PER_ROW = 5;
const PITCH = 12; // center-to-center distance between neighboring dots
const DOT_R = 4.5; // dot radius: a 9px marker, above the 8px marker floor
const RING_R = DOT_R + 2.5; // UC's ring sits 2.5px outside its dot
const HIT_R = 6.5; // invisible hover target, a little bigger than the dot
const BIN_GAP = 22; // space between semester 8 and the "course not required" bin
const BIN_W = COL_W;
const FLAG_GAP = 14; // space between the bin and the UC flag column
const FLAG_W = 104; // the UC flag column at the far right; fits "▶ 2 sem late"
const HEAD_H = 40; // year and semester heads at the top of each chart
const AREA_HEAD_H = 42; // a heading row: an area (area sort) or a typical year (year sort)
const GROUP_RULE_Y = 10; // where the dark rule above a heading row sits, from the row's top
const MIN_STRIP_H = 42; // fits the two label lines even when a strip has one row of dots
const BASE_PAD = 6; // gap between the lowest dot row and the strip's baseline
const RIGHT_PAD = 10;
const SEM_TICK_H = 8; // the in-year semester divider: a short tick up from the baseline
const SHARE_W = 60; // the "share of other schools" bar in each strip's label
const SHARE_H = 7;

// UC flags (07-timeline-view.md, "UC flags"; the percentile rule is the user's choice).
// "Most" is at least two thirds, of the other 15 schools (missing) or of the other
// schools that require the course (early, late). A "UC only" flag (few others require
// it) was built and then removed at the user's request: it didn't read clearly.
// Timing is only judged when at least MIN_TIMING_N other schools require the course:
// with fewer, "earlier than most" rests on two or three schools.
const FLAG_MOST = 2 / 3;
const MIN_TIMING_N = 5;
// Glyph and short word for each flag. The arrows point along the time axis (left is
// earlier); none is a circle, since circles already mean match types.
const FLAG_GLYPHS = {
  early: { glyph: "◀", word: "early" },
  late: { glyph: "▶", word: "late" },
  missing: { glyph: "✕", word: "missing" },
};

// The three areas this view shows (07-timeline-view.md: lab science, writing, and
// general education are left out), in the order they are listed and sorted. Labels are
// shorter than the plan view's, to fit the toggle buttons.
const SHOWN_AREAS = [
  { key: "cs", label: "Computing (CS and IT)", button: "Computing" },
  { key: "eng", label: "Engineering & co-op prep", button: "Engineering & co-op" },
  { key: "math", label: "Math & statistics", button: "Math & statistics" },
];
const SHOWN_KEYS = new Set(SHOWN_AREAS.map((a) => a.key));

// Page state: which area buttons are on, the sort, the school followed by a click or
// the picker (pinned), and the school under the pointer (hover, which wins while it lasts).
// Only Computing is on at first (the user's choice); the other two buttons start off.
const state = { areas: new Set(["cs"]), sort: "year", pinned: null, hover: null };

let data = null; // { schools, canon, rows } once loaded
let strips = []; // one model per drawable canonical course (see buildStrips)

// Load the combined table (step 14) with the registry and canonical list. Each row gets
// its registry entry as `school`, and `idx`, its position in the file, which is the
// school's own row order and keeps the stacking order stable.
function loadTimelineData() {
  return Promise.all([
    d3.json(DATA_DIR + "schools.json"),
    d3.json(DATA_DIR + "canonical_courses.json"),
    d3.json(DATA_DIR + "all_required_courses.json"),
  ]).then(([schools, canon, rows]) => {
    const byId = new Map(schools.map((s) => [s.school_id, s]));
    return { schools, canon, rows: rows.map((r, idx) => ({ ...r, idx, school: byId.get(r.school_id) })) };
  });
}

// Build one strip model per canonical course: its dots (one per matched row with a
// semester), its area, the schools that have it, and the schools that don't. Rejected
// matches are skipped. Courses whose matched rows all lack a semester (co-op work
// terms) are returned separately so the page can name them instead of drawing them.
function buildStrips() {
  const schoolRank = new Map(data.schools.map((s, i) => [s.school_id, i])); // registry order; UC is first
  const built = [];
  const undrawn = [];
  for (const c of data.canon) {
    const matched = [];
    for (const row of data.rows) {
      // find(): the row's match for this canonical course, if any (a row matches each
      // canonical course at most once).
      const m = row.matches.find((x) => x.canonical_id === c.canonical_id && x.match_status !== "rejected");
      if (m) matched.push({ row, match: m });
    }
    if (!matched.length) continue;
    const dots = matched.filter((d) => d.row.norm_semester != null) // != null: neither null nor undefined
      .map((d) => ({ ...d, sem: d.row.norm_semester, schoolId: d.row.school_id }));
    const area = majorityArea(matched.map((d) => d.row.subject_area));
    if (!dots.length) { undrawn.push({ canon: c, area }); continue; }

    // Stack order: UC first, then registry order, then each school's own row order.
    dots.sort((a, b) => schoolRank.get(a.schoolId) - schoolRank.get(b.schoolId) || a.row.idx - b.row.idx);
    // A school "has" the course if any dot is a full match; a school whose only dots are
    // one_of matches "possibly" has it (students may pick another option). Neither kind
    // goes in the "course not required" bin.
    const definite = new Set(dots.filter((d) => d.match.match_role !== "one_of").map((d) => d.schoolId));
    const possible = new Set(dots.map((d) => d.schoolId).filter((id) => !definite.has(id)));
    const absent = data.schools.filter((s) => !definite.has(s.school_id) && !possible.has(s.school_id));
    // Typical semester: each school's earliest full-match semester (a possible dot may
    // never be taken), then the median across schools. Taking one value per school
    // keeps a school with several rows (e.g. four language semesters) from outweighing
    // the others. d3.rollup gives a Map school -> earliest semester.
    const earliest = d3.rollup(dots.filter((d) => d.match.match_role !== "one_of"), (v) => d3.min(v, (d) => d.sem),
      (d) => d.schoolId);
    const typicalSem = earliest.size ? d3.median([...earliest.values()]) : Infinity; // Infinity sorts last
    built.push({
      canon: c, area, dots, definite, possible, absent, typicalSem,
      flags: ucFlags(earliest, definite, possible),
      // Year of the typical semester: semesters 1-2 are year 1, 3-4 year 2, ... A median
      // between two semesters (e.g. 2.5) rounds up to the later one's year.
      typicalYear: Number.isFinite(typicalSem) ? Math.ceil(typicalSem / 2) : null,
      // d3.group: Map from semester -> that semester's dots, in stack order.
      bySem: d3.group(dots, (d) => d.sem),
    });
  }
  return { built, undrawn };
}

// UC's flags for one canonical course: where UC differs from most of the other schools.
// Takes the Map school -> earliest full-match semester and the definite / possible
// school sets from buildStrips. Returns a list (zero or one flag: missing excludes
// timing, and early excludes late) of { kind, text, why }, with `why` the evidence for
// the tooltip and table.
//   missing: UC doesn't require it (not even as an option), most others do.
//   early / late: UC's earliest semester is before / after most of the others'
//     earliest semesters (ties count as neither), when at least MIN_TIMING_N others
//     require it. The gap is UC's semester minus the others' median.
// A UC "possible" match is neither missing nor timed: students may never take it.
function ucFlags(earliest, definite, possible) {
  const n = data.schools.length - 1; // the other schools
  // Other schools' earliest semesters (UC left out, so UC isn't compared with itself).
  const others = [...earliest].filter(([id]) => id !== "uc").map(([, sem]) => sem);
  const flags = [];
  const has = definite.has("uc");
  if (!has && !possible.has("uc") && others.length >= FLAG_MOST * n) {
    flags.push({ kind: "missing", text: "", why: `UC doesn't require it; ${others.length} of ${n} other schools do` });
  }
  if (has && others.length >= MIN_TIMING_N) {
    const uc = earliest.get("uc");
    const before = others.filter((x) => x < uc).length; // schools that take it earlier than UC
    const after = others.filter((x) => x > uc).length;
    const mid = d3.median(others);
    const gap = uc - mid; // negative: UC is earlier than the typical school
    const sem = `${Math.abs(gap)} sem`;
    if (after >= FLAG_MOST * others.length) {
      flags.push({ kind: "early", text: ` ${sem}`, why: `UC: semester ${uc}; ${after} of ${others.length} other schools take it later (median semester ${mid})` });
    } else if (before >= FLAG_MOST * others.length) {
      flags.push({ kind: "late", text: ` ${sem}`, why: `UC: semester ${uc}; ${before} of ${others.length} other schools take it earlier (median semester ${mid})` });
    }
  }
  return flags;
}

// One line of flag text, e.g. "◀ 2 sem early" or "✕ missing". Written for a list so
// that a second kind of flag could be added (several flags show every glyph, then the
// last flag's words).
function flagText(flags) {
  if (!flags.length) return "";
  const glyphs = flags.map((f) => FLAG_GLYPHS[f.kind].glyph).join(" ");
  const last = flags[flags.length - 1];
  return `${glyphs}${last.text} ${FLAG_GLYPHS[last.kind].word}`;
}

// The most common area among a canonical course's rows; ties go to the earlier area in
// the palette order (AREAS in common.js), so the result never depends on row order.
function majorityArea(keys) {
  const counts = d3.rollup(keys, (v) => v.length, (k) => k); // Map area -> count
  const rank = (k) => AREAS.findIndex((a) => a.key === k);
  return [...counts.keys()].sort((a, b) => counts.get(b) - counts.get(a) || rank(a) - rank(b))[0];
}

// The page's two sections (07-timeline-view.md): every canonical course any school
// requires, then requirement slots (collapsed). Each test takes a strip model.
const SECTIONS = {
  course: (s) => s.canon.kind === "course",
  slot: (s) => s.canon.kind === "slot",
};

// The strips to draw for one section (a SECTIONS key), filtered by the area buttons and
// sorted by the chosen sort. Array.prototype.sort is stable, so ties keep the
// canonical list's order and the picture is the same on every load.
function visibleStrips(section) {
  const areaRank = new Map(SHOWN_AREAS.map((a, i) => [a.key, i]));
  const list = strips.filter((s) => SECTIONS[section](s) && SHOWN_KEYS.has(s.area) && state.areas.has(s.area));
  const byName = (a, b) => a.canon.name.localeCompare(b.canon.name);
  const sorts = {
    area: (a, b) => areaRank.get(a.area) - areaRank.get(b.area) || byName(a, b),
    common: (a, b) => b.definite.size - a.definite.size || b.possible.size - a.possible.size || byName(a, b),
    // Typical year (default): by typical year, then, within a year, by the percent of
    // other schools that require the course (the share bar's number, UC excluded),
    // highest first (the user's choice), then by "+N possible". ?? Infinity puts the
    // "Only as an option" courses (no typical year) last.
    year: (a, b) => (a.typicalYear ?? Infinity) - (b.typicalYear ?? Infinity)
      || otherShare(b).required - otherShare(a).required
      || otherShare(b).possible - otherShare(a).possible || byName(a, b),
  };
  return list.sort(sorts[state.sort]);
}

// Height of a strip: enough rows for its tallest stack (a semester or the "course not required"
// bin), never less than the two label lines need.
function stripHeight(s) {
  const tallest = Math.max(1, ...[...s.bySem.values()].map((v) => v.length), s.absent.length);
  const rows = Math.ceil(tallest / DOTS_PER_ROW);
  return Math.max(MIN_STRIP_H, rows * PITCH + BASE_PAD + 10);
}

// Center of the i-th dot in a cell whose left edge is x0, for a strip whose baseline is
// at y = base. Dots fill a row left to right, then the next row up.
function dotXY(i, x0, base) {
  const col = i % DOTS_PER_ROW;
  const row = Math.floor(i / DOTS_PER_ROW);
  const pad = (COL_W - DOTS_PER_ROW * PITCH) / 2; // center the dot grid in its column
  return [x0 + pad + col * PITCH + PITCH / 2, base - BASE_PAD - row * PITCH - PITCH / 2 + 2];
}

const semX = (k) => LABEL_W + (k - 1) * COL_W; // left edge of semester k's column
const BIN_X = LABEL_W + 8 * COL_W + BIN_GAP; // left edge of the "course not required" bin
const FLAG_X = BIN_X + BIN_W + FLAG_GAP; // left edge of the UC flag column (the user's choice: far right)
const CHART_W = FLAG_X + FLAG_W + RIGHT_PAD;

// Draw one section (a SECTIONS key) into its SVG: the heads, then each strip with its
// label, baseline, dots, and "course not required" bin. Called on load and whenever a control
// changes. In the area sort, an area heading row starts each area's run of strips.
function drawSection(svgId, section) {
  const svg = d3.select(svgId);
  svg.selectAll("*").remove();
  const list = visibleStrips(section);
  if (!list.length) {
    svg.attr("width", CHART_W).attr("height", 40);
    svg.append("text").attr("class", "strip-sub").attr("x", 12).attr("y", 24).text("Nothing to show: every area button is off.");
    return;
  }

  // Heads: "Year 1" over each pair of semester columns, the semester numbers under it,
  // and the bin's title.
  const head = svg.append("g");
  for (let y = 1; y <= 4; y++) {
    head.append("text").attr("class", "year-head").attr("x", semX(2 * y - 1) + COL_W).attr("y", 15)
      .attr("text-anchor", "middle").text(`Year ${y}`);
  }
  for (let k = 1; k <= 8; k++) {
    head.append("text").attr("class", "sem-head").attr("x", semX(k) + COL_W / 2).attr("y", 31)
      .attr("text-anchor", "middle").text(`Sem ${k}`);
  }
  // The bin's title is on two lines ("Course not" / "required"): one line is wider than
  // the column. Each <tspan> with x and dy starts a new line under the previous one.
  const binHead = head.append("text").attr("class", "year-head").attr("y", 15).attr("text-anchor", "middle");
  binHead.append("tspan").attr("x", BIN_X + BIN_W / 2).text("Course not");
  binHead.append("tspan").attr("x", BIN_X + BIN_W / 2).attr("dy", 14).text("required");
  // The UC flag column's title, on two lines like the bin's.
  const flagHead = head.append("text").attr("class", "year-head").attr("y", 15);
  flagHead.append("tspan").attr("x", FLAG_X + 6).text("UC vs. most");
  flagHead.append("tspan").attr("x", FLAG_X + 6).attr("dy", 14).text("other schools");

  let y = HEAD_H;
  let lastGroup = null;
  for (const s of list) {
    const group = groupHeading(s);
    if (group && group !== lastGroup) {
      // A darker full-width rule, then a larger heading under it, so each group (a typical
      // year, or an area) reads as its own section, not as one more strip (the user's choice).
      svg.append("line").attr("class", "group-rule").attr("x1", 0).attr("x2", CHART_W)
        .attr("y1", y + GROUP_RULE_Y).attr("y2", y + GROUP_RULE_Y);
      svg.append("text").attr("class", "area-head").attr("x", 12).attr("y", y + 34).text(group);
      y += AREA_HEAD_H;
      lastGroup = group;
    }
    const h = stripHeight(s);
    drawStrip(svg.append("g").attr("transform", `translate(0,${y})`), s, h);
    y += h;
  }
  svg.attr("width", CHART_W).attr("height", y + 8).attr("viewBox", `0 0 ${CHART_W} ${y + 8}`);
  applyFollow();
}

// The heading a strip falls under in the current sort: its area in the area sort, its
// typical year in the year sort, none in the "most common" sort.
function groupHeading(s) {
  if (state.sort === "area") return SHOWN_AREAS.find((a) => a.key === s.area).label;
  if (state.sort === "year") return s.typicalYear ? `Typically year ${s.typicalYear}` : "Only as an option";
  return null;
}

// Draw one strip at the origin of group g, h pixels tall.
function drawStrip(g, s, h) {
  const base = h - 4; // the strip's baseline, near its bottom edge
  // A faint rule between strips, faint year dividers, and the bin divider. There is no
  // separate baseline under the semesters (the user's choice, for a cleaner look): the
  // rule between strips, 4px below the dots' base, serves as each strip's floor, so the
  // vertical lines run down to it (y2 = h) and meet it.
  g.append("line").attr("class", "sem-tick").attr("x1", 0).attr("x2", CHART_W).attr("y1", h).attr("y2", h);
  for (let k = 3; k <= 7; k += 2) {
    g.append("line").attr("class", "sem-tick").attr("x1", semX(k)).attr("x2", semX(k)).attr("y1", 4).attr("y2", h);
  }
  // A short tick rising from the strip's floor between the two semesters of each year
  // (before semesters 2, 4, 6, 8), so the fall/spring boundary reads without another
  // full-height line through the stacks. SEM_TICK_H keeps it below the lowest dot row.
  for (let k = 2; k <= 8; k += 2) {
    g.append("line").attr("class", "sem-mid").attr("x1", semX(k)).attr("x2", semX(k))
      .attr("y1", base - SEM_TICK_H).attr("y2", h);
  }
  g.append("line").attr("class", "bin-rule").attr("x1", BIN_X - BIN_GAP / 2).attr("x2", BIN_X - BIN_GAP / 2)
    .attr("y1", 4).attr("y2", h);
  g.append("line").attr("class", "bin-rule").attr("x1", FLAG_X - FLAG_GAP / 2).attr("x2", FLAG_X - FLAG_GAP / 2)
    .attr("y1", 4).attr("y2", h); // the same dashed divider before the flag column

  // Label: the canonical course name (cut with "…" if too long) and a counts line that
  // ends with UC's placement, so UC's status reads without finding its dot.
  const name = g.append("text").attr("class", "strip-name").attr("x", 12).attr("y", 17);
  fitText(name.node(), s.canon.name, LABEL_W - 20);
  // UC's flag (if any) sits in its own column at the far right, on the name's line, so
  // flagged courses can be scanned down one edge. The <title> child is its hover text:
  // the evidence.
  if (s.flags.length) {
    const flag = g.append("text").attr("class", "uc-flag").attr("x", FLAG_X + 6).attr("y", 17)
      .text(flagText(s.flags));
    flag.append("title").text(s.flags.map((f) => f.why).join(". "));
  }
  // Second line: a small bar of how common the course is among the other schools, its
  // percent, and UC's placement.
  const share = otherShare(s);
  const bar = g.append("g").attr("class", "share").attr("transform", "translate(12,24)");
  bar.append("title").text(share.text); // hover text for the bar
  bar.append("rect").attr("class", "share-track").attr("width", SHARE_W).attr("height", SHARE_H).attr("rx", 2);
  // The "possible" part is drawn first, from the left edge to the end of required +
  // possible, and the required part on top of it, so each keeps its own rounded end.
  bar.append("rect").attr("class", "share-possible").attr("height", SHARE_H).attr("rx", 2)
    .attr("width", SHARE_W * (share.required + share.possible) / share.n);
  bar.append("rect").attr("class", "share-required").attr("height", SHARE_H).attr("rx", 2)
    .attr("width", SHARE_W * share.required / share.n);
  const sub = g.append("text").attr("class", "strip-sub").attr("x", 12 + SHARE_W + 6).attr("y", 32);
  sub.append("tspan").attr("class", "pct").text(`${share.pct}%`);
  sub.append("tspan").text(`${share.possible ? ` +${share.possible} possible` : ""} · `);
  const uc = ucStatus(s);
  sub.append("tspan").attr("class", uc.none ? "uc-none" : "uc").text(uc.text);

  // Dots, semester by semester, then the bin.
  for (const [sem, dots] of s.bySem) {
    dots.forEach((d, i) => drawDot(g, d, dotXY(i, semX(sem), base), s));
  }
  s.absent.forEach((school, i) => {
    const [cx, cy] = dotXY(i, BIN_X, base); // the bin is one column wide, like a semester
    drawDot(g, { absent: true, school, schoolId: school.school_id }, [cx, cy], s);
  });
}

// How common a course is among the comparison schools, UC excluded (the user's choice:
// UC's own status is shown separately). `required`: schools with a full match;
// `possible`: schools whose only match is one option of a choice. The percent counts
// required schools only, rounded to a whole number.
function otherShare(s) {
  const n = data.schools.length - 1; // every school but UC
  const required = [...s.definite].filter((id) => id !== "uc").length;
  const possible = [...s.possible].filter((id) => id !== "uc").length;
  const pct = Math.round((100 * required) / n);
  const text = `${required} of ${n} other schools require it (${pct}%)` + (possible ? `; ${possible} more as one option of a choice` : "");
  return { n, required, possible, pct, text };
}

// "UC: semester 3", "UC: semesters 1, 2", "UC: possible, semester 5", or "UC: not required".
function ucStatus(s) {
  const mine = s.dots.filter((d) => d.schoolId === "uc");
  if (!mine.length) return { none: true, text: "UC: not required" };
  const sems = [...new Set(mine.map((d) => d.sem))].sort((a, b) => a - b);
  const word = sems.length > 1 ? "semesters" : "semester";
  return { none: false, text: `UC: ${s.possible.has("uc") ? "possible, " : ""}${word} ${sems.join(", ")}` };
}

// Draw one dot: an invisible hit circle, the mark (filled, half-filled, or hollow),
// and a ring that only UC's dots (and a followed school's) show. Hover shows the
// tooltip and lights up the school's dots everywhere; click or Enter pins that school.
function drawDot(g, d, [cx, cy], s) {
  const role = d.match?.match_role; // ?. : undefined for "course not required" dots, which have no match
  const dot = g.append("g").attr("class", "dot").attr("transform", `translate(${cx},${cy})`)
    .attr("tabindex", 0).attr("data-school", d.schoolId)
    .classed("uc", d.schoolId === "uc").classed("absent", !!d.absent)
    .classed("possible", role === "one_of").classed("partial", !!d.match?.partial_match && role !== "one_of")
    .attr("aria-label", dotLabel(d, s));
  dot.append("circle").attr("class", "hit").attr("r", HIT_R);
  dot.append("circle").attr("class", "ring").attr("r", RING_R);
  dot.append("circle").attr("class", "mark").attr("r", DOT_R);
  if (dot.classed("partial")) {
    // Left half of the disc, filled: an SVG arc from the top point to the bottom point
    // (sweep-flag 0 goes counterclockwise, i.e. around the left side), closed by Z.
    dot.append("path").attr("class", "half").attr("d", `M0,${-DOT_R} A${DOT_R},${DOT_R} 0 0 0 0,${DOT_R} Z`);
  }
  dot.on("mouseenter", (event) => { state.hover = d.schoolId; applyFollow(); showTooltip(event, ...tipContent(d, s)); })
    .on("mousemove", moveTooltip)
    .on("mouseleave", () => { state.hover = null; applyFollow(); hideTooltip(); })
    .on("click", () => togglePin(d.schoolId))
    .on("keydown", (event) => { if (event.key === "Enter") togglePin(d.schoolId); })
    // Keyboard focus shows the same tooltip, placed by the dot's position on screen.
    .on("focus", (event) => {
      const box = event.currentTarget.getBoundingClientRect();
      showTooltip({ clientX: box.right, clientY: box.bottom }, ...tipContent(d, s));
    })
    .on("blur", hideTooltip);
}

// Short text for screen readers, e.g. "UC, CS 2028C, semester 3, Data Structures".
function dotLabel(d, s) {
  if (d.absent) return `${d.school.short_name}: course not required, ${s.canon.name}`;
  return `${d.row.school.short_name}, ${d.row.course_code || d.row.title}, semester ${d.sem}, ${s.canon.name}`;
}

// The tooltip's lines and description block for a dot: [lines, descs] in the form
// showTooltip() (common.js) takes.
function tipContent(d, s) {
  if (d.absent) {
    return [[`${d.school.short_name} · ${d.school.institution}`, `No required course matched to ${s.canon.name}.`], []];
  }
  const r = d.row;
  const lines = [
    `${r.school.short_name} · ${r.course_code ? `${r.course_code} ` : ""}${r.title}`,
    `Semester ${r.norm_semester} · Year ${r.norm_year} ${r.norm_term} · ${creditText(r)} credits`,
    r.school.institution,
  ];
  if (d.match.match_role === "one_of") lines.push(`Possible: one of ${r.options.replaceAll("; ", ", ")}`);
  else if (d.match.partial_match) lines.push(`Partial match to ${s.canon.name}`);
  const group = groupText(r);
  if (group) lines.push(group);
  if (r.counts_toward_total === false) lines.push("Not counted toward the degree total");
  return [lines, [{ heading: "Description", row: r }]];
}

// "ELENG 66 or ELENG 64: one in each of semesters 4 and 5, in either order" for a row
// of an all_of_group group (rows of its school sharing its choice_group), else "".
// Same wording as the alignment view.
function groupText(r) {
  if (!r.choice_group) return "";
  const sems = data.rows.filter((x) => x.school_id === r.school_id && x.choice_group === r.choice_group)
    .map((x) => x.norm_semester).sort((a, b) => a - b);
  return `${r.options.replaceAll("; ", " or ")}: one in each of semesters ${sems.join(" and ")}, in either order`;
}

// Shorten an SVG <text> element's content with "…" until it fits maxWidth, measuring
// the rendered width (so the element must already be in the page). Binary search over
// the length keeps it fast. Same approach as the alignment view's fitText.
function fitText(textEl, str, maxWidth) {
  textEl.textContent = str;
  if (textEl.getComputedTextLength() <= maxWidth) return;
  let lo = 0;
  let hi = str.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    textEl.textContent = str.slice(0, mid) + "…";
    if (textEl.getComputedTextLength() <= maxWidth) lo = mid; else hi = mid - 1;
  }
  textEl.textContent = str.slice(0, lo) + "…";
  d3.select(textEl).append("title").text(str); // full name on hover
}

// Light up the followed school's dots in both charts and fade the rest. The hovered
// school wins over the pinned one while the pointer is on a dot.
function applyFollow() {
  const id = state.hover ?? state.pinned; // ?? : the pinned school when nothing is hovered
  d3.selectAll("#chart-courses, #chart-slots").classed("following", id != null);
  d3.selectAll(".dot").classed("on", function () { return this.dataset.school === id; });
}

// Pin a school (or unpin it if it is already pinned; null unpins), and keep the
// "Follow school" picker in step.
function togglePin(id) {
  state.pinned = id === state.pinned ? null : id;
  d3.select("#follow").property("value", state.pinned ?? "");
  applyFollow();
}

// The companion table: one row per strip shown (courses, then slots), with each
// school's semesters. "(possible)" marks one_of rows. Follows the sort and the buttons.
function renderTable() {
  const table = d3.select("#table");
  table.selectAll("*").remove();
  const head = ["Canonical course", "Area", "Other schools requiring it", "UC", "UC flag", "Other schools (semester)", "Course not required"];
  table.append("thead").append("tr").selectAll("th").data(head).join("th").text((t) => t)
    .classed("num", (t) => t === "Other schools requiring it");
  const body = table.append("tbody");
  for (const s of [...visibleStrips("course"), ...visibleStrips("slot")]) {
    // d3.group by school, in stack order, then "OSU 3, 4" per school.
    const perSchool = [...d3.group(s.dots, (d) => d.schoolId)].map(([id, ds]) => {
      const sems = [...new Set(ds.map((d) => d.sem))].join(", ");
      return { id, text: `${ds[0].row.school.short_name} ${sems}${s.possible.has(id) ? " (possible)" : ""}` };
    });
    const uc = perSchool.find((p) => p.id === "uc");
    const tr = body.append("tr");
    tr.append("td").text(s.canon.name + (s.canon.kind === "slot" ? " (slot)" : ""));
    tr.append("td").text(SHOWN_AREAS.find((a) => a.key === s.area).button);
    const share = otherShare(s);
    tr.append("td").attr("class", "num")
      .text(`${share.required} of ${share.n} (${share.pct}%)${share.possible ? ` + ${share.possible} possible` : ""}`);
    tr.append("td").text(uc ? uc.text.replace(/^UC /, "") : "not required"); // ^UC : drop the school name at the start
    // The flag spelled out, with its evidence, since a glyph alone means little in a table.
    tr.append("td").text(s.flags.map((f) => `${FLAG_GLYPHS[f.kind].glyph} ${FLAG_GLYPHS[f.kind].word}${f.text ? ` (${f.text.trim()})` : ""}: ${f.why}`).join("; "));
    tr.append("td").text(perSchool.filter((p) => p.id !== "uc").map((p) => p.text).join("; "));
    tr.append("td").text(s.absent.map((x) => x.short_name).join(", "));
  }
}

// Redraw everything that depends on the controls.
function draw() {
  drawSection("#chart-courses", "course");
  drawSection("#chart-slots", "slot");
  renderTable();
}

// Controls: the area toggle buttons, the sort, the school picker, and the legend.
function setupControls() {
  const toggles = d3.select("#area-toggles").selectAll("label").data(SHOWN_AREAS).join("label").attr("class", "toggle");
  // Each button starts checked only if its area is on in the initial state.
  toggles.append("input").attr("type", "checkbox").property("checked", (a) => state.areas.has(a.key))
    .on("change", (event, a) => {
      if (event.target.checked) state.areas.add(a.key); else state.areas.delete(a.key);
      draw();
    });
  toggles.append("span").text((a) => a.button);

  d3.select("#sort").on("change", (event) => { state.sort = event.target.value; draw(); });

  const follow = d3.select("#follow");
  follow.append("option").attr("value", "").text("None");
  follow.selectAll("option.school").data(data.schools).join("option").attr("class", "school")
    .attr("value", (s) => s.school_id).text((s) => `${s.short_name} (${s.institution})`);
  follow.on("change", (event) => { state.pinned = event.target.value || null; applyFollow(); });

  // Legend swatches are tiny SVGs built with the same classes as the chart's dots.
  const legend = d3.select("#legend");
  const keys = [
    [{ uc: true }, "UC"], [{}, "Other school"], [{ partial: true }, "Partial match"],
    [{ possible: true }, "Possible (one option of a choice)"], [{ absent: true }, "Course not required (other school)"],
    [{ absent: true, uc: true }, "Course not required (UC)"],
  ];
  for (const [cls, text] of keys) {
    const item = legend.append("span");
    const g = item.append("svg").attr("width", 18).attr("height", 18).attr("aria-hidden", true)
      .append("g").attr("class", "dot").attr("transform", "translate(9,9)")
      .classed("uc", !!cls.uc).classed("partial", !!cls.partial).classed("possible", !!cls.possible)
      .classed("absent", !!cls.absent);
    g.append("circle").attr("class", "ring").attr("r", RING_R);
    g.append("circle").attr("class", "mark").attr("r", DOT_R);
    if (cls.partial) g.append("path").attr("class", "half").attr("d", `M0,${-DOT_R} A${DOT_R},${DOT_R} 0 0 0 0,${DOT_R} Z`);
    item.append("span").text(text);
  }
  // The UC flag glyphs, as text (they are text in the chart too).
  const flagKeys = [
    ["early", "UC earlier than most"], ["late", "UC later than most"],
    ["missing", "UC doesn't require it; most do"]
  ];
  for (const [kind, text] of flagKeys) {
    const item = legend.append("span");
    item.append("span").attr("class", "uc-flag").attr("aria-hidden", true).text(FLAG_GLYPHS[kind].glyph);
    item.append("span").text(text);
  }

  // Escape unpins; a click on empty chart space unpins too (dot clicks don't reach it
  // because they are handled on the dot, and stopPropagation is not needed: the target
  // check below ignores them).
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") togglePin(null); });
  d3.selectAll("#chart-courses, #chart-slots").on("click", (event) => {
    if (!event.target.closest(".dot")) togglePin(null);
  });
}

// Entry point: load the data, build the strips, then the controls, and draw.
loadTimelineData()
  .then((loaded) => {
    data = loaded;
    const { built, undrawn } = buildStrips();
    strips = built;
    const names = undrawn.filter((u) => SHOWN_KEYS.has(u.area)).map((u) => u.canon.name);
    if (names.length) d3.select("#undrawn").text(` (${names.join(", ")})`);
    setupControls();
    draw();
  })
  .catch((err) => showLoadError("main", err));
