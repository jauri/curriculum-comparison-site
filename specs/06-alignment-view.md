# 06 — Alignment View

A web view that shows how UC's required courses line up with one other school's,
course by course and semester by semester. Decisions below were made with the user
on 2026-10-17 (before step 11). The tab is labeled **Course-level alignment** (renamed
2026-10-20, to set it apart from the Concept alignment tab).

## Purpose

Let the curriculum committee see at a glance:

- which UC courses have a counterpart at another school, and which don't (on either side),
- whether a shared topic is taken earlier, at the same time, or later at the other school,
- how the picture changes when focusing on one area (e.g. CS only, or CS + math).

## Layout

- A two-axis parallel coordinate view drawn with D3 (SVG), in a new page
  `web/compare.html` + `web/compare.js`, linked from the other pages' nav.
- **Left axis: UC. Right axis: one comparison school**, chosen with a picker (every
  school in `data/processed/schools.json` except UC).
- **Vertical position = normalized semester.** Both axes are split into 8 semester
  bands, top to bottom. Band *k* has the same height and position on both sides (the
  larger of the two schools' credit totals for that semester), so semester *k* lines up
  horizontally. Bands are labeled on both sides with each school's own term (see
  "Labels per side").
- **Nodes are course and slot rows** (named courses, electives, gen-ed slots, choice
  slots). Co-op rows have no semester and are left out; the page says so.
- **Node height is proportional to credits**, the same scale as the 4-year plan view.
  A node shows its code (or slot title) and as much title as fits; the full text is in
  a hover tooltip. Slots have dashed borders and the GENERIC badge, as in the plan view.
  Rows with `counts_toward_total = false` are marked "not counted".
- **Within a semester band**, nodes are ordered so that linked courses sit across from
  each other where possible (see "Ordering").

## Co-op terms

Added at the user's request on 2026-10-20, for this view and the concept alignment view
(`10-concept-alignment-view.md`).

- A **"Show co-op terms"** checkbox, off by default (kept in the URL as `&coop=1`). Off,
  the view is the 8 normalized semesters described above.
- On, each school's **co-op work terms** (`is_coop` rows) are drawn in their place
  between academic semesters, as shaded rows. A co-op term goes after semester *k*, where
  *k* is the highest normalized semester among the academic terms before it in the plan
  (so Northeastern's half-term pairs count once). Several co-op terms after the same
  semester (Northeastern's Spring + Summer 1) get one slot each.
- The two sides share one slot list: after semester *k* there are as many co-op slots as
  the side with more co-op terms there needs. A school with **no co-op term** at that
  point gets an empty dashed "No co-op term" box, so semester *k* stays across from
  semester *k* on both sides. Today only UC and Northeastern have co-op terms.
- **Labels per side:** each side has its own label gutter (UC left, the other school
  right) showing that school's own term from its plan, e.g. UC's semester 3 is "Year 2
  Spring" while OSU's is "Year 2 Autumn". Since 2026-10-20 this holds with co-op off too
  (the user's request), so UC's real year and term are always shown and its later years
  don't look like a data error. With co-op off, a semester right after a co-op term gets a
  third line, "after co-op". (Before, co-op off had one left gutter with the normalized
  "Year 2 Fall".)
- Co-op boxes are a fixed height (0 credits) in the co-op color. They ignore the subject
  filter (the checkbox controls them). Co-op terms match the canonical `coop-work-term`,
  so UC's and Northeastern's co-op terms link to each other (many-to-many). A link with
  a co-op end has no semester shift.
- Built in `web/common.js` (`termSlots`, `coopGaps`, `drawSlotBands`) and used by both views.

## Links

- Two rows are linked when they **share a canonical course** (any of their matches;
  step 13 allows several per row). This is the whole definition of "similar". It comes
  from the reviewed match files, and the page adds no similarity judgment of its own.
  Two rows that share several concepts get one link, listing every shared concept.
- Many-to-many is drawn as is: e.g. UC's four first-year engineering courses link to
  each of OSU's two.
- A link is **dashed if either end's match is partial** (`partial_match = true`).
- A link through a **`one_of`** match (a real choice) is drawn dotted and labeled
  "possible": OSU's "CSE 32X1 (CSE 3231 or CSE 3241)" now links to UC's Software
  Engineering and UC's Databases this way (step 13; it used to map to `core-choice`).
- A link through an **`all_of_group`** match (timing flexibility) is drawn solid and its
  tooltip says the course is taken in one of the group's semesters, e.g. "Berkeley:
  ELENG 64 in semester 4 or 5".
- Links are drawn as smooth curves from the right edge of the UC node to the left edge
  of the other school's node, so a link that slopes down means the other school takes
  the course later.
- **Color = subject area** of the UC node (the same palette as the plan view). When the
  two ends are in different areas (e.g. UIC's CS 277 vs UC's ENGL 4092), the UC side's
  color is used.
- Nodes with **no counterpart** on the other side are drawn with a lighter fill and
  listed under the view in two tables, "UC courses with no OSU counterpart" and the
  reverse (course with area swatch, title, placement, credits; in chart order). Tables
  replaced a run-on sentence list on 2026-10-20 (the user found it hard to read).

## Subject areas and filtering

- The six areas and colors from the plan view (`web/common.js`): Computer science, Math &
  statistics, Lab science, Engineering & co-op prep, Writing, General education.
- One **checkbox per area**, only computer science on by default (as in the concept alignment view), any combination allowed. A node is shown
  if its area is checked; a link is shown if both of its nodes are shown. The view
  re-lays out around the shown nodes (bands shrink, so the chosen areas fill the view);
  semester bands still line up across the two sides. Changed during step 12: leaving
  empty space made a filtered view mostly gaps. A node whose only counterpart is hidden
  still counts as matched (not faded), and the detail panel lists hidden counterparts.
- New subject prefixes for OSU and UIC: CSE → CS; ECE → Engineering (decided with the
  user); ENGR → Engineering; GENED → General education; PHYSICS → Lab science; STAT and
  MATH → Math; ENGL → Writing; UIC's CS → CS.
- New slot concepts: `core-choice` and `software-development-project` → CS;
  `math-science-elective` → Math; `free-elective` → General education (the area's label
  becomes "General education & free electives"). (`core-choice` was retired in step 13.)
- Step 13 prefixes: UT's `C S`, Texas A&M's CSCE, Berkeley's COMPSCI, Northeastern's DS
  and CY → CS; UT's M and SDS → Math; CHEM and PHYS → Lab science; EECE and ELENG →
  Engineering (like ECE); RHE, ENGW, COMM → Writing; UT's GOV → General education. Slots
  `oral-communication` → Writing, `technology-and-society` → General education. A
  choice row whose options span subjects takes its first option's area.
- Step 13 batch 2 prefixes: UIUC's ENG → Engineering; Wisconsin's `COMP SCI`, Minnesota's
  CSCI, Michigan's EECS → CS; STATS and DATASCI → Math; Wisconsin's INTER-LS (career
  development) → Engineering & co-op prep; WRIT and TCHNCLCM → Writing. Minnesota's CSE
  1001 (a college first-year course) → Engineering through an institution-specific
  override, since OSU's CSE is its CS department. Slots `world-language` → General
  education, `capstone-design` (Michigan's capstone slot) → CS.
- Step 13 batch 3 prefixes: CMU's department numbers 07 and 15 → CS, 21 → Math, 76 →
  Writing, 99 (Core@CMU) → General education; Penn State's CMPSC → CS, CMPEN →
  Engineering (like ECE), CAS (speech) → Writing; VT's ENGE → Engineering, CMDA → Math;
  Purdue's MA → Math; Georgia Tech's APPH (wellness) and HIST → General education. Slot
  `first-year-seminar` (Penn State's seminar slot) → General education. CMU codes have no
  space ("15-259"), so a choice row's option subject is the part before the hyphen.

## Interaction

- **Hover a node:** highlight it, every node linked to it, and those links; dim
  everything else. **Hover a link:** highlight it and its two nodes.
- **Hover tooltip** (added at the user's request in step 12): a node's tooltip shows its
  placement, credits, counterpart count, and description; a link's tooltip shows the
  canonical course, both rows' semesters and the shift, and both descriptions.
  Descriptions are shortened (about 320 characters) and keep the GENERIC badge.
- **Click a node:** pin the highlight and open a detail panel with the row's school,
  code, title, semester, credits, and description (GENERIC badge when generic), its
  canonical course (name and description), the match confidence and rationale, the
  options of a choice slot, and its counterparts on the other side (code, title,
  semester). Click it again, click empty space, or press Escape to unpin.
- Keyboard: nodes are focusable (Tab), and Enter acts like a click.

## Ordering within a semester

Barycenter heuristic, a standard way to reduce crossings in a two-layer graph:

1. Start each band in a fixed order: subject area (palette order), then canonical id.
2. Repeat a few times (e.g. 6 passes, alternating sides): sort each band's nodes by the
   average y of their linked nodes on the other side. Unlinked nodes keep their
   current relative position.
3. Stop early if an order stops changing. The result is deterministic (same data →
   same picture).

Nodes never leave their semester band; only their order within the band changes.

## Accessible companion

Under the view, a table lists one row per canonical course present at either school:
canonical name, the share of other schools requiring it, a status, UC rows (code,
semester), and the other school's rows (code, semester). It respects the subject filter.
This is the same pattern as the plan view's full table.

Added 2026-10-20 at the user's request:
- **Status** (UC vs the other school, by first semester), next to the name so differences
  are easy to scan. Symbol, color, and words: green ▲ "UC n semesters earlier", red ▼
  "UC n semesters later", gray = "Same semester", black ✕ "UC doesn't require" (only the
  other school does), blue ◆ "Only UC requires" (the user left this symbol open). A course
  that one side has only in a co-op term gets a gray "–" (no semester to compare).
- **Other schools requiring it**: a small bar and "k/N", where N is every school except
  UC. A school counts if any of its required rows matches the canonical course outright;
  a school whose only matches are one option of a choice (`one_of`) is shown as a lighter
  segment and "(+m)". Counted over all rows, regardless of the subject filter.

## Data

- The page reads `data/processed/schools.json`, `data/processed/<id>/required_courses.json`,
  and `data/processed/canonical_courses.json`, all written by `build_outputs.py`. It needs
  no new pipeline step; links are a join on `canonical_id` done in the browser.
- No value shown is invented by the page; everything traces to the processed tables.

## Out of scope (for now)

- More than two schools at once.
- Topic-level similarity beyond the canonical match.

## Check

The user opens `web/compare.html`, compares UC with OSU and with UIC, and tries the
hover, click, and subject filter. Also checked: no horizontal page scroll at phone width
(the view itself may scroll inside its own container), and light and dark mode.
