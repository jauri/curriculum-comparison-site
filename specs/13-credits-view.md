# 13 — Credits View

Credits each school's plan requires in each subject area, one bar chart per area.
Requested and designed with the user on 2026-11-20.

## Purpose

Show how each degree divides its credits among computing, math, lab science,
engineering & co-op prep, writing, and general education & free electives, and where UC
sits in each.

## Data

- No new data or Python step. The page reads `data/processed/schools.json` and each
  school's `<id>/required_courses.json` through `loadAllSchools()` (`web/common.js`), so
  hidden schools (CMU, Pitt) are left out, as on every view.
- A school's credits in an area are the sum of `credits_min` (and, separately,
  `credits_max`) over its rows with that `subject_area`, leaving out co-op rows and
  rows with `counts_toward_total = false`. This is the same rule as the Course Plans
  legend (`creditSum` in `web/index.js`), and the area sums add up to each school's
  stated total in `schools.csv` (checked 2026-11-20).
- Areas, labels, and colors are `AREAS` in `web/common.js`.

## Layout (chosen with the user)

- Page `web/credits.html` + `web/credits.js`, nav link "Credits by area" after
  Categories.
- Six charts, one per area, in `AREAS` order. **Vertical columns** (the user's choice
  over horizontal bars): one column per school, names rotated under the axis. On a
  narrow screen each chart scrolls sideways in its own box.
- **UC is always the first column**, set apart by a gap and a thin rule, with its name
  in bold and its value printed above the column. The other schools follow, **sorted
  from most credits to fewest** in that area (the user's choice); ties sort by name.
- Every column is the area's color (color is the area, not the school). A credit range
  (e.g. UC's 8–10 lab science credits) is a solid column to the low end and a lighter
  cap to the high end. Schools sort by the low end.
- A dashed line marks the **median of the other schools** (low end), labeled with its
  value, so UC can be read against the typical school.
- Each chart has its own y scale (computing runs to ~75 credits, writing to ~12).
- Hover (or focus) a column: school, credits, share of the school's degree total, the
  number of rows (courses and slots) behind it, and (added 2026-11-20 at the user's
  request) the list of those courses and slots, one line each with its credits
  (identical slots merged with ×count, long names cut with …), ending "Click for
  sources and details".
- A table under the charts gives every number: one row per school (UC first, then
  alphabetical), one column per area, plus the degree total.

## Evidence (added 2026-11-20, chosen with the user)

The user asked for evidence behind every count: a link to the program and a reason.

- **Data:** `src/build_sources.py` copies, for each displayed school, the source records
  (URL, description, retrieval date from `data/raw/<id>/sources.csv`) of the files its
  plan rows cite (`source_file`) and of the file that states the degree total
  (`credits_source`, newest snapshot). Writes `data/processed/sources.json`; fails if
  any of those files has no URL. Run it after any school's `build_outputs.py`.
- **Layout (the user's choice over a per-school section):** clicking, tapping, or
  pressing Enter on a column opens an evidence box under that chart; each number in
  the table is a button that opens the same box. The chosen column keeps an outline.
- **The box shows:** the plan source link(s); the stated degree total and where it is
  stated ("the same plan" when one page gives both); program, catalog year, and the
  school's `schools.csv` note; one sentence giving the reason ("N = the sum of the K
  rows below ... counted at the credits the plan gives it", with the share of the
  degree); a table of those rows (identical slots merged with ×count; a choice slot's
  options or the row's note under it) with a total line; any rows in the area left out
  of the stated total, with their note; and a link to `subject_areas.csv` for why a
  course sits in an area. Only http(s) URLs become links.
