# 02 — Data Sources

## UC CS BS curriculum

- **Primary source:** UC's eCurriculum "major map" for the Computer Science BS (College of
  Engineering and Applied Science). UC publishes plans per **graduating class and
  section**, not per catalog year. The project's "2026–27 catalog" means the
  **Class of 2031** (students entering Fall 2026):
  - Canonical plan: Class of 2031 Section I,
    https://webapps2.uc.edu/ecurriculum/DegreePrograms/Home/MajorMap/11017
  - Cross-check: Class of 2031 Section II,
    https://webapps2.uc.edu/ecurriculum/DegreePrograms/Home/MajorMap/11018
    (same courses, different co-op rotation)
  - Program detail (college, 124–126 credit total, accreditation):
    https://webapps2.uc.edu/ecurriculum/DegreePrograms/Program/Detail/20BC-CS-BSCS
- No 2026–27 Academic Program Catalog PDF was published as of 2026-10-17, and the major
  maps have no PDF version, so HTML is the only source.
- **Needed from it:**
  - Each required course: subject code, number, title, credit hours
  - Term placement in the official plan of study (year + semester), including co-op terms
  - Requirement slots that are not a single course (electives, gen-ed buckets)
- **Course descriptions:** UC has no public static course catalog. Official descriptions
  come from UC's public Catalyst "Browse Course Catalog" (PeopleSoft, no login).
  `src/collect_uc_courses.py` replays its form posts for each course in the Section I
  plan and saves each course detail page to `data/raw/uc/courses/`
  (`method = script-peoplesoft` in the manifest). When a course has several offerings,
  the CEAS one is preferred and regional campuses (Blue Ash, Clermont) are avoided.
  Third-party sites (e.g., Coursicle) are never treated as official.
- **Elective lists:** No public list of approved CS / directed electives was found.
  Elective slots stay placeholder rows with generic descriptions.

## Other schools (phase 2)

- Raw files go in `data/raw/<school_id>/`, with the same filename and manifest
  (`sources.csv`) rules as UC.
- Each school gets its own collect and parse scripts, because every school publishes its
  plan and catalog differently. They write fixed-schema files (`plan_parsed.csv`,
  `official_descriptions.csv`) that the shared steps read.
- Sites that refuse scripts (HTTP 403, or an AWS bot "challenge") are saved through the
  user's Chrome, never by disguising the script as a browser: a same-origin `fetch()` in
  an open page of the site reads each page, and the unchanged bytes are downloaded as a
  file (Berkeley, Michigan) or, since step 13 batch 3, as one JSON "bundle" of several
  base64-encoded pages (Virginia Tech, Purdue), because Chrome blocks a tab's second
  automatic download. `collect_common.import_bundle()` saves each page with
  `method = browser`.
- Program facts (college, catalog year, stated credit total) are recorded in
  `data/reference/schools.csv` and must be verified against a saved page.

## Collection approach

- Save raw source material (HTML pages or PDFs) to `data/raw/` with the retrieval date as
  a filename prefix (`YYYY-MM-DD_<slug>.html`), so results can be traced back even if
  UC's site changes. `src/collect_uc.py` downloads the static pages, never overwrites
  existing files, and records each one in `data/raw/uc/sources.csv` (URL, file, date,
  method, SHA-256).
- Parse raw files into a table with a script in `src/` (one parser per school). Don't copy data by hand unless a
  source can't be parsed, and if that happens, note it.

## Generic descriptions

When UC has no official description for a course (or for an elective slot), we write a
generic description of what courses with that name in a CS department usually cover.

- Generic descriptions must be **clearly labeled** (`description_source = generic`) and
  never presented as UC's own text.
- Keep them short (2–4 sentences) and neutral, describing typical content rather than
  claims about UC.

## Open questions

- [x] Sources: **online only.** Claude fetches UC's public catalog pages and saves them to
      `data/raw/`; no user-provided documents.
