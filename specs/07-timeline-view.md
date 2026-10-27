# 07 — Timeline View

A web view that shows, for every computing, engineering, and math canonical course,
**when** each school schedules it in the normalized 4-year sequence and **which schools
don't require it at all**, with UC highlighted. Decisions below were made with the user
on 2026-10-17 (after step 13). The alignment view (`06-alignment-view.md`) compares UC
with one school; this view compares UC with all fifteen at once, one topic at a time.

## Purpose

Let the curriculum committee see at a glance:

- how common each course is across the comparison set (16 of 16 schools, or 3 of 16),
- whether schools agree on when it is taken, and where UC falls in that spread,
- which courses UC lacks that other schools require, and which UC requires that most
  others don't.

## Layout

- A D3 (SVG) view in a new page `web/timeline.html` + `web/timeline.js`, linked from the
  other pages' nav.
- **One strip per canonical course.** A strip is a horizontal line spanning normalized
  semesters 1–8, with a tick per semester and a label per year (Year 1 … Year 4). The
  canonical course name sits at the left of the strip, with the share bar below it.
- **Share bar** (the user's request): under each course name, a 60px bar shows the share
  of the 15 comparison schools (UC excluded; the user's choice) that require the course,
  in neutral ink, with a lighter extension for schools where it is only one option of a
  choice, followed by the percent ("73%", "+2 possible") and UC's placement. The bars
  line up down the page, so strips compare at a glance. The table's count column gives
  the same numbers ("11 of 15 (73%)").
- **One dot per matched row** (the user's choice): each row of a school's required
  courses that matches the canonical course draws one dot at the row's `norm_semester`.
  A school that schedules the course in several semesters (e.g. four semesters of
  language) draws several dots. A row that matches several canonical courses (CMU
  15-213: computer organization + operating systems) draws a dot in each strip.
- **Dots in the same semester stack** upward from the line. Stack order is fixed: UC
  first (so it always sits on the line), then the other schools in registry order
  (`schools.csv`: group, then the order listed). The same school is therefore at a
  predictable height, and the picture is deterministic. A strip's height grows to fit
  its tallest stack.
- **"Course not required" bin** (renamed from "No course" at the user's request), to
  the right of semester 8, separated by a rule: one dot per school with no row matched
  to the canonical course, laid out in a small grid in the same order. The strip label's
  count ("12 of 16 schools") gives the number. The view compares **required** courses
  only: it does not check whether a school (UC included) offers the course as an
  elective. A UC-only catalog check ("not required" vs "not offered") was built and then
  removed at the user's request, to keep the view to the degree plans.
- Rows with no normalized semester (co-op terms) are left out, as in the alignment view;
  the page says so. A canonical course whose rows all lack a semester
  (`coop-work-term`) is listed in a note instead of drawn.

## Marks

- **UC is highlighted**: its dots use an accent color with a ring and are drawn on top;
  every other school's dots are one neutral color. (Fifteen distinct school colors
  would not be readable; the school is in the tooltip.) UC's dot in the "course not required" bin
  gets the same highlight, since that is the case the committee most needs to see. The
  strip label also states UC's placement ("UC: semester 3", or "UC: not required").
- Match types use the alignment view's conventions:
  - `covers`: filled dot.
  - `partial_match = true`: half-filled dot.
  - `one_of` (a real choice, e.g. "OS or Networks"): hollow dot, tooltip says "possible".
    The school is not in the "course not required" bin, since students may take it.
  - `all_of_group` (timing flexibility): filled dot at the row's own semester; the
    tooltip names the group's other semesters.
- A legend above the view explains UC vs other schools, filled / half / hollow, and the
  "course not required" bin.

## UC flags

Added 2026-10-24 at the user's request: a glyph that says where UC differs from most of
the other 15 schools. Style and rule are the user's choices (glyph + gap size; the
percentile rule, with two thirds as "most").

- **Rules** (computed in the browser from the same fields as the strip; a "possible"
  match, one option of a choice, never counts as requiring the course):
  - ✕ **missing**: UC doesn't require the course, not even as an option, and at least
    two thirds of the other schools (10 of 15) do.
  - ◀ **early** / ▶ **late**: compare UC's earliest semester with each other school's
    earliest full-match semester. Early if at least two thirds of those schools take it
    later than UC; late if at least two thirds take it earlier. Ties count as
    neither. There is no dead zone, so a one-semester gap counts. It is only judged when
    at least 5 other schools require the course. The label gives the gap: UC's semester
    minus the others' median ("▶ 1 sem late").
  - A course carries at most one flag. Slots are flagged by the same rules.
  - A fourth flag, ◆ **UC only** (UC requires it, at most a third of the others do), was
    built and then removed at the user's request (2026-10-24): it didn't make sense on
    the page.
- **Where:** in its own column at the far right, after the "course not required" bin,
  headed "UC vs. most other schools", on the name's line (moved there from the label
  at the user's request, 2026-10-24).
  Hovering the glyph shows the evidence ("UC: semester 4; 11 of 14 other schools take
  it earlier (median semester 3)"). The legend lists the three glyphs, and the companion table has a "UC flag" column that spells out each flag and its
  evidence.
- A dashed tick at the other schools' median semester on early or late strips was built
  and then dropped at the user's request (2026-10-24): it ran through the dot stacks and
  read as unexplained; the flag text already gives the gap.
- **Caveat:** "missing" means UC has no required course *matched to this canonical
  course*. UC may teach the material inside another course (concept mode would show this).

## Sections, sorting, and filtering

- **Courses first, slots second.** Canonical courses with `kind = course` are the main
  section, one list whether or not UC requires them (UC's dot sits in the "course not
  required" bin when it doesn't). Slots (`cs-elective`, `math-science-elective`, …) are a
  second section, collapsed by default, since a slot can put up to eight dots per school
  in one strip. (A split into "UC's required courses" and a collapsed "Courses UC doesn't
  require" was built and then reverted at the user's request.)
- **Sort** (a control, one choice at a time):
  - by typical year (default; the user's request after the first build): each school's
    earliest full-match semester, the median across schools, and that semester's year.
    Strips sit under "Typically year 1" ... "Typically year 4" headings, ordered within
    each year by the percent of the other schools that require the course (the share
    bar's percent), highest first (the user's choice), then by "+N possible". A course only ever matched as one option
    of a choice goes under "Only as an option",
  - by area (Computing, Engineering & co-op, Math, in that order), then canonical name,
  - by how many schools require it (most common first).
- **Three areas only** (the user's choice): the view shows canonical courses in
  **Computing** (area `cs`, which already includes IT courses such as UC's IT 2030C),
  **Engineering & co-op prep** (`eng`: first-year engineering, co-op preparation), and
  **Math & statistics** (`math`). Lab science, writing, and general education are left
  out entirely, and the page says so. This applies to slots too: the slot section shows
  only slots in these areas (`cs-elective`, `technical-elective`, `capstone-design`,
  `math-science-elective`).
- **Area filter**: three toggle buttons ("Computing", "Engineering & co-op",
  "Math & statistics"), styled as checkbox buttons, with only Computing on by default (the user's choice), any combination
  allowed, so the reader can turn off the other two and see computing alone. Strips
  hide and the remaining ones close up (no gaps).
- The area of a canonical course is the most common `subject_area` of its matched rows
  (ties: palette order), computed in the browser from the step 14 column. A strip is
  shown if its area is one of the three and its button is on. Dots keep every matched
  row, even one whose own row is in another area (e.g. an engineering school's ECE
  course matched to `digital-logic`, a computing concept).

## Interaction

- **Hover a dot**: a tooltip with school, course code, title, semester (with year and
  term), credits, match role (and "partial" or "possible"), and the description,
  shortened to about 320 characters with the GENERIC badge when generic. A "course not required"
  dot's tooltip names the school and says it has no required course matched to this
  canonical course.
- **Follow a school**: hovering a dot also highlights that school's dots in every strip
  and dims the rest lightly, so a reader can trace one school down the page. Clicking a
  dot pins this; clicking it again, clicking empty space, or pressing Escape unpins.
  A school picker above the view does the same thing without hovering.
- Keyboard: dots are focusable (Tab), Enter acts like a click.

## Accessible companion

Under the view, a table with one row per canonical course: name, number of schools,
UC's semester(s), each other school's semester(s), and the schools that don't require it. It
respects the sort and the area filter, like the alignment view's table.

## Data

- The page reads `data/processed/all_required_courses.json` (step 14),
  `data/processed/canonical_courses.json`, and `data/processed/schools.json`. Everything
  shown is a field of those files or a count of them; the page adds no judgment of its
  own.
- Subject areas come from the rows' `subject_area` column (step 14), not from a map in
  the page.

## Later: concept mode

When the concept table exists (`08-concepts.md`), the page gets a toggle between
**canonical courses** and **concepts**. In concept mode a strip is one concept, a dot is
one row tagged with it, and the tooltip shows the evidence phrase highlighted in the
description. Everything else (stacking, UC highlight, "course not required" bin, follow a school)
stays the same.

## Out of scope (for now)

- Credit-weighted dots (all dots are one size).
- Comparing two catalog years of the same school.

## Check

The user opens `web/timeline.html`, tries each sort, the area buttons (computing
alone), hover, and following a school, and confirms UC stands out in both the semester
stacks and the "course not required" bin. Also checked: no horizontal page scroll at phone width (the strips may
scroll inside their own container), and light and dark mode.
