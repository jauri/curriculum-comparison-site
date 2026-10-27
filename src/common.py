"""Shared paths and helpers for the per-school pipeline.

Phase 2 runs the same steps for every school in the comparison set. Only collecting and
parsing differ from school to school (each school publishes its plan of study and its
catalog differently), so those scripts are per school: collect_<id>.py, parse_<id>.py,
parse_<id>_descriptions.py. Every later step (normalize, describe, check_canonical,
build_outputs, validate) is shared and takes `--school <id>`.

The steps meet through files with fixed names inside per-school folders:

    data/raw/<id>/                    source files as downloaded (sources.csv logs them)
    data/reference/<id>/              hand-reviewed: matches.csv, generic_descriptions.csv
    data/processed/<id>/              generated:
        plan_parsed.csv               parse_<id>.py: one row per course or slot
        official_descriptions.csv     parse_<id>_descriptions.py: catalog text per course
        plan_4year.csv                normalize.py
        plan_described.csv            describe.py
        required_courses.csv / .json  build_outputs.py (the final table)

Program-level facts (institution, college, catalog year, stated credit total) come from
the hand-reviewed registry data/reference/schools.csv, one row per school, so no shared
script has to know anything about a particular school.
"""

import argparse
from pathlib import Path

import pandas as pd

# Resolve paths from this file's location so every script works from any directory.
ROOT = Path(__file__).resolve().parent.parent
SCHOOLS_CSV = ROOT / "data" / "reference" / "schools.csv"
CANON_CSV = ROOT / "data" / "reference" / "canonical_courses.csv"
CANON_JSON = ROOT / "data" / "processed" / "canonical_courses.json"
SCHOOLS_JSON = ROOT / "data" / "processed" / "schools.json"  # registry copy for the web views
# Subject-area rules (step 14), hand-reviewed; moved here from web/common.js so the
# Python steps (the concept table tags CS courses only) and the web views agree.
SUBJECT_AREAS_CSV = ROOT / "data" / "reference" / "subject_areas.csv"
# The six areas of the web views, in palette order (web/common.js AREAS holds their
# labels and colors, which are presentation, not data).
AREA_KEYS = ["cs", "math", "science", "eng", "writing", "gened"]

# Columns every parse_<id>.py must write to plan_parsed.csv, in this order. Parsers may
# leave optional ones blank (e.g. orig_calendar_year when a school's sample plan says
# only "Year 2, Fall"), but every column must exist so the shared steps can rely on it.
# - counts_toward_total: False for a row that is in the plan but whose credits don't
#   count toward the degree total (UIC's ENGR 100; OSU's CSE 1223, which students take
#   unless they place out). Decided with the user in step 10.
# - options: for a choice slot ("CSE 3231 or 3241"), the option course codes separated
#   by "; ", so each option's official description can still be looked up.
# - choice_kind, choice_group: for a choice slot, whether the student picks one option
#   ("choose") or takes every option in an order of their choosing ("all_in_any_order",
#   e.g. Berkeley's ELENG 66 / ELENG 64 listed in two semesters). Rows of one
#   all_in_any_order group share a choice_group id. Set by the parser from the school's
#   own text; see finish_choices() below. Added in step 13.
PARSED_COLUMNS = [
    "institution", "program", "catalog_year", "plan",
    "course_code", "subject", "number", "title", "credits_min", "credits_max",
    "requirement_type", "gened_tag", "min_grade",
    "orig_year", "orig_term", "orig_calendar_year", "orig_term_type", "is_coop",
    "counts_toward_total", "notes", "options", "choice_kind", "choice_group", "source_file",
]
# Allowed choice_kind values (specs/03-processing.md, "Choice kinds").
CHOICE_KINDS = {"choose", "all_in_any_order"}
# Term names allowed in orig_term. Ohio State calls its fall term "Autumn"; it is kept
# as written (it is the original placement) and treated as a fall term when sorting.
# Northeastern splits summer into two half-terms, "Summer 1" and "Summer 2" (step 13).
TERM_NAMES = {"Fall", "Autumn", "Spring", "Summer", "Summer 1", "Summer 2"}
# Columns of official_descriptions.csv, one row per course code with saved catalog text.
OFFICIAL_COLUMNS = ["course_code", "description", "prerequisites", "description_url", "description_file"]


# The choice rules of specs/03-processing.md, as failure messages. Shared by every
# parser (through finish_choices) and by validate.py, so the rules live in one place:
# - choice_kind is set exactly on rows with options, to an allowed value;
# - choice_group is set exactly on all_in_any_order rows;
# - the rows of one group list the same options, and there is one row per option
#   (two options taken in either order fill two semesters);
# - an option set repeated across "choose" rows stops the parser: it usually means the
#   options are all required in some order, and the source must say which.
def choice_failures(df: pd.DataFrame) -> list[str]:
    """Return failure messages for choice rows that break the choice rules."""
    failures = []
    has_options = df["options"] != ""
    for r in df[has_options & ~df["choice_kind"].isin(CHOICE_KINDS)].itertuples():
        failures.append(f"Choice row '{r.title}' has choice_kind '{r.choice_kind}', not one of {sorted(CHOICE_KINDS)}.")
    for r in df[~has_options & (df["choice_kind"] != "")].itertuples():
        failures.append(f"Row '{r.title}' has a choice_kind but no options.")
    grouped = df["choice_kind"] == "all_in_any_order"
    for r in df[grouped != (df["choice_group"] != "")].itertuples():  # != on booleans: exactly one is true
        failures.append(f"Row '{r.title}': choice_group must be set exactly when choice_kind is all_in_any_order.")
    for group, g in df[grouped & (df["choice_group"] != "")].groupby("choice_group"):
        option_sets = {frozenset(o.split("; ")) for o in g["options"]}  # frozenset: hashable, order-free
        if len(option_sets) != 1:
            failures.append(f"Choice group '{group}': rows list different options.")
        elif len(g) != len(next(iter(option_sets))):  # next(iter(...)): the one set in option_sets
            failures.append(f"Choice group '{group}': {len(g)} rows for {len(next(iter(option_sets)))} options.")
    choose = df[df["choice_kind"] == "choose"]
    for options, g in choose.groupby(choose["options"].map(lambda o: frozenset(o.split("; ")))):
        if len(g) > 1:
            failures.append(f"Options {'; '.join(sorted(options))} appear in {len(g)} 'choose' rows; check the "
                            "source for whether all are required (all_in_any_order) and mark them.")
    return failures


# Called by every parse_<id>.py just before writing plan_parsed.csv. Rows with options
# that the parser didn't mark get choice_kind "choose", the default when the source says
# nothing more (03-processing.md); then the choice rules are checked, and the parser
# stops if any fails. Returns the same DataFrame so the call can sit inline.
def finish_choices(df: pd.DataFrame) -> pd.DataFrame:
    """Fill choice_kind / choice_group defaults, check the choice rules, return df."""
    for col in ["choice_kind", "choice_group"]:
        if col not in df.columns:
            df[col] = ""
    # fillna(""): rows built without these keys get NaN when the DataFrame is made.
    df[["choice_kind", "choice_group"]] = df[["choice_kind", "choice_group"]].fillna("")
    df.loc[(df["options"] != "") & (df["choice_kind"] == ""), "choice_kind"] = "choose"
    failures = choice_failures(df)
    if failures:
        raise SystemExit("CHOICE CHECKS FAILED:\n  " + "\n  ".join(failures))
    return df


# One school's directories. A small class instead of loose functions so that a script
# can say `s.processed / "plan_4year.csv"` and the folder layout lives in one place.
class School:
    """A row of schools.csv plus the paths of the school's data folders."""

    # Copy the registry row into attributes and derive the three folder paths.
    def __init__(self, row: dict):
        self.id = row["school_id"]
        self.short_name = row["short_name"]
        self.institution = row["institution"]
        self.program = row["program"]
        self.college = row["college"]
        # The registry stores text; only the exact string "true" counts as engineering.
        self.in_engineering_college = row["in_engineering_college"] == "true"
        self.catalog_year = row["catalog_year"]
        self.credits = (int(row["credits_min"]), int(row["credits_max"]))
        self.credits_source = row["credits_source"]  # glob in raw/<id>/ stating the total
        self.college_source = row["college_source"]  # glob in raw/<id>/ naming the college
        self.raw = ROOT / "data" / "raw" / self.id
        self.reference = ROOT / "data" / "reference" / self.id
        self.processed = ROOT / "data" / "processed" / self.id

    # Find the newest saved snapshot matching a glob in this school's raw folder.
    # Filenames start with an ISO date (YYYY-MM-DD_...), so alphabetical order is
    # chronological order and the last match is the newest.
    def newest(self, pattern: str) -> Path:
        """Return the newest file in data/raw/<id>/ matching a glob pattern."""
        matches = sorted(self.raw.glob(pattern))
        if not matches:
            raise SystemExit(f"No file matching {pattern} in {rel(self.raw)}; run the collect script first.")
        return matches[-1]


# Look up one school in the registry. dtype=str and keep_default_na=False read every
# cell as plain text ("" for blanks), so values like "2026-27" are never reinterpreted.
def load_school(school_id: str) -> School:
    """Return the School for an id in data/reference/schools.csv, or stop with an error."""
    schools = pd.read_csv(SCHOOLS_CSV, dtype=str, keep_default_na=False)
    rows = schools[schools["school_id"] == school_id]
    if rows.empty:
        raise SystemExit(f"Unknown school '{school_id}'. Known: {', '.join(schools['school_id'])}.")
    return School(rows.iloc[0].to_dict())  # iloc[0]: first (only) matching row


# Every school id in the registry, in file order. Used by checks that span all schools,
# such as "no canonical course is unused".
def all_school_ids() -> list[str]:
    """Return the school ids listed in schools.csv."""
    return pd.read_csv(SCHOOLS_CSV, dtype=str, keep_default_na=False)["school_id"].tolist()


# Parse the command line of a shared step: `--school <id>` (required) plus whatever
# extra arguments the caller adds through `extra`, a function that receives the parser.
# Returns the School and the parsed arguments.
def school_from_args(description: str, extra=None) -> tuple[School, argparse.Namespace]:
    """Parse --school (and any extra arguments) and return (School, args)."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--school", required=True, help="school id from data/reference/schools.csv, e.g. uc")
    if extra:
        extra(parser)
    args = parser.parse_args()
    return load_school(args.school), args


# Stop with a helpful message if any input file is missing. `inputs` pairs each path
# with the step that produces it, e.g. (plan_csv, "normalize.py").
def require(inputs: list[tuple[Path, str]]) -> None:
    """Exit with an error naming the first missing file and the step that writes it."""
    for path, step in inputs:
        if not path.exists():
            raise SystemExit(f"{rel(path)} not found; check {step}.")


# Path relative to the repo root, for messages and for paths stored in the tables
# (as_posix() writes forward slashes on every OS, so the CSVs don't depend on the platform).
def rel(path: Path) -> str:
    """Return a repo-relative, forward-slash path string."""
    return path.relative_to(ROOT).as_posix()


# The subject of a choice row's first option, e.g. "SDS" for "SDS 321; M 362K", for a
# choice row whose options span subjects (so the row's own subject is blank). A code's
# subject is everything before its last space ("C S 312" -> "C S"); a CMU code has no
# space, and its subject is the department number before the hyphen ("15-259" -> "15").
# Same rule as optionSubject() in web/common.js had before step 14.
def option_subject(options: str) -> str:
    """Return the subject prefix of the first option in a "; "-separated list, or ""."""
    if not options:
        return ""
    first = options.split("; ")[0]
    # rfind: index of the last space (-1 if none); str.find gives the first hyphen.
    cut = first.rfind(" ") if " " in first else first.find("-")
    return first[:cut]


# Give each row its subject area from data/reference/subject_areas.csv. Rules are tried
# in a fixed order, the first that fits wins (specs/04-outputs.md, "Subject areas"):
#   1. institution + subject (a subject that means different things at different
#      schools: OSU's CSE is CS, Minnesota's CSE 1001 is a college first-year course),
#   2. subject (the row's own, or its first option's for a mixed choice row),
#   3. slot: the row's first canonical course (slots have no subject).
# `df` needs institution, subject, options, and canonical_ids columns. Unlike the old
# JavaScript, which quietly fell back to CS, an unknown row stops the build: a new
# school's subjects must be added to the reference file on purpose.
def subject_areas(df: pd.DataFrame) -> pd.Series:
    """Return a Series of subject_area keys, one per row of df."""
    rules = pd.read_csv(SUBJECT_AREAS_CSV, dtype=str, keep_default_na=False)
    bad = sorted(set(rules["subject_area"]) - set(AREA_KEYS))
    if bad:
        raise SystemExit(f"{rel(SUBJECT_AREAS_CSV)} has unknown areas: {', '.join(bad)}.")
    # One dict per rule kind; zip pairs each key with its area.
    by_rule = {kind: g for kind, g in rules.groupby("rule")}
    inst = {(i, k): a for i, k, a in by_rule["institution_subject"][["institution", "key", "subject_area"]].values}
    subj = dict(by_rule["subject"][["key", "subject_area"]].values)
    slot = dict(by_rule["slot"][["key", "subject_area"]].values)

    areas, unknown = [], []
    for r in df.itertuples():
        subject = r.subject or option_subject(r.options)
        first_id = r.canonical_ids.split("; ")[0]  # the row's main canonical course
        # dict.get returns None when absent, so `or` moves on to the next rule.
        area = inst.get((r.institution, subject)) or subj.get(subject) or slot.get(first_id)
        if area is None:
            unknown.append(f"{r.title} (subject '{subject}', canonical '{first_id}')")
        areas.append(area)
    if unknown:
        raise SystemExit(f"No subject-area rule in {rel(SUBJECT_AREAS_CSV)} for: {'; '.join(unknown)}.")
    return pd.Series(areas, index=df.index)


# Concepts (phase 5, specs/08-concepts.md). The vocabulary is hand-reviewed reference
# data; the combined table (build_combined.py) is the input every concept step reads.
CONCEPTS_CSV = ROOT / "data" / "reference" / "concepts.csv"
ALL_COURSES_CSV = ROOT / "data" / "processed" / "all_required_courses.csv"

# A tag's `evidence` cell may hold several phrases, every one that states the concept in
# the row's text ("sets | tuples | sequences"), so the review page can highlight them
# all. " | " is the separator because no in-scope title or description contains "|",
# while commas and semicolons occur inside phrases.
EVIDENCE_SEP = " | "


# Split an evidence cell into its phrases, dropping empty pieces (a trailing separator).
# The first phrase is the one the tag was first proposed with.
def split_evidence(cell: str) -> list[str]:
    return [p.strip() for p in str(cell).split("|") if p.strip()]


# Return the rows of the combined table that concept tagging covers: CS subject area,
# a named course (slots have no course code and no fixed content), and the school's own
# catalog text. Generic descriptions were written for this project, so they are not
# evidence of what a school teaches (08-concepts.md, "Scope"). One row per (school,
# course code): a course listed twice in a plan (e.g. two semesters) is one course to
# tag, keyed like matches.csv. Shared so the preview, the checker, and the coverage
# build all agree on scope.
def concept_scope_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Return the in-scope rows of the combined table, one per (school, course code)."""
    in_scope = (
        (df["subject_area"] == "cs")
        & (df["course_code"] != "")
        & (df["description_source"] == "official")
    )
    # drop_duplicates keeps the first (earliest-listed) row of each course.
    return df[in_scope].drop_duplicates(["school_id", "course_code"])
