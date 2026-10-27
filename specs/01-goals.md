# 01 — Goals

## Purpose

Build a clean, comparable data table of the **required courses in the University of
Cincinnati (UC) Computer Science BS**, so it can later be compared against CS programs at
other universities.

UC's CS degree is a **5-year program with mandatory co-op**: academic semesters alternate
with co-op work semesters. Most peer programs are 4 years with no built-in co-op. The UC
data must therefore be normalized so that "when a course is taken" means the same thing
across programs.

## Phase 1 scope (this project, now)

1. Gather UC CS required courses into a data table.
2. Normalize UC's 5-year co-op timeline to a 4-year academic equivalent.
3. Add a description to each course, either:
   - the **official** UC catalog description, or
   - a **generic** description typical of courses with that title in a CS (or related)
     department, when an official one is not available.

## Out of scope for phase 1

- Gathering data on other universities. That is phase 2; see `05-comparison-set.md`. The
  table design should anticipate it.
- Topic-level or learning-outcome analysis of course content.
- Visualizations and reports beyond inspecting the table.

## Definition of done (phase 1)

- A single table (see `04-outputs.md`) lists every required course in the UC CS BS plan
  of study, with UC's original term placement and the normalized 4-year placement.
- Every course has a description, and every description is labeled as `official` or
  `generic`. Official descriptions include a source URL.
- The normalization rules are written down (`03-processing.md`) and applied by a script,
  not by hand, so they can be rerun and audited.

## Open questions

- [x] Catalog year: **2026–27** (current). UC publishes plans per cohort, so this means
      the Class of 2031 (entering Fall 2026), Section I; see `02-data.md`.
- [x] "Required" includes named required courses **and** requirement slots (CS electives,
      math/science electives, gen-ed buckets) as placeholder rows, so credit totals match
      the degree total.
- [x] Comparison set: see `05-comparison-set.md` (15 semester schools: Ohio public peers +
      aspirational programs).
