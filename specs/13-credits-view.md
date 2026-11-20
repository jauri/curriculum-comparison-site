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
- Hover (or focus) a column: school, credits, share of the school's degree total, and
  the number of rows (courses and slots) behind it.
- A table under the charts gives every number: one row per school (UC first, then
  alphabetical), one column per area, plus the degree total.
