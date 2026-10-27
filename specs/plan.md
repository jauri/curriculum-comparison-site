# Plan

Each step ends with something you can check before moving on.

## Phase 1: UC Computer Science BS

1. **Project setup.** Create `data/raw/`, `data/processed/`, `src/`, `web/`, a Python
   environment (pandas, requests, BeautifulSoup), a `.gitignore`, and a README.
   *Check:* `python -c "import pandas"` works; repo has its first commit.
2. **Collect UC sources.** Find the 2026–27 UC CS BS plan of study and course catalog pages;
   save them to `data/raw/uc/` with the retrieval date.
   *Check:* the user reviews the list of saved URLs.
3. **Parse the plan of study.** `src/parse_uc.py` produces one row per course or
   requirement slot with UC's original year/term and academic/co-op type.
   *Check:* credit total matches UC's stated degree total; the user spot-checks the rows.
4. **Normalize to 8 semesters.** `src/normalize.py` reads the parsed 5-year plan
   (`data/processed/uc_plan_parsed.csv`) and writes a separate 4-year plan,
   `data/processed/uc_plan_4year.csv`, applying the rule in `03-processing.md` (drop
   co-op, shift summers into sequence). Original placement columns are kept alongside.
   *Check:* exactly 8 normalized semesters; the user reviews the original → normalized
   mapping.
5. **Attach descriptions.** Official UC catalog text where available, otherwise labeled
   generic descriptions.
   *Check:* every row has a description and `description_source`; the user reads all
   generic ones.
6. **Seed the canonical course list.** Create `data/reference/canonical_courses.csv`
   from UC's courses and assign each UC row its `canonical_id` in
   `data/reference/uc_matches.csv` (both hand-reviewed; `src/check_canonical.py` validates
   them without writing).
   *Check:* the user reviews the canonical list and descriptions.
7. **Write outputs.** `data/processed/uc_cs_required_courses.csv` and `.json`, plus a
   validation script that runs every check in `03-processing.md`.
8. **First web views.** `web/index.html` (D3 / Observable Plot) shows UC's required courses
   laid out over the 8 normalized semesters; `web/review.html` shows matches for review.
   *Check:* the user opens both in a browser.

## Phase 2: Comparison set (15 schools)

9. **Generalize the pipeline.** Per-school collectors and parsers (`parse_<id>.py`,
   `parse_<id>_descriptions.py`) write fixed-schema files into `data/processed/<id>/`;
   normalize, describe, check_canonical, build_outputs, and validate are shared and take
   `--school <id>`. Program-level facts go in the registry `data/reference/schools.csv`.
   *Check:* rerunning UC through the shared pipeline reproduces the phase 1 outputs
   (apart from moved file paths), and planted errors are caught.
10. **Pilot with two schools.** One Ohio peer (Ohio State) and one aspirational program
    (University of Illinois Chicago, UIC), to test the generalized pipeline, track/core
    handling, and course matching. (UIC replaced UIUC as the pilot at the user's request;
    UIUC is done in step 13.)
    *Check:* the user reviews all matches and any new or revised canonical courses.

## Phase 3: Alignment view (added 2026-10-17, before the remaining schools)

11. **Spec the alignment view.** `specs/06-alignment-view.md`: a D3 parallel coordinate
    view with UC on the left and one chosen school on the right, linked by shared
    canonical courses, in semester order, with hover highlighting and a subject filter.
    *Check:* the user approves the spec.
12. **Build the alignment view.** `web/compare.html` + `compare.js`, with the subject
    areas extended for OSU and UIC.
    *Check:* the user compares UC with OSU and with UIC in a browser.

## Phase 4: Remaining schools and comparison

13. **Remaining 13 schools.** Collect, parse, describe, match, and validate each one; flag
    anything that doesn't fit the rules (non-semester terms, degree in a different college,
    unusual structures). Each new school appears in the alignment view automatically.
14. **Combined table.** `src/build_combined.py` writes
    `data/processed/all_required_courses.csv` / `.json`: every school's required-course
    rows in one table, with `school_id` and a new `subject_area` column. The subject-area
    map moves out of `web/common.js` into `data/reference/subject_areas.csv`, so Python
    (the concept step needs "CS courses only") and the web views use the same areas;
    `build_outputs.py` writes `subject_area` on each row, and the views read it.
    *Check:* row counts match the per-school tables; every row's `subject_area` equals
    what `web/common.js` gives it today; the existing views look unchanged.
15. **Timeline view.** `web/timeline.html` + `timeline.js`, per `07-timeline-view.md`: one
    strip per canonical course, one dot per matched row at its semester, stacked, a "no
    course" bin, UC highlighted.
    *Check:* the user tries it in a browser.

## Phase 5: Concepts (added 2026-10-17, after step 13)

Specified in `08-concepts.md`. CS courses with official descriptions only.

16. **Concept vocabulary.** Read every in-scope description and propose
    `data/reference/concepts.csv` (bottom-up, project-defined groups).
    *Check:* the user reviews the concepts, definitions, groups, and granularity before
    any tagging.
17. **Tag courses.** Propose `data/reference/<school>/concept_tags.csv` for every school,
    each tag with a word-for-word evidence phrase; `src/check_concepts.py` validates them;
    a review page shows tags with the evidence highlighted.
    *Check:* the checker passes for all schools; the user reviews the tags (in batches,
    as with matches).
18. **Coverage table.** `src/build_concepts.py` writes `all_concept_tags` and
    `concept_coverage` (CSV + JSON).
    *Check:* the user spot-checks a few concepts against the tags.
19. **Concept views.** `web/concepts.html` (coverage chart with UC marker and gap lists)
    and the timeline view's concept mode.
    *Check:* the user tries both in a browser.
20. **Other comparison views.** Anything else the committee needs (e.g. where UC differs
    overall), to be specified before building.

## Phase 6: Process page (added 2026-10-18, during step 17; done before step 17's review resumes)

21. **Process page.** A web page that illustrates how the project was done: the user's
    process and Claude's process, and how they worked together. Specified in
    `09-process-view.md` (draft).
    *Check:* the user approves the spec, then checks the page in a browser.

## Phase 7: Concept alignment view (added 2026-10-18; draft)

22. **Concept alignment view.** `web/concept_compare.html` + `.js`, per
    `10-concept-alignment-view.md`: UC vs one school, bands sized by the share of each
    course's concepts found in the other school's courses. Needs step 18's
    `all_concept_tags.json` first; best after step 17's tag review.
    *Check:* the user approves the spec, then tries the page in a browser.

## Phase 8: Curriculum editor (added 2026-10-20)

23. **Curriculum editor.** `web/editor.html` + `.js`, per `11-editor-view.md`: named draft
    revisions of UC's plan (move, remove, revise, add courses), compared with UC today and
    with any comparison school. Drafts live in the viewer's browser (Export / Import JSON).
    *Check:* the user tries it in a browser.

## Later (not yet planned)

- Expand beyond 15 schools (alternates are listed in `05-comparison-set.md`).
- Mapping the concept table to ACM/IEEE CS2023 knowledge areas (phase 5 is bottom-up).
- Concepts in non-CS courses, or from syllabi rather than catalog descriptions.
