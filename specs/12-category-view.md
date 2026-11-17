# 12 — Category View

The timeline view (`07-timeline-view.md`) grouped into major categories of computing
courses. Requested and designed with the user on 2026-11-16.

## Purpose

Let the committee read the computing curriculum by area (fundamentals, systems,
specialty areas, ...) instead of one long list: within each area, which courses schools
require, when, how common each is, and where UC is missing, early, or late.

## Categories (data)

- `data/reference/course_categories.csv`: one line per category (`category_id`, `name`,
  `order`, `description`, `notes`). `data/reference/category_members.csv`: one line per
  canonical course placed in a category (`canonical_id`, `category_id`, `notes`). Both
  hand-reviewed; a canonical course is in at most one category.
- `src/build_categories.py` checks them against `canonical_courses.csv` (unknown ids,
  duplicates stop the build), writes `data/processed/course_categories.json`, and prints
  the computing-area canonical courses that no category holds.
- Categories chosen with the user (computing only; the user's choice of scope):
  1. **Computing Fundamentals**: orientation, CS1, Programming II, programming
     practicum, Python, functional programming, computational problem solving, and
     **Programming Languages** (the user's choice, over Theory).
  2. **Data Structures & Algorithms**.
  3. **Theory & Discrete Math**: discrete math, intro to proofs, theory of computation.
  4. **Systems**: digital logic, electronics, computer organization, systems
     programming, operating systems, networks.
  5. **Software Development**: software engineering, team project, capstone.
  6. **CS Specialty Areas** (the user's name, over "Topics in Computing"): databases,
     AI, graphics, information security, data science foundations, numerical methods.
- Not in any category (not drawn, named in the page note): computing ethics, senior
  seminar, experiential learning, and the CS and technical elective slots. Writing,
  gen-ed, math, science, and elective categories were proposed and left out by the user.

## Layout

- Page `web/categories.html` + `web/categories.js`, linked from every page's nav
  ("Categories", after Timeline). It loads `timeline.js` for the strip model and drawing
  (`buildStrips`, `drawStrip`, `drawHeads`, `ucFlags`, `otherShare`, the follow and
  legend setup), so dots, share bars, UC flags, and the tooltip are the timeline's.
- **One shaded band per category** (the user's choice: bands with sub-bands only, no
  combined category row and no collapsing), in the CSV's order, under a heading with the
  category name only (a summary, "8 courses · UC requires 4 · 3 UC flags", was built and
  then removed at the user's request, 2026-11-16).
- **One sub-band per canonical course** in the band: the timeline strip, with its share
  bar and percent of the other schools, UC's placement, the "course not required" bin,
  and UC's flag (missing / early / late / few others, same rules as spec 07), or the gray
  "not in UC plan" note when UC lacks a course without a ✕ flag.
- Within a band, courses are ordered by typical semester (median of each school's
  earliest full-match semester), then by share of other schools, then by the order in
  `category_members.csv`. Canonical courses no school requires are left out.
- Hover a dot to follow that school in every band; click or the picker pins it.
- Companion table: category, canonical course, share, UC semester(s), UC flag with
  evidence.

## Check

The user opens `web/categories.html`, hovers dots to follow a school across bands, and
confirms UC stands out and the flags match the timeline's.
