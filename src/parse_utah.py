"""Parse Utah's CS BS sample four-year plan into one row per course or requirement slot.

Utah's school-specific plan parser (batch 4). Reads the newest saved Coursedog API
responses (data/raw/utah/*_cs-bs-programs-api.json and *_cs-bs-courses-api.json, saved
through Chrome; 2026-2027 General Catalog) and the Kahlert School's 2026-27 requirements
sheet (*_cs-requirements-26-27.pdf), and writes data/processed/utah/plan_parsed.csv with
the columns in common.PARSED_COLUMNS.

The program record (CPSCBS, effective 2026-08-17) has a list of degree maps; the plan
used is the one named "Computer Science Sample 4 Year Plan" (the others are emphasis
plans). Each of its eight semesters has a year ("Year 1"), a term ("Fall"), and a list
of requirements. A requirement's "requirementSelect" holds one or more selections:
- {"type": "courses", "value": "<course id>"}: a course, looked up in the courses
  response by id (the part of its key before the first "-"); two course selections in
  one requirement are a choice ("CS 4150 or CS 4400" on the page);
- {"type": "courseAttributes" or "requirementDesignations", "value": "GE - LS (Life
  Sciences)"}: a general education slot;
- {"type": "generic", "value": "CS Electives (6 cr)"}: a labeled slot.
Slot credits are in "actualCredits"; course credits come from the course record.

Modeling decisions (batch 4, for the user's review):
- "CS 4150 or CS 4400" appears in both Year 3 terms, and the 2026-27 requirements sheet
  lists both CS 4150 (Algorithms) and CS 4400 (Computer Systems) in the CS core, so the
  two rows are one all_in_any_order group (Berkeley's ELENG 66/64 precedent): students
  take one each term, in either order. The parser checks the sheet still lists both.
- Other two-course requirements (CS 3100 or CS 3200, WRTG 3014 or 3015, the capstone
  pairs CS 4000 or CS 4940 and CS 4500 or CS 4970) are ordinary choice rows.
- A slot of 6 credits ("CS Electives (6 cr)", "General Electives (6 cr)") becomes two
  3-credit rows, so each elective course is one row (Tennessee's rule).
- General education slots keep the catalog's label as the title ("GE - LS (Life
  Sciences)", "BD - DV (Diversity)") and are gen_ed.

Usage:
    python src/parse_utah.py
"""

import json
import re

import pandas as pd
import pdfplumber

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("utah")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN_NAME = "Computer Science Sample 4 Year Plan"
PLAN = f"{PLAN_NAME}, 2026-2027 General Catalog"
PROGRAM_KEY = "CPSCBS-2026-08-17"
# The pair the plan offers in both Year 3 terms; both are required (see the docstring).
BOTH_REQUIRED = ("CS 4150", "CS 4400")
# Generic slot labels (credits removed) -> (title, requirement_type, notes).
GENERIC = {
    "CS Electives": ("CS Elective", "elective_slot", "Utah: CS electives (3000+ CS courses) from the requirements sheet."),
    "General Elective": ("General Elective", "elective_slot", "Utah: general elective to reach 120 credits."),
    "General Electives": ("General Elective", "elective_slot", "Utah: general elective to reach 120 credits."),
    "Additional Math/Science": ("Additional Math/Science", "elective_slot",
                                "Utah: a math, science, or engineering course with MATH 1220 as a pre- or co-requisite "
                                "(BIOL 1610, CHEM 1210, or PHYS 2010 also accepted), per the requirements sheet."),
}


# A course record's "SUBJ NUM" code from its compact code ("CS1420" -> "CS 1420").
def spaced(code: str) -> str:
    """Return a course code with a space between subject and number."""
    m = re.fullmatch(r"([A-Z]+)(\d{4})", code)
    return f"{m.group(1)} {m.group(2)}" if m else code


# A blank row dict with the defaults every row starts from.
def base_row(credits: int) -> dict:
    """Return a row with fixed credits."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": credits,
            "credits_max": credits, "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": "", "choice_kind": "", "choice_group": ""}


# Turn one degree-map requirement into rows.
def requirement_rows(req: dict, courses: dict) -> list[dict]:
    """Return the plan rows for one requirement."""
    sel = req["requirementSelect"]
    tag = req.get("courseRequirementGroupFreeText", "")  # e.g. "GE-QL", "BD-CW": designations the course meets
    if all(s["type"] == "courses" for s in sel):
        recs = [courses[s["value"]] for s in sel]
        codes = [spaced(r["code"]) for r in recs]
        cr = recs[0]["credits"]["creditHours"]["min"]
        row = base_row(cr)
        row["gened_tag"] = tag
        if len(recs) == 1:
            subj, num = codes[0].split()
            row.update(course_code=codes[0], subject=subj, number=num, title=recs[0]["longName"])
        else:
            subjects = {c.split()[0] for c in codes}
            row.update(title=f"{' or '.join(codes)} ({recs[0]['longName']})",
                       subject=subjects.pop() if len(subjects) == 1 else "", requirement_type="elective_slot",
                       options="; ".join(codes),
                       notes="Utah: choose one: " + " | ".join(f"{c} ({r['longName']})" for c, r in zip(codes, recs)) + ".")
        return [row]
    if len(sel) != 1:
        raise SystemExit(f"Mixed requirement selections: {sel}")
    kind, label = sel[0]["type"], sel[0]["value"].strip()
    credits = req.get("actualCredits", {}).get("min")
    if kind in ("courseAttributes", "requirementDesignations"):
        row = base_row(credits)
        row.update(title=label, requirement_type="gen_ed", gened_tag=tag,
                   notes="Utah general education: a course carrying this attribute or designation.")
        return [row]
    if kind == "generic":
        m = re.fullmatch(r"(.+?) \((\d+) cr\)", label)
        name, total = m.group(1), int(m.group(2))
        title, rtype, note = GENERIC[name]
        return [dict(base_row(3), title=title, requirement_type=rtype, notes=note, gened_tag=tag)
                for _ in range(total // 3)]
    raise SystemExit(f"Unknown selection type: {kind!r}")


# Read the plan's eight semesters into rows.
def parse_plan(program: dict, courses: dict) -> pd.DataFrame:
    """Return the plan rows."""
    plan = [d for d in program["degreeMaps"] if d["degreeMapName"] == PLAN_NAME]
    if len(plan) != 1:
        raise SystemExit(f"Expected one degree map named {PLAN_NAME!r}, found {len(plan)}.")
    rows = []
    for sem in plan[0]["semesters"]:
        year = int(sem["year"].removeprefix("Year "))
        for req in sem["requirements"]:
            for row in requirement_rows(req, courses):
                row.update(orig_year=year, orig_term=sem["semester"])
                rows.append(row)
    df = pd.DataFrame(rows)
    # The CS 4150 / CS 4400 pair in both Year 3 terms is one all_in_any_order group.
    pair = df["options"] == "; ".join(BOTH_REQUIRED)
    df.loc[pair, "choice_kind"] = "all_in_any_order"
    df.loc[pair, "choice_group"] = "cs-4150-4400"
    df.loc[pair, "notes"] = ("Utah: 'CS 4150 or CS 4400' in both Year 3 terms; the 2026-27 requirements sheet "
                             "requires both, so students take one each term, in either order.")
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, requirements: str, stated: int) -> list[str]:
    """Return failed-check messages."""
    failures = []
    got = df["credits_min"].sum()
    if got != stated:
        failures.append(f"Credits {got} != the plan's stated {stated}.")
    if SCHOOL.credits != (stated, stated):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the plan states {stated}.")
    for code in BOTH_REQUIRED:
        if code not in requirements:
            failures.append(f"{code} is no longer on the 2026-27 requirements sheet; recheck the CS 4150/4400 group.")
    if (df["choice_group"] == "cs-4150-4400").sum() != 2:
        failures.append("Expected the CS 4150 / CS 4400 pair in exactly two rows.")
    if len(df.groupby(["orig_year", "orig_term"])) != 8:
        failures.append("Expected 8 semesters.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    program = json.loads(path.read_text(encoding="utf-8"))[PROGRAM_KEY]
    if SCHOOL.college not in program["college"]:
        raise SystemExit(f"College '{SCHOOL.college}' not in {rel(path)} (found {program['college']!r}).")
    if program["effectiveStartDate"] != "2026-08-17":
        raise SystemExit(f"{rel(path)}: program effective {program['effectiveStartDate']}, expected 2026-08-17.")
    narrative = [d for d in program["degreeMaps"] if d["degreeMapName"] == PLAN_NAME][0]["degreeMapNarrative"]
    raw_courses = json.loads(SCHOOL.newest("*_cs-bs-courses-api.json").read_text(encoding="utf-8"))
    # Course records are keyed "<id>-<effective date>"; the plan refers to them by id alone.
    courses = {key.split("-")[0]: rec for key, rec in raw_courses.items()}
    with pdfplumber.open(SCHOOL.newest("*_cs-requirements-26-27.pdf")) as pdf:  # "with" closes the file
        requirements = re.sub(r"(CS) (\d{4})", r"\1 \2", "\n".join(p.extract_text() for p in pdf.pages))
    df = parse_plan(program, courses)
    # The plan's credit total is in its title on the page ("120 credits"); the sheet also says "Minimum 120".
    stated = 120 if "Minimum 120" in requirements else None

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    failures = check(df, requirements, stated)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (stated {stated}); plan note: {re.sub('<[^>]+>', '', narrative)[:80]}...")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All batch 4 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
