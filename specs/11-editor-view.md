# 11 — Curriculum Editor View

A web page where the user drafts revised versions of UC's curriculum and compares each
draft with UC as it is and with any comparison school. Requested by the user on
2026-10-20. Choices marked *(default)* were made without asking and can be changed.

## Purpose

Let the curriculum committee try "what if" changes to UC's 4-year (normalized) plan:
remove a course, move it to another semester, revise its title and description, or add a
new course. Then see what changed and how the draft lines up with other schools.

## Page

`web/editor.html` + `web/editor.js`, nav label **Curriculum editor** (after Timeline,
before the review pages; Process stays last). Three sections, top to bottom:

1. **Editor**: the draft's 8 semesters and a Removed area.
2. **UC today vs the draft**: what moved, what was added, what was removed.
3. **The draft vs a school**: the draft next to one comparison school, as in the
   Course-level alignment view.

One **subject-area filter** (the six checkboxes used on the other views) at the top of
the page applies to all three sections *(default: one shared filter, so the three
sections always show the same areas)*.

## Co-op switch

Added by the user on 2026-10-20. A two-way switch at the top, as on Course Plans,
applies to all three sections and is kept in the URL (`?coop=1`):

- **Academic semesters (4 years)** (default): Years 1-4 with Semesters 1-8; each
  semester shows UC's own year and term under it ("UC Year 5 Fall").
- **All terms, with co-op (5 years)** (the label counts all of UC's plan years): UC's real calendar, Years 1-5 with each year's
  terms in order (Fall, Spring, Summer). An academic term is headed by its term name
  with its semester number under it; co-op terms sit in their place as shaded, fixed
  cards (not drop targets). Both charts show the co-op terms in their slots, as in the
  alignment views (shaded, never linked, faded, or tagged).

The draft still stores semesters 1-8; the switch only changes how they are laid out.

## Drafts ("revised curricula")

- A draft starts as a copy of UC's 8 academic semesters (co-op work terms are not
  editable and are left as they are; the page says so).
- The user can keep **several named drafts**, shown on the page as **versions**
  (revised 2026-10-20 at the user's request, "a clear way to save a version and switch
  to it"). A **Versions** panel above the editor has one card per version: name, when
  it was last saved, how many courses differ from UC, and how many problems the checks
  find; the open version is highlighted ("Open now: edits save here"), and clicking
  another card switches to it. **Save as new version** asks for a name inline, saves a
  copy of the open version under it, and switches to the copy, so the version you were
  in stays as it was. Also: New from UC, Rename (the name field), Delete (two clicks). **Reset to UC** (user, 2026-10-24) puts the open
  version's courses back to UC's current plan, keeping its name; it takes two clicks
  (the first turns it into "Confirm reset") and is one Undo step.
- **Every change is saved automatically** to the current draft *(default: no separate
  Save button, so nothing is lost on reload)*. Undo and Redo (also Ctrl/Cmd+Z and
  Shift+Ctrl/Cmd+Z) cover the session's changes.
- **Storage:** the viewer's browser (`localStorage`), since the site is static (GitHub
  Pages) and has no server. Drafts made on one device are not seen on another, so
  **Export** downloads all drafts as one JSON file and **Import** reads such a file back
  (a name that already exists gets " (imported)"). An exported file can also be added to
  the repo later if a draft should become project data.
- A draft stores its full course list (not a list of edits). Each course keeps the key
  of the UC row it came from (`course_code` or slot title, plus its original semester),
  or none for an added course. Changes are worked out by comparing with UC's current
  table, so they always trace to `data/processed/uc/required_courses.json`. If a stored
  key no longer exists in that table, the page warns.

## Editing

**Every course can be edited** (user, 2026-10-23, replacing the 2026-10-20 rule that
only CS courses could be). Any UC course in the 8 academic semesters (CS, math,
science, engineering, writing, gen ed) can be moved, removed, and revised, including its
subject area, and an added course can be in any subject area (CS is preselected). Only
co-op terms are fixed. The "Fixed course" check and its "put the non-CS courses back"
button are gone with the rule.

- **Move:** drag a course card to another semester (or to another place in the same
  semester, which only changes the order). Cards can be dragged with a mouse; on a touch
  screen, press and hold a card, then drag. A drop marker shows where the card will go.
- **Remove:** drag a card into the **Removed** area. A removed card shows its code,
  title, credits, and where it used to be ("Was: Semester 3 · UC Year 2 Spring");
  clicking it shows its description. Dragging it back into a semester restores it there.
  An added course dragged to Removed is deleted (Undo brings it back).
- **Revise:** click a card to open its editor: course code, title, credits (a number or
  a range like 4-5), subject area, semester (or Removed), canonical course, and
  description. The original UC title, semester, and description are shown for reference,
  with "Restore UC original".
- **Add:** "Add a course" opens the same editor, empty. A title is required.
- The editor's semester and Removed fields do the same as dragging, so every edit also
  works from the keyboard and without drag and drop.
- Cards look like the Course Plans cards (height ~ credits, area stripe, dashed for
  requirement slots). A changed card is tinted and outlined in its change color and
  carries a symbol in its top line (revised 2026-10-22 at the user's request, "I want
  the changes to stand out a bit more"): **＋ new** (blue), **▲/▼ n moved** n semesters
  earlier or later (purple), **✎ edited** (amber: title, code, credits, area, canonical
  course, or description changed; the tooltip names which), **✕ removed** (red, in the
  Removed area). A course can show both a move and an edit; the first symbol sets the
  tint. A legend sits above the semesters. Problem tags (⚠ prereq...) stay at the
  bottom of the card, and a problem's red border wins over the change outline.
  Each semester shows its credit total and, when it differs, UC's.

### Descriptions written in the editor

A description typed in the editor is not UC's catalog text. The card shows it as an
edit (✎; the tooltip says "description written in this draft, not UC's catalog text"),
and the description heading says "written in this draft, not UC's catalog text" wherever
it appears, the same way generic descriptions are always labeled. (Until 2026-10-22 it
had its own PROPOSED badge beside REVISED; the user found the two hard to tell apart, so
they were merged into one "edited" mark.) A course whose description was not changed keeps UC's
text and its label (official or generic).

### Canonical course

The canonical course decides what a course links to in section 3. A UC course keeps its
reviewed matches unless the user picks another canonical course in the editor. An added
course has none until one is chosen (then it links to every school course that matches
it). A user-chosen match is labeled "chosen in this draft".

## Checks

Added by the user on 2026-10-20. A Checks box above the semesters lists every problem
in the draft; the checks **warn but don't block** *(default)*, so a committee can still
look at a plan that breaks a rule. Cards with a problem get a red border and a tag
(⚠ prereq, ⚠ standing), a semester outside the credit limits gets a ⚠ by its
total, and the course editor lists the course's prerequisites and warnings.

- **Credits per semester:** outside the limits, default **12–18** *(default: 12 is the
  usual full-time minimum, 18 a common cap before an overload needs approval; UC's own
  plan has 15–17)*. The viewer can change both numbers on the page; they are saved in
  the browser with the drafts. A credit range counts as over if its top is over, and
  under if its bottom is under.
- **Prerequisites:** a course placed in the same semester as, or before, a prerequisite,
  or whose prerequisite is removed. Read from UC's catalog by `src/parse_uc_prereqs.py`
  into `data/processed/uc/prerequisites.json`; the reading rules are in that script
  ("A,B, or C" = (A and B) or C; only alternatives whose courses are all in UC's plan
  are checked; a placement-test alternative means no in-plan check). UC's own plan must
  pass, or the script stops. Added courses have no prerequisites.
- **Class standing:** "Be at least a Sophomore" etc. in the catalog text, read as
  semesters 3+ (Junior 5+, Senior 7+; "First Year Student" 1–2).

## Section 2: UC today vs the draft

- A two-axis view like the Course-level alignment view: **UC today on the left, the draft
  on the right**, by semester, node height = credits, the same semester labels.
- A line joins a UC course to its own copy in the draft. Line color and symbol say how it
  moved: green ▲ moved earlier, red ▼ moved later, gray = same semester (the same tokens
  as the alignment table).
- **Removed** UC courses have no line, are faded, and are tagged REMOVED. **Added**
  courses are tagged NEW; edited ones EDITED.
- Hover a course or line for details; click to pin and see the details panel.
- Below the view, a **changes table**: one row per changed course (Removed, Added, Moved
  earlier, Moved later, Edited), with the course, where it was, where it is now, and
  what changed (e.g. the old and new title). A summary line counts each kind. A second
  small table shows credits per semester, UC vs the draft.

## Section 3: the draft vs a school

- School picker (every school but UC). The same two-axis view, **the draft on the left**,
  the school on the right, linked by shared canonical courses as in
  `06-alignment-view.md` (dashed partial, dotted possible). Courses with no counterpart
  are faded. NEW / EDITED tags show on the draft side.
- Co-op terms follow the co-op switch (see "Co-op switch").
- Below, a table per canonical course at either side: the status of **UC today vs the
  school** and of **the draft vs the school** (▲ earlier, ▼ later, = same, ✕ the draft
  doesn't require it, ◆ only the draft requires it), with "changed" marked where the
  draft's status differs from UC's, and each side's courses.

## Out of scope (for now)

- Editing co-op terms, other schools' plans, or prerequisites (they are checked, not edited).
- Sharing drafts between viewers (it would need a server or a shared store).
- Concept-level comparison of drafts (added courses have no concept tags).

## Check

The user creates two drafts, moves, removes, revises, and adds courses, reloads the page
(drafts kept), and looks at both comparisons with the subject filter. Also: no
horizontal page scroll at phone width (the charts scroll in their own box), light and
dark mode, and no console errors.
