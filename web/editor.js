// The curriculum editor: draft revised versions of UC's 4-year (normalized) plan and
// compare each draft with UC as it is and with one comparison school.
// Spec: specs/11-editor-view.md.
//
// Three sections share one subject-area filter:
//   1. the editor: the draft's 8 semesters as columns of cards, plus a Removed area;
//      cards are dragged between them, and a click opens a course editor dialog;
//   2. UC today vs the draft: a two-axis view (like the Course-level alignment view)
//      joining each UC course to its place in the draft, and a table of changes;
//   3. the draft vs one school: the same two-axis view, linked by canonical course.
//
// Reads the same processed files as the other views (loadAllSchools in common.js). The
// drafts themselves are the viewer's own work, not project data, so they live in the
// browser's localStorage, with Export / Import as a JSON file to keep or move them. A
// draft stores its whole course list; every change is worked out against UC's current
// table, so it always traces back to data/processed/uc/required_courses.json.
//
// All text (from the data and from the user) is inserted with D3's .text() or as form
// values, so nothing is ever interpreted as HTML.

// ---------------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------------

// Editor cards, as on the Course Plans page: height ~ credits, with a floor so a
// 1-credit card still fits its code line. LINE_PX / CARD_PAD_PX match the .card CSS.
const CARD_PX_PER_CREDIT = 20;
const MIN_CARD_PX = 32;
const LINE_PX = 15;
const CARD_PAD_PX = 8;

// Comparison charts, as in compare.js (Course-level alignment view).
const PX_PER_CREDIT = 12;
const MIN_NODE_PX = 18;
const NODE_GAP = 2;
const BAND_PAD = 10;
const HEAD_H = 46;
const NODE_W = 220;
const MIN_LINK_W = 140;
const TWO_LINE_PX = 30;
const ORDER_PASSES = 6;

// localStorage key. The ".v1" suffix lets a later format change use a new key instead
// of misreading old drafts.
const STORE_KEY = "uc-curriculum-editor.v1";
// Pointer travel (px) before a mouse press becomes a drag, so a plain click still opens
// the editor; and how long a touch must be held before it becomes a drag, so a quick
// swipe still scrolls the page.
const DRAG_START_PX = 5;
const TOUCH_HOLD_MS = 300;
const TOUCH_SLOP_PX = 8;

// The course fields the editor can change, compared with UC's row to find revisions.
const FIELD_LABEL = { code: "code", title: "title", credits: "credits", area: "subject area",
  canonical: "canonical course", description: "description" };

// ---------------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------------

// areas: checked subject areas (shared by all sections); school: section 3's school;
// pins: the pinned node key in each chart (survives redraws).
const state = { areas: new Set(AREAS.map((a) => a.key)), school: null, pins: { ov: null, vs: null } };
let data = null;      // { schools, canon, rows } from loadAllSchools()
let canonById = null; // canonical_id -> canonical course
// UC's rows: academic (the editable 8 semesters) and co-op (kept only so the charts'
// semester labels can say "after co-op"), and UC's registry entry.
const uc = { academic: [], coop: [], school: null };
let semInfo = null;   // semester 1-8 -> UC's own year and term for it (labels, new rows)
let baseByKey = null; // UC row key (keyOf) -> UC row
// All drafts, and which one is open. drafts maps a draft id to
// { id, name, created, updated, courses: [course, ...] }.
let store = { drafts: {}, current: null };
let storageOk = true;
// Undo / redo history for the open draft: JSON snapshots of its course list.
let undoStack = [];
let redoStack = [];
const charts = {}; // "ov" / "vs" -> { model, cfg } of the last drawing

// ---------------------------------------------------------------------------------
// Data helpers
// ---------------------------------------------------------------------------------

// The stable key of a UC row: its course code (or slot title, since slots have no code)
// plus its semester. Two slots share a title ("General Education course" in semesters 4
// and 6), so the semester is needed to tell them apart. A draft stores this key, not an
// array index, so a regenerated table with rows in another order still matches.
function keyOf(r) {
  return `${r.course_code || r.title}|${r.norm_semester}`;
}

// The AREAS entry for a subject-area key (a course in a draft stores only the key).
function areaByKey(k) {
  return AREAS.find((a) => a.key === k) ?? AREAS[0];
}

// A short random id for an added course or a new draft. Math.random is enough here:
// ids only need to be unique among one viewer's drafts.
function newId(prefix) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

// Credits as text for a course object (credits_min / credits_max), "3" or "4–5".
function credText(c) {
  return c.credits_min === c.credits_max ? `${c.credits_min}` : `${c.credits_min}–${c.credits_max}`;
}

// The total credits of a list of rows or courses, as text ("16" or "16–17"). Rows that
// don't count toward UC's degree total are left out, as on the Course Plans page.
function sumText(list) {
  const counted = list.filter((r) => r.counts_toward_total !== false);
  return credText({ credits_min: d3.sum(counted, (r) => r.credits_min), credits_max: d3.sum(counted, (r) => r.credits_max) });
}

// "Semester 3 · UC Year 2 Spring" for a semester number.
function semLabel(sem) {
  const s = semInfo.get(sem);
  return `Semester ${sem} · UC Year ${s.orig_year} ${s.orig_term}`;
}

// A draft's starting course list: a copy of each of UC's academic rows, in plan order.
// Each course keeps its UC row's key in `base`; added courses have base = null.
function baselineCourses() {
  return uc.academic.map((r) => ({
    id: keyOf(r), base: keyOf(r), sem: r.norm_semester, removed: false,
    code: r.course_code, title: r.title, credits_min: r.credits_min, credits_max: r.credits_max,
    area: r.subject_area, description: r.description, canonical: r.matches.map((m) => m.canonical_id),
  }));
}

// How one draft course differs from UC. Returns { base, added, stale, removed, moved,
// fields }: base is the UC row (or null), moved is the semester shift (negative =
// earlier), and fields lists the revised fields (keys of FIELD_LABEL). A course whose
// stored key no longer exists in UC's table is "stale" and treated as added.
function changesOf(c) {
  const b = c.base ? baseByKey.get(c.base) : null;
  const out = { base: b, added: !b, stale: !!c.base && !b, removed: c.removed, moved: 0, fields: [] };
  if (!b) return out;
  if (!c.removed && c.sem !== b.norm_semester) out.moved = c.sem - b.norm_semester;
  if (c.code !== b.course_code) out.fields.push("code");
  if (c.title !== b.title) out.fields.push("title");
  if (c.credits_min !== b.credits_min || c.credits_max !== b.credits_max) out.fields.push("credits");
  if (c.area !== b.subject_area) out.fields.push("area");
  if (c.canonical.join("; ") !== b.matches.map((m) => m.canonical_id).join("; ")) out.fields.push("canonical");
  if (c.description !== b.description) out.fields.push("description");
  return out;
}

// Is a draft course a requirement slot (an elective or gen-ed slot from UC's plan)?
// Slots have no course code. An added course without a code is drawn as a course, since
// the user hasn't said it is a slot.
function isSlotCourse(c) {
  const b = c.base ? baseByKey.get(c.base) : null;
  return !c.code && !!b && !b.course_code;
}

// The registry-like entry the charts use for a draft's side.
function draftSchool(d) {
  return { school_id: "draft", short_name: "Draft", institution: d.name, program: "revised UC curriculum" };
}

// Turn a draft into table rows shaped like required_courses.json, so the comparison
// charts and helpers in common.js can treat it like any school. Each kept course
// becomes a row placed in its draft semester, with UC's year and term for that semester
// (so the labels match UC's). A course keeps its UC row's reviewed matches unless the
// user picked another canonical course; a user's pick is labeled "chosen in this
// draft". A description changed in the editor is labeled "proposed" (not UC's text).
// UC's co-op rows are added unchanged; they are not drawn (co-op terms are off) but let
// the semester labels say "after co-op", as on the alignment views.
function draftRows(d) {
  const school = draftSchool(d);
  const rows = d.courses.filter((c) => !c.removed).map((c) => {
    const ch = changesOf(c);
    const b = ch.base;
    const s = semInfo.get(c.sem);
    const ownMatches = !b || ch.fields.includes("canonical");
    return {
      ...(b || {}),
      school, _course: c, _ch: ch,
      course_code: c.code, title: c.title, credits_min: c.credits_min, credits_max: c.credits_max,
      subject_area: c.area, description: c.description,
      description_source: b && !ch.fields.includes("description") ? b.description_source : "proposed",
      norm_semester: c.sem, norm_year: s.norm_year, norm_term: s.norm_term,
      orig_year: s.orig_year, orig_term: s.orig_term, is_coop: false,
      counts_toward_total: b ? b.counts_toward_total : true,
      options: b ? b.options : "", choice_group: b ? b.choice_group : "",
      canonical_ids: c.canonical.join("; "),
      matches: ownMatches
        ? c.canonical.map((id) => ({ canonical_id: id, match_role: "covers", partial_match: false,
          match_confidence: "chosen in this draft", match_status: "not reviewed", match_rationale: "" }))
        : b.matches,
    };
  });
  return [...rows, ...uc.coop.map((r) => ({ ...r, school }))];
}

// ---------------------------------------------------------------------------------
// Storage (localStorage, with Export / Import)
// ---------------------------------------------------------------------------------

// Read the saved drafts. localStorage can be missing or throw (private windows, blocked
// site data), so every access is in try/catch and the page still works, unsaved.
function loadStore() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) {
      const s = JSON.parse(raw);
      if (s && typeof s.drafts === "object") {
        for (const id of Object.keys(s.drafts)) s.drafts[id] = sanitizeDraft(s.drafts[id], id);
        return s;
      }
    }
  } catch (e) {
    storageOk = false;
  }
  return { drafts: {}, current: null };
}

// Write all drafts back. On failure the drafts stay in memory for this visit, and the
// status line says to use Export.
function saveStore() {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify(store));
    storageOk = true;
  } catch (e) {
    storageOk = false;
  }
}

// Make one draft read from storage or an imported file safe to use: fill in missing
// fields with defaults and clamp values, so a hand-edited or older file can't break the
// page. A course placed nowhere (no semester, not removed) is put in Removed.
function sanitizeDraft(d, id) {
  const str = (v) => (typeof v === "string" ? v : "");
  const num = (v) => (Number.isFinite(v) && v >= 0 ? v : 0);
  const courses = (Array.isArray(d?.courses) ? d.courses : []).map((c) => {
    const sem = Number.isInteger(c?.sem) && c.sem >= 1 && c.sem <= 8 ? c.sem : null;
    const lo = num(c?.credits_min);
    return {
      id: str(c?.id) || newId("new"), base: str(c?.base) || null, sem, removed: !!c?.removed || sem === null,
      code: str(c?.code), title: str(c?.title) || "(untitled)", credits_min: lo, credits_max: Math.max(lo, num(c?.credits_max)),
      area: AREAS.some((a) => a.key === c?.area) ? c.area : "cs", description: str(c?.description),
      canonical: Array.isArray(c?.canonical) ? c.canonical.filter((x) => typeof x === "string") : [],
    };
  });
  return { id: id || str(d?.id) || newId("draft"), name: str(d?.name) || "Untitled draft",
    created: str(d?.created), updated: str(d?.updated), courses };
}

// A name not used by another draft: "Draft 2", "Draft 3", ... after the given one.
function uniqueName(name, exceptId = null) {
  const taken = new Set(Object.values(store.drafts).filter((d) => d.id !== exceptId).map((d) => d.name));
  if (!taken.has(name)) return name;
  let i = 2;
  while (taken.has(`${name} ${i}`)) i++;
  return `${name} ${i}`;
}

// Create a draft (a copy of UC, or of the given course list), open it, and save.
function createDraft(name, courses = baselineCourses()) {
  const now = new Date().toISOString();
  const d = { id: newId("draft"), name: uniqueName(name), created: now, updated: now,
    courses: JSON.parse(JSON.stringify(courses)) }; // deep copy, so drafts never share course objects
  store.drafts[d.id] = d;
  openDraft(d.id);
  return d;
}

// Switch to a draft. Undo history belongs to one draft, so it is cleared.
function openDraft(id) {
  store.current = id;
  undoStack = [];
  redoStack = [];
  state.pins = { ov: null, vs: null };
  saveStore();
}

const currentDraft = () => store.drafts[store.current];

// Apply one change to the open draft: snapshot it for Undo, run the change, then save
// and redraw. A change that leaves the course list as it was (e.g. a card dropped where
// it started) records nothing. `change` may return the status message to show (it can
// depend on what the change found); otherwise `message` is shown.
function commit(change, message) {
  const d = currentDraft();
  const before = JSON.stringify(d.courses);
  const said = change(d);
  if (JSON.stringify(d.courses) === before) return;
  undoStack.push(before);
  redoStack = [];
  d.updated = new Date().toISOString();
  saveStore();
  renderAll();
  flash(said || message);
}

// Undo / redo: swap the open draft's course list with a snapshot from the stacks.
function undo() {
  if (!undoStack.length) return;
  const d = currentDraft();
  redoStack.push(JSON.stringify(d.courses));
  d.courses = JSON.parse(undoStack.pop());
  saveStore();
  renderAll();
  flash("Undone.");
}
function redo() {
  if (!redoStack.length) return;
  const d = currentDraft();
  undoStack.push(JSON.stringify(d.courses));
  d.courses = JSON.parse(redoStack.pop());
  saveStore();
  renderAll();
  flash("Redone.");
}

// Show a short message in the toolbar's status line. Storage trouble stays visible.
function flash(message) {
  const el = d3.select("#status-msg");
  if (!storageOk) {
    el.classed("warn", true).text("Not saved: this browser blocks storage. Use Export to keep your drafts.");
    return;
  }
  el.classed("warn", false).text(message || "Saved in this browser.");
}

// Download every draft as one JSON file. The file names UC's plan the drafts are based
// on, so it still makes sense when opened later. A temporary object URL points an <a>
// at the Blob; clicking it starts the download.
function exportDrafts() {
  const file = {
    format: "uc-curriculum-drafts", version: 1, exported: new Date().toISOString(),
    based_on: `${uc.school.institution}, ${uc.school.program}, ${uc.academic[0].plan}`,
    drafts: Object.values(store.drafts),
  };
  const blob = new Blob([JSON.stringify(file, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `uc-curriculum-drafts-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000); // free the Blob after the download starts
  flash(`Exported ${file.drafts.length} draft${file.drafts.length === 1 ? "" : "s"}.`);
}

// Read an exported file and add its drafts. Each gets a new id, and a name that is
// already used gets " (imported)", so nothing in this browser is overwritten.
function importDrafts(file) {
  const reader = new FileReader();
  reader.onload = () => {
    let parsed = null;
    try { parsed = JSON.parse(reader.result); } catch (e) { /* reported below */ }
    const list = Array.isArray(parsed?.drafts) ? parsed.drafts : null;
    if (!list) {
      d3.select("#status-msg").classed("warn", true).text("That file is not an exported drafts file.");
      return;
    }
    let last = null;
    for (const raw of list) {
      const d = sanitizeDraft(raw, newId("draft"));
      const taken = Object.values(store.drafts).some((x) => x.name === d.name);
      d.name = uniqueName(taken ? `${d.name} (imported)` : d.name);
      store.drafts[d.id] = d;
      last = d;
    }
    if (last) openDraft(last.id);
    renderAll();
    flash(`Imported ${list.length} draft${list.length === 1 ? "" : "s"}.`);
  };
  reader.readAsText(file);
}

// ---------------------------------------------------------------------------------
// Toolbar and filters
// ---------------------------------------------------------------------------------

// Wire up the toolbar buttons, the subject filter, the school picker, and keyboard
// shortcuts. Called once after loading.
function setupControls() {
  d3.select("#draft-pick").on("change", (event) => { openDraft(event.target.value); renderAll(); flash("Opened."); });
  // Rename on change (Enter or leaving the field). An empty name is put back; a name
  // used by another draft gets a number.
  d3.select("#draft-name").on("change", (event) => {
    const d = currentDraft();
    const name = event.target.value.trim();
    if (name) { d.name = uniqueName(name, d.id); d.updated = new Date().toISOString(); saveStore(); }
    renderAll();
    flash(name ? "Renamed." : "A draft needs a name.");
  });
  d3.select("#btn-new").on("click", () => { createDraft("Draft"); renderAll(); flash("New draft, copied from UC's current plan."); });
  d3.select("#btn-dup").on("click", () => {
    const d = currentDraft();
    createDraft(`${d.name} copy`, d.courses);
    renderAll();
    flash("Duplicated.");
  });
  // Delete takes two clicks: the first turns the button into "Confirm delete" for a few
  // seconds (no browser confirm() dialog). The last draft is replaced by a fresh copy of UC.
  let armed = null;
  d3.select("#btn-del").on("click", (event) => {
    const btn = event.currentTarget;
    if (!armed) {
      btn.textContent = "Confirm delete";
      armed = setTimeout(() => { armed = null; btn.textContent = "Delete"; }, 4000);
      return;
    }
    clearTimeout(armed);
    armed = null;
    btn.textContent = "Delete";
    const name = currentDraft().name;
    delete store.drafts[store.current];
    const rest = Object.values(store.drafts);
    if (rest.length) openDraft(rest[0].id); else createDraft("Draft 1");
    renderAll();
    flash(`Deleted "${name}".`);
  });
  d3.select("#btn-undo").on("click", undo);
  d3.select("#btn-redo").on("click", redo);
  d3.select("#btn-export").on("click", exportDrafts);
  d3.select("#btn-import").on("click", () => document.getElementById("import-file").click());
  d3.select("#import-file").on("change", (event) => {
    if (event.target.files[0]) importDrafts(event.target.files[0]);
    event.target.value = ""; // so choosing the same file again fires change again
  });
  d3.select("#btn-add").on("click", () => openCourseDialog(null));

  // One checkbox per subject area, shared by all three sections.
  const boxes = d3.select("#area-filters").selectAll("label").data(AREAS).join("label").attr("class", "area");
  boxes.append("input").attr("type", "checkbox").property("checked", true)
    .on("change", (event, a) => {
      if (event.target.checked) state.areas.add(a.key); else state.areas.delete(a.key);
      renderAll();
    });
  boxes.append("i").style("background", (a) => a.color);
  boxes.append("span").text((a) => a.label);

  // Section 3's school picker (every school but UC), kept in the URL as ?school=osu.
  const others = data.schools.filter((s) => s.school_id !== "uc");
  const fromUrl = new URLSearchParams(location.search).get("school");
  state.school = others.some((s) => s.school_id === fromUrl) ? fromUrl : others[0].school_id;
  d3.select("#school").selectAll("option").data(others).join("option")
    .attr("value", (s) => s.school_id).text((s) => `${s.short_name} (${s.institution})`)
    .property("selected", (s) => s.school_id === state.school);
  d3.select("#school").on("change", (event) => {
    state.school = event.target.value;
    state.pins.vs = null;
    history.replaceState(null, "", `?school=${state.school}`);
    renderVsSchool();
  });

  // Legends for the two charts' line styles.
  const legend = (sel, keys) => {
    for (const [cls, color, text] of keys) {
      const item = d3.select(sel).append("span");
      item.append("i").attr("class", cls).style("border-color", color);
      item.append("span").text(text);
    }
  };
  legend("#ov-legend", [["line-key", "var(--earlier)", "▲ Moved earlier"], ["line-key", "var(--later)", "▼ Moved later"],
    ["line-key", "var(--axis)", "Same semester"], ["unmatched-key", null, "Removed in the draft"]]);
  legend("#vs-legend", [["line-key", "var(--ink-2)", "Same canonical course"], ["partial-key", null, "Partial match"],
    ["possible-key", null, "Possible (one option of a choice)"], ["unmatched-key", null, "No counterpart on the other side"]]);

  // Keyboard: Escape unpins both charts; Ctrl/Cmd+Z undoes and Shift+Ctrl/Cmd+Z redoes,
  // except while typing in a field or with the course dialog open (where Ctrl+Z
  // should undo typing, as usual).
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { state.pins = { ov: null, vs: null }; renderOldNew(); renderVsSchool(); }
    const typing = event.target.closest("input, textarea, select") || document.getElementById("course-dialog").open;
    if (!typing && (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      if (event.shiftKey) redo(); else undo();
    }
  });
  // Redraw the charts when resizing pauses (150 ms), since their width follows the page.
  let timer = null;
  window.addEventListener("resize", () => { clearTimeout(timer); timer = setTimeout(() => { renderOldNew(); renderVsSchool(); }, 150); });
}

// Refresh the toolbar for the open draft: picker options, name, and button states.
function renderToolbar() {
  const d = currentDraft();
  const list = d3.sort(Object.values(store.drafts), (x) => x.name.toLowerCase());
  d3.select("#draft-pick").selectAll("option").data(list, (x) => x.id).join("option")
    .attr("value", (x) => x.id).text((x) => x.name).property("selected", (x) => x.id === d.id);
  d3.select("#draft-name").property("value", d.name);
  d3.select("#btn-undo").property("disabled", !undoStack.length);
  d3.select("#btn-redo").property("disabled", !redoStack.length);
}

// Redraw everything after a change.
function renderAll() {
  renderToolbar();
  renderEditor();
  renderOldNew();
  renderVsSchool();
}

// ---------------------------------------------------------------------------------
// Section 1: the editor
// ---------------------------------------------------------------------------------

// Is a draft course in a checked subject area?
const shownCourse = (c) => state.areas.has(c.area);

// Card height in the editor (as on Course Plans). Range rows use the top of the range.
const cardHeight = (c) => Math.max(MIN_CARD_PX, c.credits_max * CARD_PX_PER_CREDIT);

// Draw the year blocks with their semester columns, the Removed area, and the summary
// line. Each column shows the draft's credits for that semester and, when different,
// UC's. Hidden subject areas are left out of the cards but not of the credit totals.
function renderEditor() {
  const d = currentDraft();
  const root = d3.select("#years");
  root.selectAll("*").remove();
  for (let year = 1; year <= 4; year++) {
    const block = root.append("section").attr("class", "year");
    block.append("h3").text(`Year ${year}`);
    const sems = block.append("div").attr("class", "sems");
    for (const sem of [2 * year - 1, 2 * year]) {
      const col = sems.append("div");
      const mine = d.courses.filter((c) => !c.removed && c.sem === sem);
      const head = col.append("div").attr("class", "sem-head");
      head.append("b").text(`Semester ${sem}`);
      const s = semInfo.get(sem);
      head.append("span").text(`UC Year ${s.orig_year} ${s.orig_term}`);
      const now = sumText(mine);
      const before = sumText(uc.academic.filter((r) => r.norm_semester === sem));
      const cr = head.append("span").text(`${now} credits`);
      if (now !== before) cr.append("span").attr("class", "delta").text(` (UC: ${before})`);
      // data-drop marks the element as a drop target; its value is the semester.
      const stack = col.append("div").attr("class", "stack").attr("data-drop", sem);
      drawCards(stack, mine.filter(shownCourse), false);
    }
  }

  const removed = d.courses.filter((c) => c.removed);
  const removedStack = d3.select("#removed");
  removedStack.selectAll("*").remove();
  drawCards(removedStack, removed.filter(shownCourse), true);
  if (!removed.length) removedStack.append("p").attr("class", "muted").style("margin", "auto 0").text("Nothing removed.");
  else if (!removed.some(shownCourse)) removedStack.append("p").attr("class", "muted").style("margin", "auto 0").text("Removed courses are in hidden subject areas.");

  // Summary: credits, and how many courses differ from UC.
  const kept = d.courses.filter((c) => !c.removed);
  const changed = d.courses.filter((c) => { const ch = changesOf(c); return ch.added || ch.removed || ch.moved || ch.fields.length; });
  const when = d.updated ? new Date(d.updated).toLocaleString() : "";
  d3.select("#draft-summary").text(`"${d.name}": ${sumText(kept)} credits in ${kept.length} courses and slots ` +
    `(UC today: ${sumText(uc.academic)} in ${uc.academic.length}). ${changed.length} course${changed.length === 1 ? "" : "s"} ` +
    `changed from UC.${when ? ` Last changed ${when}.` : ""}`);

  // Courses whose UC row is gone from the data (the table was regenerated).
  const stale = d.courses.filter((c) => changesOf(c).stale);
  d3.select("#stale-msg").classed("warn", stale.length > 0).text(stale.length
    ? `${stale.length} course${stale.length === 1 ? " is" : "s are"} no longer in UC's table and ${stale.length === 1 ? "is" : "are"} treated as added: ${stale.map((c) => c.code || c.title).join(", ")}.`
    : "");
}

// Draw course cards into a drop target. Removed cards show where the course used to be
// in UC's plan. Tags say how a card differs from UC: NEW, MOVED (from semester k),
// REVISED, and PROPOSED when its description was written in the editor.
function drawCards(stack, courses, removedMode) {
  const cards = stack.selectAll("button.card").data(courses, (c) => c.id).join("button")
    .attr("type", "button")
    .attr("class", (c) => `card${isSlotCourse(c) ? " slot" : ""}`)
    .attr("data-id", (c) => c.id)
    .style("--stripe", (c) => areaByKey(c.area).color)
    // min-height, not height, so a card with change tags can grow to fit them.
    .style("min-height", removedMode ? null : (c) => `${cardHeight(c)}px`)
    .attr("title", (c) => `${c.code || "Slot"}: ${c.title} (${credText(c)} cr). Drag to move; click to edit.`)
    .attr("aria-label", (c) => `${c.code || "Slot"} ${c.title}, ${credText(c)} credits${removedMode ? ", removed" : `, semester ${c.sem}`}. Press Enter to edit.`);

  cards.each(function (c) {
    const card = d3.select(this);
    const ch = changesOf(c);
    const top = card.append("span").attr("class", "code");
    top.append("span").text(c.code ? `${c.code} · ${credText(c)} cr` : `${credText(c)} cr`);
    const b = ch.base;
    if (b && b.description_source === "generic" && !ch.fields.includes("description")) appendGenericBadge(top);

    const tags = [];
    if (ch.added) tags.push(["new", "new"]);
    if (ch.moved) tags.push(["moved", `moved from S${b.norm_semester}`]);
    if (ch.fields.length) tags.push(["revised", "revised"]);
    if (ch.added || ch.fields.includes("description")) tags.push(["proposed", "proposed"]);
    if (removedMode && b) {
      card.append("span").attr("class", "title").text(c.title);
      card.append("span").attr("class", "was").text(`Was: ${semLabel(b.norm_semester)}`);
    } else {
      // Title lines left under the code line (and the tag line, if any), as on Course Plans.
      const lines = Math.floor((cardHeight(c) - CARD_PAD_PX) / LINE_PX) - 1 - (tags.length ? 1 : 0);
      if (lines >= 1) card.append("span").attr("class", "title").style("-webkit-line-clamp", lines).text(c.title);
    }
    if (tags.length) {
      const t = card.append("span").attr("class", "tags");
      for (const [cls, text] of tags) t.append("span").attr("class", `tag ${cls}`).text(text);
    }
    enableDrag(this, c);
  });
}

// ---- Drag and drop -------------------------------------------------------------
//
// Built on pointer events (mouse, pen, and touch alike) instead of the HTML5 drag-and-
// drop API, which doesn't work on most phones. A mouse press becomes a drag after
// DRAG_START_PX of movement; a touch becomes a drag after being held still for
// TOUCH_HOLD_MS, so an ordinary swipe still scrolls the page. While dragging, a copy of
// the card (the "ghost") follows the pointer, the target under it is outlined, and a
// marker shows where the card will be inserted.

let drag = null; // { course, el, ghost, dx, dy, target, before } while a drag is on
let suppressClick = false; // the click that follows a drop must not open the editor

// While a touch drag is on, stop the page from scrolling. This needs a non-passive
// touchmove listener (passive listeners can't call preventDefault).
document.addEventListener("touchmove", (event) => { if (drag) event.preventDefault(); }, { passive: false });

// Make one card draggable, and open the editor on a plain click.
function enableDrag(el, course) {
  el.addEventListener("click", () => {
    if (suppressClick) { suppressClick = false; return; }
    openCourseDialog(course);
  });
  el.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return; // left button / touch contact only
    const x0 = e.clientX;
    const y0 = e.clientY;
    const touch = e.pointerType !== "mouse";
    let hold = null;
    let last = e;
    const begin = () => startDrag(el, course, last);
    if (touch) hold = setTimeout(begin, TOUCH_HOLD_MS);

    const move = (ev) => {
      last = ev;
      const dist = Math.hypot(ev.clientX - x0, ev.clientY - y0); // straight-line distance moved
      if (!drag) {
        if (touch) { if (dist > TOUCH_SLOP_PX) stop(); return; } // moved before the hold: a scroll
        if (dist < DRAG_START_PX) return;
        begin();
      }
      ev.preventDefault();
      dragMove(ev);
    };
    const up = (ev) => {
      if (drag) { dragDrop(ev); suppressClick = true; setTimeout(() => { suppressClick = false; }, 0); }
      stop();
    };
    const stop = () => {
      clearTimeout(hold);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", cancel);
    };
    const cancel = () => { if (drag) endDrag(); stop(); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", cancel);
  });
}

// Start dragging: make the ghost (a clone of the card at the same size) and fade the card.
function startDrag(el, course, e) {
  const rect = el.getBoundingClientRect();
  const ghost = el.cloneNode(true);
  ghost.classList.add("ghost");
  ghost.style.width = `${rect.width}px`;
  ghost.style.height = `${rect.height}px`;
  document.body.appendChild(ghost);
  el.classList.add("dragging");
  // dx / dy: where the pointer grabbed the card, so the ghost doesn't jump.
  drag = { course, el, ghost, dx: e.clientX - rect.left, dy: e.clientY - rect.top, target: null, before: null };
  hideTooltip();
  dragMove(e);
}

// Move the ghost and find the drop target and insertion point under the pointer.
// elementFromPoint returns the topmost element there; the ghost has pointer-events:
// none, so it is never the answer. closest() walks up to the element marked data-drop.
function dragMove(e) {
  drag.ghost.style.left = `${e.clientX - drag.dx}px`;
  drag.ghost.style.top = `${e.clientY - drag.dy}px`;
  const under = document.elementFromPoint(e.clientX, e.clientY);
  const target = under ? under.closest("[data-drop]") : null;
  document.querySelectorAll(".drop-on").forEach((t) => t.classList.remove("drop-on"));
  document.querySelectorAll(".drop-marker").forEach((m) => m.remove());
  drag.target = target;
  drag.before = null;
  if (!target) return;
  target.classList.add("drop-on");
  // Insert before the first card whose middle is below the pointer (semesters stack
  // vertically). The Removed area has no meaningful order, so drops there go last.
  const cards = [...target.querySelectorAll(".card:not(.dragging)")];
  const ref = target.dataset.drop === "removed" ? null
    : cards.find((c) => { const r = c.getBoundingClientRect(); return e.clientY < r.top + r.height / 2; });
  drag.before = ref ? ref.dataset.id : null;
  const marker = document.createElement("div");
  marker.className = "drop-marker";
  target.insertBefore(marker, ref || null); // insertBefore(x, null) appends
}

// Drop: apply the move (or removal), then clean up. A drop outside any target does nothing.
function dragDrop() {
  const { course, target, before } = drag;
  endDrag();
  if (!target) return;
  placeCourse(course.id, target.dataset.drop, before);
}

// Remove the ghost, marker, and highlights.
function endDrag() {
  drag.ghost.remove();
  drag.el.classList.remove("dragging");
  document.querySelectorAll(".drop-on").forEach((t) => t.classList.remove("drop-on"));
  document.querySelectorAll(".drop-marker").forEach((m) => m.remove());
  drag = null;
}

// Put a course (already in, or new to, the list `courses`) in a semester ("1"-"8") or
// in "removed", before the course with id `beforeId` (or at the end of that semester).
// Mutates the list and returns a status message. Shared by drag and drop and the
// course editor. An added course moved to Removed is deleted, since it has no UC
// placement to show there; Undo brings it back.
function moveInList(courses, c, where, beforeId = null) {
  const label = c.code || c.title;
  const i = courses.indexOf(c);
  if (i >= 0) courses.splice(i, 1); // take it out; it goes back in below
  let message;
  if (where === "removed") {
    if (!c.base) return `Deleted added course ${label} (Undo restores it).`;
    c.removed = true;
    message = `Removed ${label}.`;
  } else {
    const was = i < 0 ? null : c.removed ? "Removed" : `semester ${c.sem}`;
    c.removed = false;
    c.sem = Number(where);
    message = !was ? `Added ${label} to semester ${c.sem}.`
      : was === `semester ${c.sem}` ? `Reordered semester ${c.sem}.` : `Moved ${label} from ${was} to semester ${c.sem}.`;
  }
  // Where in the list: before the given card, else before the first course of a later
  // semester (keeping the list in semester order), else at the end. Removed courses go last.
  let at = beforeId ? courses.findIndex((x) => x.id === beforeId) : -1;
  if (at < 0) {
    const after = c.removed ? -1 : courses.findIndex((x) => x.removed || x.sem > c.sem);
    at = after < 0 ? courses.length : after;
  }
  courses.splice(at, 0, c);
  return message;
}

// Move a course of the open draft as one Undo step (see moveInList).
function placeCourse(id, where, beforeId = null) {
  commit((d) => moveInList(d.courses, d.courses.find((c) => c.id === id), where, beforeId));
}

// ---------------------------------------------------------------------------------
// Course editor dialog
// ---------------------------------------------------------------------------------

let editing = null; // the course being edited, or null when adding

// Fill the dialog's select boxes once: subject areas, semesters (with UC's terms), and
// canonical courses (alphabetical, with "none" first).
function setupDialog() {
  d3.select("#f-area").selectAll("option").data(AREAS).join("option").attr("value", (a) => a.key).text((a) => a.label);
  const sems = [...d3.range(1, 9).map((s) => [String(s), semLabel(s)]), ["removed", "Removed"]];
  d3.select("#f-sem").selectAll("option").data(sems).join("option").attr("value", (s) => s[0]).text((s) => s[1]);
  const dlg = document.getElementById("course-dialog");
  d3.select("#f-cancel").on("click", () => dlg.close());
  d3.select("#course-form").on("submit", (event) => {
    event.preventDefault(); // keep the dialog open until the input is valid
    if (saveCourseDialog()) dlg.close();
  });
  d3.select("#f-remove").on("click", () => { dlg.close(); placeCourse(editing.id, "removed"); });
  d3.select("#f-restore").on("click", () => {
    const b = baseByKey.get(editing.base);
    const id = editing.id;
    commit((d) => {
      const c = d.courses.find((x) => x.id === id);
      Object.assign(c, { code: b.course_code, title: b.title, credits_min: b.credits_min, credits_max: b.credits_max,
        area: b.subject_area, description: b.description, canonical: b.matches.map((m) => m.canonical_id),
        removed: false, sem: b.norm_semester });
    }, `Restored ${b.course_code || b.title} to UC's original.`);
    dlg.close();
  });
}

// The canonical-course choices for a course. A UC row with several matches gets a
// first option that keeps all of them, since one select box can't show several.
function fillCanonOptions(c) {
  const opts = [["", "(none)"]];
  if (c && c.canonical.length > 1) {
    opts.push(["__keep", `Keep: ${c.canonical.map((id) => canonById.get(id)?.name || id).join(" + ")}`]);
  }
  for (const k of d3.sort(data.canon, (k) => k.name)) opts.push([k.canonical_id, k.name]);
  d3.select("#f-canon").selectAll("option").data(opts, (o) => o[0]).join("option").attr("value", (o) => o[0]).text((o) => o[1]);
  const v = !c ? "" : c.canonical.length > 1 ? "__keep" : c.canonical[0] || "";
  document.getElementById("f-canon").value = v;
}

// Open the dialog for one course, or empty for a new one (course = null).
function openCourseDialog(course) {
  editing = course;
  const f = (id) => document.getElementById(id);
  const b = course && course.base ? baseByKey.get(course.base) : null;
  f("dlg-title").textContent = course ? `Edit ${course.code || course.title}` : "Add a course";
  f("f-code").value = course ? course.code : "";
  f("f-title").value = course ? course.title : "";
  f("f-credits").value = course ? credText(course).replace("–", "-") : "3";
  f("f-area").value = course ? course.area : "cs";
  f("f-sem").value = !course ? "1" : course.removed ? "removed" : String(course.sem);
  f("f-desc").value = course ? course.description : "";
  fillCanonOptions(course);
  f("f-error").textContent = "";
  f("f-restore").classList.toggle("hidden", !b);
  f("f-remove").classList.toggle("hidden", !course || course.removed);
  f("f-remove").textContent = b ? "Remove" : "Delete";

  // UC's original, for reference (a UC course only).
  const orig = d3.select("#f-orig").classed("hidden", !b);
  orig.selectAll("*").remove();
  if (b) {
    orig.append("summary").text(`UC original: ${b.course_code ? `${b.course_code} ` : ""}${b.title} · ` +
      `${semLabel(b.norm_semester)} · ${creditText(b)} cr`);
    const h = orig.append("p").style("margin", "6px 0 2px").style("font-weight", "600")
      .text(b.description_source === "generic" ? "Description (generic, written for this project) " : "Description (UC catalog)");
    if (b.description_source === "generic") appendGenericBadge(h);
    orig.append("p").attr("class", "desc").text(b.description);
  }
  hideTooltip();
  f("course-dialog").showModal();
  f("f-title").focus();
}

// Check the dialog's fields and apply them as one change (one Undo step). Returns false
// (and shows why) when a field is invalid.
function saveCourseDialog() {
  const f = (id) => document.getElementById(id);
  const title = f("f-title").value.trim();
  // Credits: one number, or a range "4-5" / "4–5". (\d+(?:\.\d+)?) is a whole or decimal
  // number; the second, optional group is the top of the range.
  const m = f("f-credits").value.match(/^\s*(\d+(?:\.\d+)?)\s*(?:[-–]\s*(\d+(?:\.\d+)?))?\s*$/);
  const lo = m ? Number(m[1]) : NaN;
  const hi = m ? Number(m[2] ?? m[1]) : NaN;
  const err = !title ? "A title is required."
    : !m || hi < lo || hi > 30 ? "Credits must be a number from 0 to 30, or a range like 4-5." : "";
  f("f-error").textContent = err;
  if (err) return false;

  const canonPick = f("f-canon").value;
  const where = f("f-sem").value;
  const fields = { code: f("f-code").value.trim(), title, credits_min: lo, credits_max: hi, area: f("f-area").value,
    description: f("f-desc").value.replace(/\r\n/g, "\n").trim() };
  if (!editing) {
    if (where === "removed") { f("f-error").textContent = "Choose a semester for the new course."; return false; }
    // A new course goes at the end of its semester.
    const c = { id: newId("new"), base: null, sem: Number(where), removed: false,
      ...fields, canonical: canonPick ? [canonPick] : [] };
    commit((d) => moveInList(d.courses, c, where));
    return true;
  }
  const id = editing.id;
  const moveTo = where === "removed" ? (editing.removed ? null : "removed") : (editing.removed || Number(where) !== editing.sem ? where : null);
  // Description: if only line breaks or outer spaces differ from UC's, keep UC's text
  // exactly, so the course isn't marked as having a proposed description.
  const b = editing.base ? baseByKey.get(editing.base) : null;
  if (b && fields.description === b.description.replace(/\r\n/g, "\n").trim()) fields.description = b.description;
  // One change (one Undo step): the fields, then the move, if any.
  commit((d) => {
    const c = d.courses.find((x) => x.id === id);
    Object.assign(c, fields);
    if (canonPick !== "__keep") c.canonical = canonPick ? [canonPick] : [];
    if (moveTo) return moveInList(d.courses, c, moveTo);
  }, `Saved ${fields.code || title}.`);
  return true;
}

// ---------------------------------------------------------------------------------
// Two-axis comparison charts (sections 2 and 3)
// ---------------------------------------------------------------------------------
//
// The same layout as the Course-level alignment view (compare.js): two columns of
// course nodes by semester (shared bands so semester k lines up), node height ~
// credits, a curve between linked nodes, barycenter ordering within each band, and the
// band labels from common.js (drawSlotBands, each side with its own terms). What links
// two rows, and how a node or line is tagged, comes from the chart's config (cfg):
//   linkFn(leftRow, rightRow) -> null, or an object of link properties (cls, shared...)
//   tagOf(node) -> { text, cls } or null   (a small tag at the right of the node)
//   fade(node) -> true to draw the node lighter
//   tipNode / tipLink(event, x), detail(node) -> panel contents

// Node height for one row (co-op rows are not drawn here).
const nodeHeight = (r) => Math.max(MIN_NODE_PX, r.credits_max * PX_PER_CREDIT);

// A key that finds the same node again after a redraw (node ids are positional): the
// side, school, and the course id (draft) or row key (UC and other schools).
const nodeKey = (n) => `${n.side}:${n.row.school.school_id}:${n.row._course ? n.row._course.id : keyOf(n.row)}`;

// Build the graph: nodes for the placed rows (co-op terms are off, so termSlots gives
// the 8 semesters), links from cfg.linkFn over every pair, then the subject filter
// (links are found among all rows first, so a course whose only counterpart is hidden
// still counts as matched), band heights, and the within-band order.
function buildModel(leftRows, rightRows, cfg) {
  const { slots, slotOf } = termSlots(leftRows, rightRows, false);
  const nodes = (rows, side) => rows.filter((r) => slotOf(r) !== null && slotOf(r) !== undefined)
    .map((r, i) => ({ id: `${side}${i}`, side, row: r, sem: r.norm_semester, slot: slotOf(r), h: nodeHeight(r),
      area: areaOf(r), allLinks: [] }));
  let left = nodes(leftRows, "L");
  let right = nodes(rightRows, "R");
  const allLinks = [];
  for (const u of left) {
    for (const v of right) {
      const props = cfg.linkFn(u.row, v.row);
      if (!props) continue;
      const link = { ...props, id: `${u.id}-${v.id}`, source: u, target: v };
      allLinks.push(link);
      u.allLinks.push(link);
      v.allLinks.push(link);
    }
  }
  const shown = (n) => state.areas.has(n.area.key);
  left = left.filter(shown);
  right = right.filter(shown);
  const links = allLinks.filter((l) => shown(l.source) && shown(l.target));
  for (const n of [...left, ...right]) n.links = n.allLinks.filter((l) => links.includes(l));

  const stackHeight = (ns, k) => d3.sum(ns.filter((n) => n.slot === k), (n) => n.h + NODE_GAP);
  const bandH = slots.map((s, k) => Math.max(stackHeight(left, k), stackHeight(right, k), MIN_NODE_PX) + 2 * BAND_PAD);
  // d3.cumsum gives running totals; prepending 0 turns them into each band's top.
  const bandTop = [0, ...d3.cumsum(bandH)].map((y) => y + HEAD_H);
  const bands = { L: d3.group(left, (n) => n.slot), R: d3.group(right, (n) => n.slot) };
  const m = { left, right, links, slots, bandH, bandTop, bands, bySlot: bands, withCoop: false, height: bandTop[slots.length] + 8 };
  orderNodes(m);
  return m;
}

// Stack each band's nodes from its top, in their current order.
function placeNodes(m) {
  for (const side of ["L", "R"]) {
    for (const [k, ns] of m.bands[side]) {
      let y = m.bandTop[k] + BAND_PAD;
      for (const n of ns) { n.y = y; y += n.h + NODE_GAP; }
    }
  }
}

// Barycenter ordering, as in compare.js: start by subject area, then by course label;
// then, a few passes alternating sides, sort each band by the mean y of each node's
// partners. Array.prototype.sort is stable, so the result is the same on every run.
function orderNodes(m) {
  const areaRank = new Map(AREAS.map((a, i) => [a.key, i]));
  for (const side of ["L", "R"]) {
    for (const ns of m.bands[side].values()) {
      ns.sort((a, b) => areaRank.get(a.area.key) - areaRank.get(b.area.key) || rowLabel(a.row).localeCompare(rowLabel(b.row)));
    }
  }
  placeNodes(m);
  const center = (n) => n.y + n.h / 2;
  let unchanged = 0;
  for (let pass = 0; pass < ORDER_PASSES && unchanged < 2; pass++) {
    const side = pass % 2 === 0 ? "R" : "L";
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
    unchanged = changed ? 0 : unchanged + 1;
  }
}

// Draw one comparison chart into svg#<cfg.id>-chart from the given rows and config.
function drawChart(cfg, leftRows, rightRows) {
  const model = buildModel(leftRows, rightRows, cfg);
  charts[cfg.id] = { model, cfg };
  const wrap = document.querySelector(`#${cfg.id}-chart`).parentNode;
  const width = Math.max(wrap.clientWidth, 2 * COOP_LABEL_W + 2 * NODE_W + MIN_LINK_W);
  const xL = COOP_LABEL_W;
  const xR = width - NODE_W - COOP_LABEL_W;
  const svg = d3.select(`#${cfg.id}-chart`).attr("width", width).attr("height", model.height)
    .attr("viewBox", `0 0 ${width} ${model.height}`);
  svg.selectAll("*").remove();

  for (const [x, head] of [[xL, cfg.heads[0]], [xR, cfg.heads[1]]]) {
    fitSvgText(svg.append("text").attr("class", "col-head").attr("x", x).attr("y", 18).node(), head.name, NODE_W);
    fitSvgText(svg.append("text").attr("class", "col-sub").attr("x", x).attr("y", 34).node(), head.sub, NODE_W);
  }
  drawSlotBands(svg, model, { width, xL, xR, nodeW: NODE_W, rowsL: leftRows, rowsR: rightRows });

  // A cubic Bézier from the right edge of the left node to the left edge of the right
  // node, both control points at the horizontal middle: a smooth S-curve.
  const path = (l) => {
    const x1 = xL + NODE_W;
    const y1 = l.source.y + l.source.h / 2;
    const x2 = xR;
    const y2 = l.target.y + l.target.h / 2;
    const mid = (x1 + x2) / 2;
    return `M${x1},${y1}C${mid},${y1} ${mid},${y2} ${x2},${y2}`;
  };
  const linkSel = svg.append("g").selectAll("g").data(model.links, (l) => l.id).join("g");
  linkSel.append("path").attr("class", (l) => `link ${l.cls || ""}`).attr("d", path)
    .attr("stroke", (l) => l.color || null); // null leaves the color to the CSS class
  linkSel.append("path").attr("class", "link-hit").attr("d", path)
    .on("mouseenter", (event, l) => { focusChart(cfg.id, l); cfg.tipLink(event, l); })
    .on("mousemove", moveTooltip)
    .on("mouseleave", () => { hideTooltip(); focusChart(cfg.id, pinnedNode(cfg.id)); });

  const nodeSel = svg.append("g").selectAll("g").data([...model.left, ...model.right], (n) => n.id).join("g")
    .attr("class", (n) => ["node", n.row.course_code || n.row._course ? "" : "slot", cfg.fade(n) ? "unmatched" : ""].join(" "))
    .attr("transform", (n) => `translate(${n.side === "L" ? xL : xR},${n.y})`)
    .attr("tabindex", 0)
    .attr("role", "button")
    .attr("aria-label", (n) => `${n.row.school.short_name} ${rowLabel(n.row)}: ${n.row.title}, semester ${n.sem}, ` +
      `${creditText(n.row)} credits${cfg.tagOf(n) ? `, ${cfg.tagOf(n).text}` : ""}`)
    .on("mouseenter", (event, n) => { focusChart(cfg.id, n); cfg.tipNode(event, n); })
    .on("mousemove", moveTooltip)
    .on("mouseleave", () => { hideTooltip(); focusChart(cfg.id, pinnedNode(cfg.id)); })
    .on("click", (event, n) => { event.stopPropagation(); togglePin(cfg.id, n); })
    .on("keydown", (event, n) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); togglePin(cfg.id, n); } });

  nodeSel.append("rect").attr("class", "box").attr("width", NODE_W).attr("height", (n) => n.h).attr("rx", 4);
  nodeSel.append("rect").attr("class", "stripe").attr("width", 4).attr("height", (n) => n.h).attr("rx", 2)
    .attr("fill", (n) => n.area.color);
  // Text: code and credits (or slot title) on the first line, the title on a second
  // line when the box is tall enough, and the node's tag (NEW, REMOVED...) at the right.
  nodeSel.each(function (n) {
    const g = d3.select(this);
    const r = n.row;
    const tag = cfg.tagOf(n);
    const tagW = tag ? 7 * tag.text.length + 10 : 0; // rough width of the small caps tag
    const twoLines = n.h >= TWO_LINE_PX;
    const y1 = twoLines ? 13 : n.h / 2 + 4;
    const first = r.course_code ? `${r.course_code} · ${creditText(r)} cr` : r.title;
    fitSvgText(g.append("text").attr("class", "code").attr("x", 10).attr("y", y1).node(), first, NODE_W - 14 - tagW);
    if (tag) g.append("text").attr("class", `ntag ${tag.cls}`).attr("x", NODE_W - 6).attr("y", y1).attr("text-anchor", "end").text(tag.text);
    if (twoLines) {
      const second = r.course_code ? r.title : `${creditText(r)} cr${r._course && !r._course.base ? "" : ", student chooses"}`;
      fitSvgText(g.append("text").attr("class", "title").attr("x", 10).attr("y", 27).node(), second, NODE_W - 14);
    }
  });

  svg.on("click", () => togglePin(cfg.id, null));
  if (!pinnedNode(cfg.id)) state.pins[cfg.id] = null; // the pinned course is gone or hidden
  focusChart(cfg.id, pinnedNode(cfg.id));
  renderDetailPanel(cfg.id);
}

// The pinned node of a chart in its current model, or null.
function pinnedNode(id) {
  const c = charts[id];
  if (!c || !state.pins[id]) return null;
  return [...c.model.left, ...c.model.right].find((n) => nodeKey(n) === state.pins[id]) || null;
}

// Highlight a node (with its partners and links) or a link, fading the rest; null clears.
function focusChart(id, target) {
  const on = new Set();
  if (target && target.links) {
    on.add(target.id);
    for (const l of target.links) { on.add(l.id); on.add(l.source.id); on.add(l.target.id); }
  } else if (target) {
    on.add(target.id); on.add(target.source.id); on.add(target.target.id);
  }
  const svg = d3.select(`#${id}-chart`).classed("focusing", !!target);
  svg.selectAll(".node").classed("on", (n) => on.has(n.id)).classed("pinned", (n) => nodeKey(n) === state.pins[id]);
  svg.selectAll(".link").classed("on", (l) => on.has(l.id));
}

// Pin or unpin a node (clicking the pinned node again, or empty space, unpins).
function togglePin(id, n) {
  state.pins[id] = n && nodeKey(n) !== state.pins[id] ? nodeKey(n) : null;
  focusChart(id, pinnedNode(id));
  renderDetailPanel(id);
}

// Fill a chart's side panel with the pinned node's details (or a hint).
function renderDetailPanel(id) {
  const panel = d3.select(`#${id}-detail`);
  panel.selectAll("*").remove();
  const n = pinnedNode(id);
  if (!n) {
    panel.append("p").attr("class", "muted").text("Click a course to pin it and see its details.");
    return;
  }
  charts[id].cfg.detail(panel, n);
}

// Common parts of a detail panel: heading, title, facts, and the description with its
// label (UC catalog, generic, or proposed in this draft). A draft course gets an
// "Edit this course" button that opens the course editor.
function detailBasics(panel, n, extraFacts = []) {
  const r = n.row;
  const h = panel.append("h3").text(`${r.school.short_name} ${rowLabel(r)}`);
  if (r.description_source === "generic") { h.append("span").text(" "); appendGenericBadge(h); }
  if (r.course_code) panel.append("p").text(r.title);
  const facts = [["Placement", semText(r)], ["Credits", creditText(r)], ["Area", n.area.label], ...extraFacts];
  for (const m of r.matches) facts.push(["Canonical", matchText(m, canonById)]);
  const dl = panel.append("dl");
  for (const [k, v] of facts) { dl.append("dt").text(k); dl.append("dd").text(v); }
  if (r._course) {
    panel.append("button").attr("class", "btn").attr("type", "button").text("Edit this course")
      .on("click", () => openCourseDialog(currentDraft().courses.find((c) => c.id === r._course.id)));
  }
  panel.append("h4").text(descHeading(r));
  panel.append("p").attr("class", "desc").text(r.description || "(no description)");
}

// The heading for a row's description, saying where the text comes from.
function descHeading(r) {
  if (r.description_source === "proposed") return "Description (proposed in this draft, not UC's catalog text)";
  if (r.description_source === "generic") return "Description (generic, written for this project)";
  return `Description (${r.school.school_id === "draft" ? "UC" : r.school.short_name} catalog)`;
}

// Tooltip description blocks for rows; the heading names the source of the text.
const tipDescs = (rows) => rows.map((r) => ({ heading: `${r.school.short_name} ${rowLabel(r)}: ${descHeading(r)}`,
  row: { ...r, description: r.description || "(no description)" } }));

// "moved 2 earlier" / "moved 1 later" for a semester shift.
const shiftText = (k) => `moved ${Math.abs(k)} semester${Math.abs(k) === 1 ? "" : "s"} ${k < 0 ? "earlier" : "later"}`;

// What changed in a draft course, as a list of short phrases.
function changePhrases(c) {
  const ch = changesOf(c);
  const b = ch.base;
  const out = [];
  if (ch.added) out.push(ch.stale ? "added (its UC row is no longer in the data)" : "added in this draft");
  if (ch.removed) out.push("removed");
  if (ch.moved) out.push(`${shiftText(ch.moved)} (from semester ${b.norm_semester} to ${c.sem})`);
  for (const f of ch.fields) {
    if (f === "title") out.push(`title: "${b.title}" → "${c.title}"`);
    else if (f === "code") out.push(`code: ${b.course_code || "(none)"} → ${c.code || "(none)"}`);
    else if (f === "credits") out.push(`credits: ${creditText(b)} → ${credText(c)}`);
    else if (f === "area") out.push(`area: ${areaByKey(b.subject_area).label} → ${areaByKey(c.area).label}`);
    else if (f === "canonical") {
      const names = (ids) => ids.map((id) => canonById.get(id)?.name || id).join(" + ") || "(none)";
      out.push(`canonical course: ${names(b.matches.map((m) => m.canonical_id))} → ${names(c.canonical)}`);
    } else out.push(`${FIELD_LABEL[f]} rewritten`);
  }
  return out;
}

// ---------------------------------------------------------------------------------
// Section 2: UC today vs the draft
// ---------------------------------------------------------------------------------

// Draw the "UC today vs the draft" chart and its two tables.
function renderOldNew() {
  const d = currentDraft();
  const left = [...uc.academic, ...uc.coop];
  const right = draftRows(d);
  const courseByBase = new Map(d.courses.filter((c) => c.base).map((c) => [c.base, c]));
  drawChart({
    id: "ov",
    heads: [{ name: "UC today", sub: `${uc.school.institution}, ${uc.school.program}` }, { name: d.name, sub: "Draft (revised curriculum)" }],
    // A UC row links to its own copy in the draft. The class colors the line by shift.
    linkFn: (u, v) => {
      if (!v._course || v._course.base !== keyOf(u)) return null;
      const shift = v.norm_semester - u.norm_semester;
      return { shift, cls: shift < 0 ? "earlier" : shift > 0 ? "later" : "same" };
    },
    tagOf: (n) => {
      if (n.side === "L") return n.allLinks.length ? null : { text: "REMOVED", cls: "removed" };
      const ch = n.row._ch;
      if (ch.added) return { text: "NEW", cls: "new" };
      if (ch.moved) return { text: `${ch.moved < 0 ? "▲" : "▼"} ${Math.abs(ch.moved)}${ch.fields.length ? " · REVISED" : ""}`, cls: "moved" };
      if (ch.fields.length) return { text: "REVISED", cls: "revised" };
      return null;
    },
    fade: (n) => n.side === "L" && !n.allLinks.length, // removed UC courses
    tipNode: (event, n) => {
      const r = n.row;
      const lines = [`${r.school.short_name} ${rowLabel(r)}`, r.title, `${semText(r)} · ${creditText(r)} cr`];
      if (n.side === "L") {
        const c = courseByBase.get(keyOf(r));
        lines.push(!c || c.removed ? "Removed in the draft" : changePhrases(c).join("; ") || "Unchanged in the draft");
      } else {
        lines.push(changePhrases(r._course).join("; ") || "Unchanged from UC");
      }
      showTooltip(event, lines, tipDescs([r]));
    },
    tipLink: (event, l) => {
      const c = l.target.row._course;
      showTooltip(event, [
        `${rowLabel(l.source.row)}: semester ${l.source.sem} → ${l.target.sem}`,
        l.shift ? shiftText(l.shift) : "Same semester",
        ...changePhrases(c).filter((p) => !p.startsWith("moved")),
      ], tipDescs(changesOf(c).fields.length ? [l.source.row, l.target.row] : [l.target.row]));
    },
    detail: (panel, n) => {
      if (n.side === "L") {
        const c = courseByBase.get(keyOf(n.row));
        detailBasics(panel, n, [["In the draft", !c || c.removed ? "Removed" : changePhrases(c).join("; ") || "Unchanged"]]);
        if (c && c.removed) {
          panel.append("button").attr("class", "btn").attr("type", "button").style("margin-top", "4px")
            .text("Restore to UC's semester").on("click", () => placeCourse(c.id, String(n.row.norm_semester)));
        }
      } else {
        detailBasics(panel, n, [["Change", changePhrases(n.row._course).join("; ") || "Unchanged from UC"]]);
      }
    },
  }, left, right);
  renderChangesTable(d);
  renderCreditsTable(d);
}

// The changes table: one row per changed course in a shown subject area, grouped as
// Removed, Added, Moved earlier, Moved later, Revised (a course that moved and was
// revised is listed once, under its move), plus a summary line of counts.
function renderChangesTable(d) {
  const KINDS = [
    ["removed", "✕", "Removed"], ["added", "+", "Added"], ["earlier", "▲", "Moved earlier"],
    ["later", "▼", "Moved later"], ["revised", "✎", "Revised"],
  ];
  const rows = [];
  let unchanged = 0;
  for (const c of d.courses) {
    const ch = changesOf(c);
    const kind = ch.removed ? (ch.base ? "removed" : null) : ch.added ? "added" : ch.moved < 0 ? "earlier"
      : ch.moved > 0 ? "later" : ch.fields.length ? "revised" : null;
    if (!kind) { unchanged++; continue; }
    rows.push({ c, ch, kind });
  }
  const counts = d3.rollup(rows, (v) => v.length, (r) => r.kind);
  d3.select("#ov-summary").text(KINDS.map(([k, , label]) => `${counts.get(k) || 0} ${label.toLowerCase()}`).join(", ") +
    `; ${unchanged} unchanged.` + (state.areas.size < AREAS.length ? " The table below shows the checked subject areas only." : ""));

  const shown = rows.filter((r) => state.areas.has(r.ch.removed ? r.ch.base.subject_area : r.c.area))
    .sort((a, b) => KINDS.findIndex((k) => k[0] === a.kind) - KINDS.findIndex((k) => k[0] === b.kind) ||
      (a.c.sem ?? 0) - (b.c.sem ?? 0));
  const table = d3.select("#ov-table");
  table.selectAll("*").remove();
  if (!shown.length) { table.append("tbody").append("tr").append("td").attr("class", "muted").text("No changes in the shown subject areas."); return; }
  table.append("thead").append("tr").selectAll("th").data(["Change", "Course", "UC today", "Draft", "Details"]).join("th").text((h) => h);
  const tr = table.append("tbody").selectAll("tr").data(shown).join("tr");
  tr.append("td").each(function ({ kind }) {
    const [, sym, label] = KINDS.find((k) => k[0] === kind);
    const cell = d3.select(this).append("span").attr("class", `status ${kind}`);
    cell.append("b").attr("aria-hidden", "true").text(sym);
    cell.append("span").text(label);
  });
  const course = tr.append("td");
  course.append("i").attr("class", "swatch").style("background", ({ c, ch }) => areaByKey(ch.removed ? ch.base.subject_area : c.area).color);
  course.append("span").text(({ c }) => `${c.code ? `${c.code} ` : ""}${c.title}`);
  tr.append("td").text(({ ch }) => (ch.base ? semLabel(ch.base.norm_semester) : "—"));
  tr.append("td").text(({ c }) => (c.removed ? "Removed" : semLabel(c.sem)));
  tr.append("td").text(({ c, kind }) => changePhrases(c).filter((p) => !(kind === "removed" && p === "removed") &&
    !(kind === "added" && p.startsWith("added"))).join("; ") || "—");
}

// Credits per semester, UC today vs the draft, for the shown subject areas.
function renderCreditsTable(d) {
  const sems = d3.range(1, 9);
  const shownUc = uc.academic.filter((r) => state.areas.has(r.subject_area));
  const shownDraft = d.courses.filter((c) => !c.removed && shownCourse(c));
  const table = d3.select("#ov-credits");
  table.selectAll("*").remove();
  table.append("thead").append("tr").selectAll("th").data(["", ...sems.map((s) => `S${s}`), "Total"])
    .join("th").attr("class", (h, i) => (i ? "num" : null)).text((h) => h);
  const body = table.append("tbody");
  const line = (label, list, semOf) => {
    const tr = body.append("tr");
    tr.append("th").text(label);
    for (const s of sems) tr.append("td").attr("class", "num").text(sumText(list.filter((x) => semOf(x) === s)));
    tr.append("td").attr("class", "num").text(sumText(list));
  };
  line("UC today", shownUc, (r) => r.norm_semester);
  line("Draft", shownDraft, (c) => c.sem);
}

// ---------------------------------------------------------------------------------
// Section 3: the draft vs a school
// ---------------------------------------------------------------------------------

// The shared canonical courses of two rows, with each side's match (as in compare.js's
// makeLink): partial if either end is partial, possible if every shared course is one
// option of a choice on at least one end.
function canonLink(u, v) {
  const vById = new Map(v.matches.map((m) => [m.canonical_id, m]));
  const shared = u.matches.filter((m) => vById.has(m.canonical_id)).map((m) => ({ id: m.canonical_id, u: m, v: vById.get(m.canonical_id) }));
  if (!shared.length) return null;
  const ends = shared.flatMap((s) => [s.u, s.v]);
  const partial = ends.some((m) => m.partial_match);
  const possible = shared.every((s) => s.u.match_role === "one_of" || s.v.match_role === "one_of");
  return { shared, partial, possible, cls: [partial ? "partial" : "", possible ? "possible" : ""].join(" "), color: areaOf(u).color };
}

// Draw the "draft vs school" chart and its table.
function renderVsSchool() {
  const d = currentDraft();
  const other = data.schools.find((s) => s.school_id === state.school);
  const left = draftRows(d);
  const right = data.rows.filter((r) => r.school.school_id === state.school);
  drawChart({
    id: "vs",
    heads: [{ name: d.name, sub: "Draft (revised UC curriculum)" }, { name: other.short_name, sub: `${other.institution}, ${other.program}` }],
    linkFn: canonLink,
    tagOf: (n) => {
      if (n.side === "R") return null;
      const ch = n.row._ch;
      return ch.added ? { text: "NEW", cls: "new" } : ch.moved || ch.fields.length ? { text: ch.moved ? "MOVED" : "REVISED", cls: "revised" } : null;
    },
    fade: (n) => !n.allLinks.length,
    tipNode: (event, n) => {
      const r = n.row;
      const k = n.allLinks.length;
      const otherName = n.side === "L" ? other.short_name : "the draft";
      const lines = [`${r.school.short_name} ${rowLabel(r)}`, r.title, `${semText(r)} · ${creditText(r)} cr`,
        k ? `${k} counterpart${k === 1 ? "" : "s"} at ${otherName}` : `No counterpart at ${otherName}`];
      if (r._course) { const p = changePhrases(r._course); if (p.length) lines.push(`Draft: ${p.join("; ")}`); }
      showTooltip(event, lines, tipDescs([r]));
    },
    tipLink: (event, l) => {
      const shift = l.target.sem - l.source.sem;
      showTooltip(event, [
        l.shared.map((s) => canonById.get(s.id)?.name || s.id).join(" + "),
        `Draft ${rowLabel(l.source.row)} (sem ${l.source.sem}) ↔ ${other.short_name} ${rowLabel(l.target.row)} (sem ${l.target.sem})`,
        shift === 0 ? "Same semester" : `${other.short_name} is ${Math.abs(shift)} semester${Math.abs(shift) === 1 ? "" : "s"} ${shift > 0 ? "later" : "earlier"}`,
        (l.partial ? "Partial match" : "Full match") + (l.possible ? "; possible (one option of a choice)" : ""),
      ], tipDescs([l.source.row, l.target.row]));
    },
    detail: (panel, n) => {
      const extra = n.row._course ? [["Change", changePhrases(n.row._course).join("; ") || "Unchanged from UC"]] : [];
      detailBasics(panel, n, extra);
      const otherName = n.side === "L" ? other.short_name : "the draft";
      panel.append("h4").text(`Counterparts in ${otherName}`);
      if (!n.allLinks.length) { panel.append("p").attr("class", "muted").text("None: no course there matches this canonical course."); return; }
      const ul = panel.append("ul");
      for (const l of n.allLinks) {
        const p = n.side === "L" ? l.target : l.source;
        const s = p.sem - n.sem;
        const hidden = state.areas.has(p.area.key) ? "" : ", hidden by the filter";
        ul.append("li").text(`${rowLabel(p.row)}${p.row.course_code ? ` ${p.row.title}` : ""}: semester ${p.sem} ` +
          `(${s === 0 ? "same semester" : `${Math.abs(s)} ${s > 0 ? "later" : "earlier"}`})${l.partial ? ", partial" : ""}${l.possible ? ", possible" : ""}${hidden}`);
      }
    },
  }, left, right);
  renderVsTable(d, other, left, right);
}

// UC-or-draft vs school status of one canonical course, from each side's first
// semester (the symbols of the Course-level alignment table). `mine` names the left side.
function statusOf(hasL, hasR, a, b, mine, other) {
  // d is the semester difference (0 when not comparable), so two statuses can be compared.
  if (!hasL && !hasR) return { cls: "none", d: 0, sym: "", text: "Neither requires it" };
  if (!hasL) return { cls: "absent", d: 0, sym: "✕", text: `${mine} doesn't require; ${other.short_name} does` };
  if (!hasR) return { cls: "uc-only", d: 0, sym: "◆", text: `Only ${mine} requires` };
  if (a === b) return { cls: "same", d: 0, sym: "=", text: "Same semester" };
  const n = `${Math.abs(b - a)} semester${Math.abs(b - a) === 1 ? "" : "s"}`;
  return a < b ? { cls: "earlier", d: b - a, sym: "▲", text: `${mine} ${n} earlier` }
    : { cls: "later", d: b - a, sym: "▼", text: `${mine} ${n} later` };
}

// The alignment table for section 3: one row per canonical course required (in a shown
// subject area) by UC today, the draft, or the school, with UC today's status and the
// draft's status against the school. A row whose status changed is shaded.
function renderVsTable(d, other, draftAll, schoolAll) {
  // Map(canonical_id -> [{row, m}]) over one side's placed rows in shown areas.
  const byCanon = (rows) => d3.group(rows.filter((r) => r.norm_semester !== null && state.areas.has(r.subject_area))
    .flatMap((r) => r.matches.map((m) => ({ row: r, m }))), (e) => e.m.canonical_id);
  const today = byCanon(uc.academic);
  const draft = byCanon(draftAll);
  const school = byCanon(schoolAll);
  const ids = [...new Set([...draft.keys(), ...school.keys(), ...today.keys()])];
  // d3.min over each entry's semester; ?? 99 sorts "not required" last.
  const first = (es) => (es ? d3.min(es, (e) => e.row.norm_semester) : null);
  ids.sort((a, b) => (first(draft.get(a)) ?? 99) - (first(draft.get(b)) ?? 99) || (first(school.get(a)) ?? 99) - (first(school.get(b)) ?? 99));

  const key = d3.select("#vs-key");
  key.selectAll("*").remove();
  for (const [cls, sym, text] of [["earlier", "▲", "earlier than the school"], ["later", "▼", "later"], ["same", "=", "same semester"],
    ["absent", "✕", `not required (${other.short_name} requires it)`], ["uc-only", "◆", `required only on the UC / draft side`]]) {
    const k = key.append("span").attr("class", `status ${cls}`);
    k.append("b").attr("aria-hidden", "true").text(sym);
    k.append("span").text(text);
  }

  const rowsText = (es) => (es ? es.map((e) => `${rowLabel(e.row)} (sem ${e.row.norm_semester}${e.m.match_role === "one_of" ? ", possible" : ""})`).join(", ") : "—");
  const table = d3.select("#vs-table");
  table.selectAll("*").remove();
  table.append("thead").append("tr").selectAll("th")
    .data(["Canonical course", `UC today vs ${other.short_name}`, `Draft vs ${other.short_name}`, "Draft", other.short_name])
    .join("th").text((h) => h);
  const items = ids.map((id) => {
    const t = statusOf(today.has(id), school.has(id), first(today.get(id)), first(school.get(id)), "UC", other);
    const n = statusOf(draft.has(id), school.has(id), first(draft.get(id)), first(school.get(id)), "Draft", other);
    return { id, t, n, changed: t.cls !== n.cls || t.d !== n.d };
  });
  const tr = table.append("tbody").selectAll("tr").data(items).join("tr").classed("changed", (x) => x.changed);
  tr.append("td").each(function (x) {
    const td = d3.select(this);
    td.append("span").text(canonById.get(x.id)?.name || x.id);
    if (x.changed) td.append("span").attr("class", "changed-mark").text(" · changed");
  });
  for (const k of ["t", "n"]) {
    tr.append("td").each(function (x) {
      const s = x[k];
      const cell = d3.select(this).append("span").attr("class", `status ${s.cls}`);
      cell.append("b").attr("aria-hidden", "true").text(s.sym);
      cell.append("span").text(s.text);
    });
  }
  tr.append("td").text((x) => rowsText(draft.get(x.id)));
  tr.append("td").text((x) => rowsText(school.get(x.id)));
}

// ---------------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------------

// Load every school's table, pick out UC's rows, then open the last-used draft (or
// make a first one, so the user can start dragging right away) and draw.
loadAllSchools()
  .then((loaded) => {
    data = loaded;
    canonById = new Map(data.canon.map((c) => [c.canonical_id, c]));
    const ucRows = data.rows.filter((r) => r.school.school_id === "uc");
    uc.academic = ucRows.filter((r) => r.norm_semester !== null);
    uc.coop = ucRows.filter((r) => r.is_coop);
    uc.school = data.schools.find((s) => s.school_id === "uc");
    baseByKey = new Map(uc.academic.map((r) => [keyOf(r), r]));
    // Semester -> UC's year and term for it, from the first UC row in that semester.
    semInfo = new Map(d3.range(1, 9).map((s) => {
      const r = uc.academic.find((x) => x.norm_semester === s);
      return [s, { norm_year: r.norm_year, norm_term: r.norm_term, orig_year: r.orig_year, orig_term: r.orig_term }];
    }));

    store = loadStore();
    if (!store.drafts[store.current]) {
      const any = Object.values(store.drafts)[0];
      if (any) openDraft(any.id); else createDraft("Draft 1");
    }
    setupDialog();
    setupControls();
    renderAll();
    flash(storageOk ? "Drafts are saved in this browser." : "");
  })
  .catch((err) => showLoadError("main", err));
