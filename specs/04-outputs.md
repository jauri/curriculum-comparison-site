# 04 — Outputs

## Main table: `data/processed/<school>/required_courses.csv`

One row per required course or requirement slot, one file per school (UC's is
`data/processed/uc/required_courses.csv`; it was `uc_cs_required_courses.csv` in phase 1).
Columns are designed so rows from other universities can be appended later with the same
schema.

| Column | Example | Notes |
|---|---|---|
| `institution` | `University of Cincinnati` | Allows multi-school tables later; from `schools.csv` |
| `program` | `Computer Science BS` | |
| `college` | `College of Engineering and Applied Science` | College housing the degree; from `schools.csv`, checked against a saved page |
| `in_engineering_college` | `true` | See `05-comparison-set.md` |
| `catalog_year` | `2026-27` | Phase 1 uses 2026–27 |
| `course_code` | `CS 2028C` | Empty for elective slots |
| `subject` | `CS` | |
| `number` | `2028C` | |
| `title` | `Data Structures` | |
| `credits_min` | `4` | Semester credit hours, low end of the range |
| `credits_max` | `5` | High end; equals `credits_min` for fixed-credit rows (decided in step 7: a range keeps totals exact, e.g. UC's 4–5 credit science slots) |
| `requirement_type` | `required` | `required`, `elective_slot`, `gen_ed`, `coop` |
| `orig_year` | `2` | Year in UC's 5-year plan |
| `orig_term` | `Spring` | Fall / Autumn / Spring / Summer, as the school writes it (Ohio State: Autumn) |
| `orig_term_type` | `academic` | `academic` or `coop` |
| `academic_term_index` | `4` | Position among academic terms only |
| `norm_semester` | `4` | 1–8, 4-year equivalent |
| `norm_year` | `2` | 1–4 |
| `is_coop` | `false` | |
| `counts_toward_total` | `true` | False for a row that is in the plan but not in the stated degree total (UIC's ENGR 100; OSU's placement-dependent CSE 1223). The credit check sums only rows that count. Added in step 10. |
| `description` | `...` | |
| `description_source` | `official` | `official` or `generic` |
| `description_url` | `https://...` | Required when official |
| `canonical_ids` | `computer-organization; operating-systems` | All of the row's matched canonical courses, "; "-separated, in match order. Details for each are in `course_matches.csv` (below). Was a single `canonical_id` before step 13. |
| `match_status` | `proposed` | `proposed`, `approved`, `rejected`: the least-reviewed of the row's matches |
| `notes` | | Anything unusual |

**Optional extra columns** follow the schema columns. Schools may leave them blank:

| Column | Example | Notes |
|---|---|---|
| `plan` | `Class of 2031 Section I` | Which published plan the row came from |
| `orig_calendar_year` | `2028` | Calendar year of the original term |
| `norm_term` | `Fall` | Fall / Spring by normalized position |
| `gened_tag` | `ENC` | Gen-ed category the school tags the course with |
| `min_grade` | `C-` | Minimum grade required, if stated |
| `options` | `CSE 3231; CSE 3241` | For a choice slot ("X or Y"), the option course codes, separated by "; " |
| `choice_kind` | `choose` | For a choice slot: `choose` or `all_in_any_order` (see `03-processing.md`); set by the parser from the source. Added in step 13. |
| `choice_group` | `eleng-66-64` | For `all_in_any_order` rows: id shared by the rows of one group. Added in step 13. |
| `prerequisites` | `...` | Prerequisite statement from the catalog (a matching signal) |
| `source_file` | `data/raw/uc/...html` | Raw plan file the row was parsed from |
| `description_file` | `data/raw/uc/courses/...html` | Saved page (or reference file) the description came from |
| `subject_area` | `cs` | One of the six areas of the web views (`cs`, `math`, `science`, `eng`, `writing`, `gened`), from `data/reference/subject_areas.csv`. Added in step 14. |

## Match table: `data/processed/<school>/course_matches.csv`

One line per (row, canonical course) match, added in step 13 so a row can match several
concepts. Built from `data/reference/<school>/matches.csv`, which has the same match
columns keyed by `match_key`. The JSON for the web views nests these as a `matches` list
on each row.

| Column | Example | Notes |
|---|---|---|
| `match_key` | `CS 3650` | Same key as in the school's `matches.csv` (course code, or slot title) |
| `canonical_id` | `operating-systems` | Link to the canonical course list |
| `match_role` | `covers` | `covers`, `one_of`, `all_of_group` (see `03-processing.md`) |
| `match_confidence` | `medium` | `high`, `medium`, `low`, `new` |
| `match_rationale` | `Second half of the course covers processes...` | One sentence |
| `partial_match` | `true` | True if the course only partly fits this concept |
| `match_status` | `proposed` | `proposed`, `approved`, `rejected` |
| `notes` | | |

## Combined table: `data/processed/all_required_courses.csv`

Every school's `required_courses.csv` stacked into one table (step 14), written by
`src/build_combined.py` with a `.json` copy for the web views. Same columns as the main
table, plus `school_id` first. The JSON nests each row's matches as in the per-school
JSON. Row order: schools in `schools.csv` order, then each school's own row order.

## Subject areas: `data/reference/subject_areas.csv`

The subject-area map that used to live in `web/common.js` (step 14), hand-reviewed. One
line per rule; `build_outputs.py` applies the first rule that fits a row, in this order:
institution + subject override, then subject, then (for slots) canonical slot. A choice
row whose options span subjects uses its first option's subject, as before.

| Column | Example | Notes |
|---|---|---|
| `rule` | `subject` | `institution_subject`, `subject`, or `slot` |
| `institution` | `University of Minnesota, Twin Cities` | Only for `institution_subject` |
| `key` | `CSE` | The subject prefix, or the canonical slot id for `slot` |
| `subject_area` | `eng` | |
| `notes` | | Why, when not obvious (e.g. "Minnesota's CSE 1001 is a college course") |

## Concept tables

Concept vocabulary, per-school concept tags, and coverage outputs are specified in
`08-concepts.md`.

## School registry: `data/reference/schools.csv`

One row per school, hand-reviewed. Shared scripts read program-level facts from here
instead of hard-coding them.

| Column | Example | Notes |
|---|---|---|
| `school_id` | `uc` | Folder name under `data/raw/`, `data/reference/`, `data/processed/` |
| `short_name` | `UC` | Used in messages and notes |
| `institution` | `University of Cincinnati` | |
| `program` | `Computer Science BS` | |
| `college` | `College of Engineering and Applied Science` | As the school writes it in full |
| `in_engineering_college` | `true` | See `05-comparison-set.md` |
| `catalog_year` | `2026-27` | |
| `credits_min`, `credits_max` | `124`, `126` | Stated degree total; the school's parser checks it against the source |
| `credits_source` | `*_cs-bs-majormap-class2031-sec1.html` | Glob in `data/raw/<id>/` for the page stating the total |
| `college_source` | `*_cs-bs-program-detail.html` | Glob in `data/raw/<id>/` for the page naming the college |
| `group` | `home` | `home`, `Ohio public`, or `Aspirational` |
| `notes` | | |

## Canonical course list: `data/reference/canonical_courses.csv`

One row per unique course concept, shared across all schools. Grows as new schools are
processed. This file is hand-reviewed, so it lives in `data/reference/`, not
`data/processed/`, and scripts must never overwrite it silently.

| Column | Example | Notes |
|---|---|---|
| `canonical_id` | `data-structures` | Stable, readable slug; never reused or renamed |
| `name` | `Data Structures` | |
| `kind` | `course` | `course` or `slot` (elective / gen-ed slot) |
| `description` | `Implementation and analysis of lists, stacks, ...` | Generic, written for this project |
| `typical_credits` | `3-4` | Helps matching |
| `first_seen` | `University of Cincinnati / CS 2028C` | Which course created it |
| `notes` | | E.g., common splits or merges |

## Match review

- A review view (web page, `web/review.html`) lists each school's courses next to their
  assigned canonical course, with confidence and rationale, so the user can approve or
  reject matches quickly. Approvals are recorded in the main table's `match_status`.

## Labeling for the committee

Every web view or report that shows course descriptions must visibly mark generic ones
and explain what "generic" means: a typical description of a course with that name, written
for this project, not the school's own text.

## Secondary outputs

- `data/raw/`: saved source pages, with the date retrieved
- `data/processed/<school>/required_courses.json`: same data as JSON for the web views
- `data/processed/canonical_courses.json`: copy of the canonical list for the web views
  (they read only from `data/processed/`)
- `data/processed/schools.json`: copy of the registry rows of schools with a built table,
  for the web views
- `web/`: static HTML pages using D3 / Observable Plot from a CDN (no build step) to
  browse the table and show the 4-year normalized layout. The plan page (`index.html`,
  titled and nav-labeled "Course Plans")
  shows one school at a time (UC first, picked from a drop-down); co-op schools get a
  switch between the 8 academic semesters in 4 years and all plan terms with co-op
  (UC: 5 years). It shows no calendar years and does not explain the normalization
  (the user's choice, 2026-10-20)
- A short README section explaining how to regenerate the table

## Open questions

- [x] Formats: CSV for analysis, JSON for the JavaScript views.
