"""Validate a school's final output table against the rules in the specs.

Shared step (any school); step 7 of specs/plan.md, generalized in step 9. Runs every
check listed under "Validation checks" in specs/03-processing.md on
data/processed/<id>/required_courses.csv (written by build_outputs.py), plus schema
checks from specs/04-outputs.md:

1. Total credits match the school's stated degree total, as recorded in
   data/reference/schools.csv. The school's parser checks that registry value against
   the saved raw page, so the check still traces back to the source, and it doesn't
   depend on the credit sums computed in earlier steps.
2. Every non-co-op row has a normalized placement; co-op rows have none.
3. Exactly 8 normalized semesters, with year and Fall/Spring derived by the rule.
4. Every row has a description and a description_source. Official rows have a URL, and
   slot rows (no course code) are labeled generic.
5. Every canonical_id exists in the canonical list; no canonical course is unused (by
   any school's table built so far); no two canonical courses share an ID or name.
6. Schema: all columns present in order, enumerated columns hold allowed values.
7. The JSON copy holds the same rows as the CSV.
8. (Step 13) The match table course_matches.csv: valid roles and values, and it agrees
   with each row's canonical_ids and match_status; choice rows follow the choice rules
   (common.choice_failures); the JSON's nested matches equal the match table's lines.

It then prints a few random rows next to their source files for a hand spot-check
(the last item in the spec's list). Pass a number to pick a different sample, e.g.
`python src/validate.py --school uc 7`.

The script only reads files. It exits with an error listing every failed check.

Usage:
    python src/validate.py --school uc [seed]
"""

import math
from pathlib import Path

import pandas as pd

# build_outputs.py and common.py live next to this file. Running `python src/validate.py`
# puts src/ on the import path, so the column lists are shared, not copied.
from build_outputs import EXTRA_COLUMNS, MATCH_COLUMNS, SCHEMA_COLUMNS, STATUS_RANK
from check_canonical import ROLES
from common import (AREA_KEYS, CANON_CSV, TERM_NAMES, School, all_school_ids, choice_failures, load_school, require,
                    school_from_args)

# Allowed values for enumerated columns, from specs/04-outputs.md.
ALLOWED = {
    "requirement_type": {"required", "elective_slot", "gen_ed", "coop"},
    "orig_term": TERM_NAMES,
    "orig_term_type": {"academic", "coop"},
    "description_source": {"official", "generic"},
    "match_status": {"proposed", "approved", "rejected"},
    "subject_area": set(AREA_KEYS),  # step 14
}
# Allowed values in course_matches.csv (specs/04-outputs.md, "Match table").
MATCH_ALLOWED = {
    "match_role": ROLES,
    "match_confidence": {"high", "medium", "low", "new"},
    "match_status": {"proposed", "approved", "rejected"},
}
BOOLEANS = ["in_engineering_college", "is_coop", "counts_toward_total"]
SLOT_TYPES = {"elective_slot", "gen_ed"}
SPOT_CHECK_ROWS = 5


# Check 6: every expected column is present in the expected order, enumerated columns
# hold allowed values, and boolean columns are real booleans.
def check_schema(df: pd.DataFrame) -> list[str]:
    """Return failures for missing columns, column order, and disallowed values."""
    failures = []
    expected = SCHEMA_COLUMNS + EXTRA_COLUMNS
    missing = [c for c in expected if c not in df.columns]
    failures += [f"Missing column: {c}" for c in missing]
    if not missing and list(df.columns) != expected:
        failures.append("Columns are not in the 04-outputs.md order (schema columns, then extras).")
    for col, allowed in ALLOWED.items():
        bad = sorted(set(df[col]) - allowed)
        failures += [f"{col} has a disallowed value: '{v}'" for v in bad]
    for col in BOOLEANS:
        # pandas reads True/False cells as bool; anything else (blank, typo) gives object.
        if df[col].dtype != bool:
            failures.append(f"{col} should hold only True/False.")
    # A credit range must run low to high (a fixed-credit row has min == max).
    failures += [f"'{r.title}': credits_min {r.credits_min} > credits_max {r.credits_max}."
                 for r in df[df["credits_min"] > df["credits_max"]].itertuples()]
    # A course code is empty for slots and present for everything else, except co-op
    # rows: UC's co-op terms are courses (COOP 2011), but Northeastern's plan names no
    # co-op course, so its co-op rows have no code (step 13).
    is_slot = df["requirement_type"].isin(SLOT_TYPES)
    may_lack_code = is_slot | (df["requirement_type"] == "coop")
    failures += [f"Slot '{t}' has a course code." for t in df.loc[is_slot & (df["course_code"] != ""), "title"]]
    failures += [f"Non-slot row '{t}' has no course code." for t in df.loc[~may_lack_code & (df["course_code"] == ""), "title"]]
    return failures


# Check 1: the academic credit total equals the school's stated degree total. Co-op
# courses are 0 credits, so including them changes nothing, but they are excluded to
# say what's meant. Rows with counts_toward_total = False (e.g. UIC's ENGR 100) are in
# the plan but not in the stated total, so they are left out of the sum too.
def check_credits(df: pd.DataFrame, school: School) -> list[str]:
    """Return a failure if the credit range differs from the one in schools.csv."""
    stated_min, stated_max = school.credits  # tuple unpacking
    academic = df[~df["is_coop"] & df["counts_toward_total"]]
    total = (academic["credits_min"].sum(), academic["credits_max"].sum())
    print(f"Credits: table {total[0]:g}-{total[1]:g}, {school.short_name} states {stated_min}-{stated_max}")
    # Credits may be fractional (step 13 batch 3): Penn State has 1.5-credit courses, and
    # CMU's units are divided by 3 and rounded to 2 decimals, so a sum can be off by a
    # few hundredths (e.g. 120.99). A tolerance of 0.05 absorbs that rounding without
    # hiding a real mismatch, which is at least one credit in practice.
    if abs(total[0] - stated_min) > 0.05 or abs(total[1] - stated_max) > 0.05:
        return [f"Credit total {total[0]:g}-{total[1]:g} does not match {school.short_name}'s stated {stated_min}-{stated_max}."]
    return []


# Checks 2 and 3: placement present exactly when the row isn't co-op, exactly 8
# semesters (1-8), and year / Fall-Spring derived from the semester by the rule in
# 03-processing.md: year = ceil(k / 2), odd = Fall, even = Spring.
def check_placement(df: pd.DataFrame) -> list[str]:
    """Return failures for missing, extra, or inconsistent normalized placement."""
    failures = []
    placed = df["norm_semester"].notna()
    failures += [f"Non-co-op row '{r.title}' has no normalized semester." for r in df[~df["is_coop"] & ~placed].itertuples()]
    failures += [f"Co-op row '{r.title}' has a normalized semester." for r in df[df["is_coop"] & placed].itertuples()]
    sems = sorted(df.loc[placed, "norm_semester"].astype(int).unique())
    if sems != list(range(1, 9)):
        failures.append(f"Normalized semesters are {sems}, not exactly 1-8.")
    for r in df[placed].itertuples():  # itertuples gives rows as named tuples (r.title, ...)
        k = int(r.norm_semester)
        if r.norm_year != math.ceil(k / 2) or r.norm_term != ("Fall" if k % 2 else "Spring"):
            failures.append(f"'{r.title}': semester {k} should be year {math.ceil(k / 2)} "
                            f"{'Fall' if k % 2 else 'Spring'}, not year {r.norm_year} {r.norm_term}.")
    return failures


# Check 4: descriptions present and sourced. Official text needs a URL. Slots have no
# catalog page of their own, so their text must be labeled generic (CLAUDE.md: generic
# descriptions are always labeled).
def check_descriptions(df: pd.DataFrame) -> list[str]:
    """Return failures for missing descriptions, URLs, or wrong source labels."""
    failures = []
    failures += [f"'{r.title}' has no description." for r in df[df["description"].str.strip() == ""].itertuples()]
    official = df["description_source"] == "official"
    failures += [f"Official row '{r.title}' has no description_url." for r in df[official & (df["description_url"] == "")].itertuples()]
    failures += [f"Slot '{r.title}' is not labeled generic." for r in df[(df["course_code"] == "") & official].itertuples()]
    return failures


# Check 5: links to the canonical list. Every canonical_id must exist; every canonical
# course must be used; IDs and names must be unique. The list itself is hand-reviewed,
# so it is only read here. "Used" means by any school's table built so far, since the
# list is shared: a school need not have every canonical course.
def check_canonical(df: pd.DataFrame, canon: pd.DataFrame) -> list[str]:
    """Return failures for unknown, unused, or duplicate canonical courses."""
    failures = []
    ids = set(canon["canonical_id"])
    for r in df.itertuples():
        failures += [f"'{r.title}' has unknown canonical_id '{c}'." for c in split_ids(r.canonical_ids) if c not in ids]
    used = {c for v in df["canonical_ids"] for c in split_ids(v)} | used_elsewhere()  # | is set union
    failures += [f"Canonical course '{c}' is not used by any row of any school." for c in sorted(ids - used)]
    for col in ["canonical_id", "name"]:
        # duplicated(keep=False) marks every copy of a repeated value.
        failures += [f"Duplicate canonical {col}: {v}" for v in sorted(set(canon.loc[canon[col].duplicated(keep=False), col]))]
    return failures


# A row's canonical_ids cell ("a; b") as a list; an empty cell gives an empty list.
def split_ids(value: str) -> list[str]:
    """Return the canonical ids in a "; "-separated cell."""
    return value.split("; ") if value else []


# Canonical ids used by every school's final table that exists so far (this school's
# own table is read too, which is harmless). Schools not built yet are skipped.
def used_elsewhere() -> set[str]:
    """Return the canonical_ids used in any data/processed/<id>/required_courses.csv."""
    used = set()
    for sid in all_school_ids():
        path = load_school(sid).processed / "required_courses.csv"
        if path.exists():
            table = pd.read_csv(path, dtype=str, keep_default_na=False)
            # Tables built before step 13 have a single canonical_id column.
            col = "canonical_ids" if "canonical_ids" in table.columns else "canonical_id"
            used |= {c for v in table[col] for c in split_ids(v)}
    return used


# Check 8: course_matches.csv. Each line has allowed values and a real boolean
# partial_match; the main table's canonical_ids and match_status are exactly what its
# key's lines give (build_outputs.summarize_matches), so the two files can't drift.
def check_match_table(df: pd.DataFrame, matches: pd.DataFrame) -> list[str]:
    """Return failures for bad match lines or rows that disagree with them."""
    failures = []
    if list(matches.columns) != MATCH_COLUMNS:
        return [f"course_matches.csv columns should be {MATCH_COLUMNS}."]
    for col, allowed in MATCH_ALLOWED.items():
        failures += [f"course_matches.csv {col} has a disallowed value: '{v}'" for v in sorted(set(matches[col]) - allowed)]
    if matches["partial_match"].dtype != bool:
        failures.append("course_matches.csv partial_match should hold only True/False.")
    keys = df["course_code"].where(df["course_code"] != "", df["title"])  # match key, as in build_outputs
    lines = {k: g for k, g in matches.groupby("match_key", sort=False)}
    for key, r in zip(keys, df.itertuples()):
        g = lines.get(key)
        if g is None:
            failures.append(f"'{key}' has no lines in course_matches.csv.")
            continue
        if r.canonical_ids != "; ".join(g["canonical_id"]):
            failures.append(f"'{key}': canonical_ids '{r.canonical_ids}' differs from its match lines.")
        if r.match_status != min(g["match_status"], key=STATUS_RANK.get):
            failures.append(f"'{key}': match_status '{r.match_status}' is not its least-reviewed line's.")
    failures += [f"course_matches.csv line for '{k}' matches no row." for k in sorted(set(lines) - set(keys))]
    return failures


# Check 7: the JSON for the web views holds the same rows as the CSV. Both are read
# back and compared after making missing values and number types agree. Since step 13
# each JSON row also carries a nested `matches` list, compared with course_matches.csv.
def check_json(df: pd.DataFrame, out_json: Path, matches: pd.DataFrame) -> list[str]:
    """Return a failure if the JSON rows differ from the CSV rows."""
    js = pd.read_json(out_json, orient="records", dtype=False)  # dtype=False: no type guessing
    nested = js.pop("matches") if "matches" in js.columns else None  # pop: remove and return the column
    if nested is None or list(js.columns) != list(df.columns) or len(js) != len(df):
        return ["JSON columns or row count differ from the CSV (plus the nested matches)."]
    # Each row's nested matches must be its key's lines in course_matches.csv. The key
    # column is not repeated inside the JSON, so it is dropped before comparing.
    keys = df["course_code"].where(df["course_code"] != "", df["title"])
    lines = {k: g.drop(columns="match_key").to_dict("records") for k, g in matches.groupby("match_key", sort=False)}
    bad = [k for k, n in zip(keys, nested) if n != lines.get(k)]
    if bad:
        return [f"JSON nested matches differ from course_matches.csv for: {', '.join(bad)}"]
    # Compare as text: JSON null and CSV blank both become "", and 1 vs 1.0 is avoided
    # by converting the nullable integer columns the same way on both sides.
    def norm(frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        for col in ["academic_term_index", "norm_semester", "norm_year"]:
            out[col] = pd.to_numeric(out[col]).astype("Int64")
        # Blank out missing values *before* converting to text: astype(str) leaves
        # <NA> in Int64 columns as float NaN, and NaN != NaN, so equal blanks would
        # otherwise always compare as different.
        return out.astype(object).where(out.notna(), "").astype(str)
    diff = (norm(js) != norm(df)).any(axis=1)  # True for rows where any cell differs
    return [f"JSON row {i} differs from the CSV." for i in diff[diff].index]


# The spec's last check is a hand spot-check against the source. Print a few random
# rows with the files to compare them against; the user does the comparing.
def print_spot_check(df: pd.DataFrame, seed: int, school: School) -> None:
    """Print SPOT_CHECK_ROWS random rows and the source files behind them."""
    print(f"\nSpot-check (seed {seed}): compare these rows with their source files.")
    # min() guards against a school with fewer rows than the sample size.
    for r in df.sample(min(SPOT_CHECK_ROWS, len(df)), random_state=seed).itertuples():
        sem = f"semester {r.norm_semester}" if pd.notna(r.norm_semester) else "co-op, no semester"
        # orig_calendar_year may be blank (sample plans without dates); fall back to plan year.
        when = f"{r.orig_term} {r.orig_calendar_year}" if r.orig_calendar_year != "" else f"Y{r.orig_year} {r.orig_term}"
        print(f"  {r.course_code or r.title}: {r.credits_min}-{r.credits_max} cr, "
              f"{school.short_name} {when} -> {sem}, {r.description_source}, -> {r.canonical_ids}")
        print(f"    plan: {r.source_file}")
        print(f"    description: {r.description_file}")


# Script entry point: load the table, run every check, print the spot-check sample.
def main() -> None:
    # The optional seed is a positional argument: nargs="?" means zero or one value.
    school, args = school_from_args(
        __doc__.splitlines()[0],
        extra=lambda p: p.add_argument("seed", nargs="?", type=int, default=0, help="spot-check sample seed"),
    )
    out_csv = school.processed / "required_courses.csv"
    out_json = school.processed / "required_courses.json"
    out_matches = school.processed / "course_matches.csv"
    require([(out_csv, "build_outputs.py"), (out_json, "build_outputs.py"), (out_matches, "build_outputs.py"),
             (CANON_CSV, "the reference file")])

    # keep_default_na=False keeps blank text as ""; the nullable-integer columns are then
    # converted explicitly, with blanks (co-op rows) becoming <NA>.
    df = pd.read_csv(out_csv, keep_default_na=False)
    for col in ["academic_term_index", "norm_semester", "norm_year"]:
        df[col] = pd.to_numeric(df[col].replace("", pd.NA)).astype("Int64")
    canon = pd.read_csv(CANON_CSV, keep_default_na=False, dtype=str)
    matches = pd.read_csv(out_matches, keep_default_na=False)

    failures = check_schema(df)
    failures += check_credits(df, school)
    failures += check_placement(df)
    failures += check_descriptions(df)
    failures += check_canonical(df, canon)
    failures += check_match_table(df, matches)
    failures += choice_failures(df)
    failures += check_json(df, out_json, matches)

    print_spot_check(df, args.seed, school)
    if failures:
        raise SystemExit("\nCHECKS FAILED:\n  " + "\n  ".join(failures))
    print(f"\nAll validation checks passed ({len(df)} rows).")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
