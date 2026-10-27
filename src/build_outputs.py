"""Write a school's final output table, as CSV and JSON.

Shared step (any school); step 7 of specs/plan.md, generalized in step 9. Joins three
inputs into the schema in specs/04-outputs.md:

- data/processed/<id>/plan_described.csv (from describe.py): one row per course or slot,
  with original and normalized placement and a description.
- data/reference/<id>/matches.csv (hand-reviewed): each course code or slot title's
  canonical_id, match_confidence, match_rationale, partial_match, and match_status.
  Since step 13 a key may have several lines (one per canonical course, each with a
  match_role), so the matches no longer fit as columns of the main table: they are
  written to their own table, and the main table lists the row's canonical_ids.
- data/reference/subject_areas.csv (hand-reviewed, step 14): the rules that give each
  row its subject_area (Computing, Math, ...), shared by the web views and later steps.
- Program-level facts: the college that houses the degree and whether it is an
  engineering college, from the registry data/reference/schools.csv. The college name
  is checked against the school's saved page named in the registry's college_source,
  so it is traceable to a raw source.

Writes:

- data/processed/<id>/required_courses.csv: the main table, for analysis.
- data/processed/<id>/required_courses.json: the same rows, for the web views, each
  with its matches nested as a `matches` list.
- data/processed/<id>/course_matches.csv: one line per (row key, canonical course)
  match, for analysis (schema in specs/04-outputs.md).
- data/processed/canonical_courses.json: a copy of the canonical list, because the web
  views read only from data/processed/ (CLAUDE.md), and the review page needs names
  and descriptions for each canonical_id.
- data/processed/schools.json: a copy of the school registry, for the same reason; the
  review page uses it to find each school's table and label its rows.

Credits are two columns, credits_min and credits_max, instead of the spec's single
`credits`. UC's science slots are 4-5 credits, and a range keeps degree totals exact
(124-126). The user chose this in step 7, and 04-outputs.md was updated to match.

This script only assembles the table. src/validate.py runs the checks from
specs/03-processing.md on what it writes.

Usage:
    python src/build_outputs.py --school uc
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import (CANON_CSV, CANON_JSON, SCHOOLS_CSV, SCHOOLS_JSON, School, rel, require, school_from_args,
                    subject_areas)

# Output column order: the 04-outputs.md schema first (with credits_min/credits_max in
# place of credits), then the optional extra columns kept for traceability and matching.
SCHEMA_COLUMNS = [
    "institution", "program", "college", "in_engineering_college", "catalog_year",
    "course_code", "subject", "number", "title", "credits_min", "credits_max",
    "requirement_type", "orig_year", "orig_term", "orig_term_type", "academic_term_index",
    "norm_semester", "norm_year", "is_coop", "counts_toward_total", "description", "description_source",
    "description_url", "canonical_ids", "match_status", "notes",
]
EXTRA_COLUMNS = [
    "plan", "orig_calendar_year", "norm_term", "gened_tag", "min_grade", "options", "choice_kind", "choice_group",
    "prerequisites", "source_file", "description_file", "subject_area",
]
# Columns of course_matches.csv (specs/04-outputs.md), in matches.csv's own order.
MATCH_COLUMNS = [
    "match_key", "canonical_id", "match_role", "match_confidence", "match_rationale",
    "partial_match", "match_status", "notes",
]
# A row's overall match_status is its least-reviewed match: any rejected line makes the
# row rejected, else any proposed line makes it proposed (a choice decided in step 13).
STATUS_RANK = {"rejected": 0, "proposed": 1, "approved": 2}
# Integer columns that are blank for co-op rows. pandas would read them as floats
# (1.0, 2.0, ...) because NaN is a float; the nullable "Int64" type keeps them whole.
NULLABLE_INTS = ["academic_term_index", "norm_semester", "norm_year"]


# Confirm the college from the newest saved page named in the registry (for UC, the
# program detail page). The registry gives the college name as the school writes it in
# full, so a change on the school's side stops the script instead of going unnoticed.
# Returns the matching file's path so the caller can mention it.
def confirm_college(school: School) -> Path:
    """Check that the registry's college name appears on the school's saved page."""
    page = school.newest(school.college_source)  # ISO date prefix: newest snapshot
    # get_text(" ") joins the text of all tags with spaces; \s+ then collapses the
    # page's tab and newline indentation so a name split across lines still matches.
    text = re.sub(r"\s+", " ", BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser").get_text(" "))
    if school.college not in text:
        raise SystemExit(f"'{school.college}' not found on {page.name}; check the college name in schools.csv.")
    return page


# Collapse a key's match lines into the two main-table columns: canonical_ids, all of
# the key's concepts "; "-joined in match-file order, and match_status, the
# least-reviewed status (STATUS_RANK). Returns one row per match_key.
def summarize_matches(matches: pd.DataFrame) -> pd.DataFrame:
    """Return match_key, canonical_ids, match_status for each key in matches.csv."""
    # groupby(sort=False) keeps the file's order of keys; agg runs one function per column.
    return matches.groupby("match_key", sort=False).agg(
        canonical_ids=("canonical_id", "; ".join),
        match_status=("match_status", lambda st: min(st, key=STATUS_RANK.get)),
    ).reset_index()


# Script entry point: join the plan and matches, add program-level columns, write files.
def main() -> None:
    school, _ = school_from_args(__doc__.splitlines()[0])  # first docstring line as --help text
    plan_csv = school.processed / "plan_described.csv"
    match_csv = school.reference / "matches.csv"
    out_csv = school.processed / "required_courses.csv"
    out_json = school.processed / "required_courses.json"
    out_matches = school.processed / "course_matches.csv"
    require([(plan_csv, "describe.py"), (match_csv, "the reference file"), (CANON_CSV, "the reference file")])
    college_page = confirm_college(school)

    # keep_default_na=False keeps blank cells as "" so text columns never hold NaN.
    plan = pd.read_csv(plan_csv, keep_default_na=False)
    matches = pd.read_csv(match_csv, keep_default_na=False, dtype=str)
    canon = pd.read_csv(CANON_CSV, keep_default_na=False, dtype=str)

    # Match key: course code, or the title for slots (same rule as check_canonical.py).
    # .where keeps course_code where it is non-empty and falls back to title elsewhere.
    plan["match_key"] = plan["course_code"].where(plan["course_code"] != "", plan["title"])
    # how="left" keeps every plan row; validate="many_to_one" makes pandas raise an error
    # if a key appears twice in the match file, which would duplicate plan rows.
    df = plan.merge(summarize_matches(matches), on="match_key", how="left", validate="many_to_one")
    unmatched = df.loc[df["canonical_ids"].isna(), "match_key"].tolist()
    if unmatched:
        raise SystemExit(f"No match in {rel(match_csv)} for: {', '.join(unmatched)}. Run check_canonical.py.")

    df["college"] = school.college
    # Subject area (step 14) from data/reference/subject_areas.csv, so the web views and
    # the concept step read one shared answer instead of each keeping a map.
    df["subject_area"] = subject_areas(df)
    df["in_engineering_college"] = school.in_engineering_college
    # Blank ("") placement cells become <NA>, then the nullable integer type.
    for col in NULLABLE_INTS:
        df[col] = pd.to_numeric(df[col].replace("", pd.NA)).astype("Int64")

    # Only the match lines of keys in the plan (check_canonical.py makes sure that is all
    # of them). The match file stores partial_match as text ("true"/"false"); make it a
    # real boolean so the CSV and JSON agree with is_coop and in_engineering_college.
    used = matches[matches["match_key"].isin(df["match_key"])][MATCH_COLUMNS].copy()
    used["partial_match"] = used["partial_match"] == "true"

    keys = df["match_key"]  # kept for nesting the matches into the JSON below
    df = df[SCHEMA_COLUMNS + EXTRA_COLUMNS]
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)
    used.to_csv(out_matches, index=False)
    # The JSON nests each row's match lines (without the key) as a `matches` list, so a
    # web view has everything about a row in one object. to_dict("records") gives one
    # dict per line; the comprehension groups them by key.
    by_key = {k: g.drop(columns="match_key").to_dict("records") for k, g in used.groupby("match_key", sort=False)}
    js = df.copy()
    js["matches"] = [by_key[k] for k in keys]
    # orient="records": a JSON array with one object per row, the shape D3 and
    # Observable Plot expect. Missing values (<NA>) are written as null.
    js.to_json(out_json, orient="records", indent=2, force_ascii=False)
    # The canonical list is shared, so every school's build rewrites the same copy.
    canon.to_json(CANON_JSON, orient="records", indent=2, force_ascii=False)
    # Only schools whose table exists are listed, so the page never requests a missing file.
    schools = pd.read_csv(SCHOOLS_CSV, keep_default_na=False, dtype=str)
    built = schools["school_id"].map(lambda sid: (CANON_JSON.parent / sid / "required_courses.json").exists())
    schools[built].to_json(SCHOOLS_JSON, orient="records", indent=2, force_ascii=False)

    print(f"College confirmed on {rel(college_page)}: {school.college}")
    print(f"Wrote {len(df)} rows to {rel(out_csv)} and {out_json.name}; {len(used)} match lines to {out_matches.name}")
    print(f"Wrote {len(canon)} canonical courses to {rel(CANON_JSON)}")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
