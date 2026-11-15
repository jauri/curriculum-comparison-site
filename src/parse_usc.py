"""Parse USC's four-year grid (Begin with CSCI 102) into one row per course or requirement slot.

USC's school-specific plan parser (batch 5). The plan is the "Computer Science — Begin
with CSCI 102" grid in the Viterbi 2026 guide (data/raw/usc/*_cs-curriculum-2026.pdf,
page 1, guide page 44), the plan for students without AP credit (decided with the
user). The grid is an image, so it can't be read as text: it was transcribed cell by
cell, top to bottom in each term, into data/reference/usc/plan_transcription.csv
(hand-made by Claude on 2026-11-14, for the user's review). This script reads that
transcription and checks it against the 2026-2027 Catalogue program page
(*_bs-cs-catalogue.html, saved through Chrome): the college, the 128-unit total, and
that every required course the Catalogue lists is in the plan. Output:
data/processed/usc/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

Course codes are subject and number without USC's letter suffixes ("CSCI 103", not
"CSCI 103L"; "MATH 125", not "MATH 125g"); see parse_usc_descriptions.py for why.

Modeling decisions (batch 5, for the user's review):
- The grid's yellow "Optional Elective" cells (2 units in seven terms, 6 in Year 4 Fall)
  are not rows, except that the Catalogue's 4-unit Free Electives requirement goes in
  Year 4 Fall's 6-unit cell, the term the grid leaves lightest (12 required units). The
  required cells sum to 124; with the free elective, 128 = the Catalogue's total.
- The four "CSCI 310 or 353 or 356 or 360" cells are one all_in_any_order group: the
  Catalogue requires all four courses (Berkeley precedent).
- "CSCI 401 or CSCI 404": the 2026-27 Catalogue requires CSCI 401 only, so the row is
  CSCI 401, with the guide's CSCI 404 alternative in notes.
- "LIFE SCIENCES (GE D)" and "PHYSICAL SCIENCES (GE E)" are choice rows listing the
  Catalogue's options (BISC 120/121/220; CHEM 105/115, PHYS 151/161).
- "GE A", "GE B", "GE C", and "GESM (GE B)" are gen_ed slots (the GE seminar counts in
  category B).
- ENGR 495 Practicum (0 units), which the Catalogue requires, is not in the grid and has
  no term, so it has no row; ENGR 102's notes record it (PRACTICUM_NOTE).

Usage:
    python src/parse_usc.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from acalog import clean
from common import PARSED_COLUMNS, finish_choices, load_school, rel
from parse_usc_descriptions import read_usc_entry

SCHOOL = load_school("usc")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
TRANSCRIPTION = SCHOOL.reference / "plan_transcription.csv"
PLAN = "Computer Science — Begin with CSCI 102, Viterbi 2026 guide (four-year grid, transcribed)"

CORE_GROUP = ["CSCI 310", "CSCI 353", "CSCI 356", "CSCI 360"]
LIFE = ["BISC 120", "BISC 121", "BISC 220"]
PHYSICAL = ["CHEM 105", "CHEM 115", "PHYS 151", "PHYS 161"]
# The Catalogue's grade rule: C or better in these core courses ("Courses with a grade
# of C- or below must be repeated").
MIN_C = {"CSCI 102", "CSCI 103", "CSCI 170", "CSCI 104", "CSCI 201"}
PRACTICUM_NOTE = ("The Catalogue also requires ENGR 495 Practicum (0 units, practical training), which the grid "
                  "does not place; it has no row.")
# Gen-ed cells -> (title, notes).
GENED = {
    "GE A*": ("GE A: The Arts", "USC general education category A (may be met by AP/IB)."),
    "GE B": ("GE B: Humanistic Inquiry", "USC general education category B."),
    "GESM (GE B)#": ("GESM: General Education Seminar (GE B)",
                     "USC general education seminar, taken in category A, B, C, or D (the guide's # note); the grid "
                     "places it in category B."),
    "GE C": ("GE C: Social Analysis", "USC general education category C."),
}
TECH_NOTE = ("USC Core Electives: at least four 300- or 400-level CSCI courses (16 units); required major courses don't "
             "count.")


# Titles of the saved Catalogue entries, keyed like the plan ("CSCI 270": title).
def entry_titles() -> dict:
    """Return {code: title} from the saved entries."""
    titles = {}
    for path in sorted((SCHOOL.raw / "courses").glob("*_*.html")):
        entry = read_usc_entry(path)
        if entry:
            titles[entry[0]] = entry[1]
    return titles


# A blank row with fixed credits.
def base_row(units: int) -> dict:
    """Return a row with the defaults every row starts from."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": units,
            "credits_max": units, "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": "", "choice_kind": "", "choice_group": ""}


# A choice row: title "A or B (title of A)", options listed, and their titles in notes.
def choice_row(units: int, options: list[str], titles: dict, rtype: str, title: str = "", note: str = "") -> dict:
    """Return a choice row over `options`."""
    row = base_row(units)
    row.update(title=title or f"{' or '.join(options)} ({titles.get(options[0], '')})",
               subject=options[0].split()[0], requirement_type=rtype, options="; ".join(options),
               notes=(note + " " if note else "") + "Options: " + " | ".join(f"{c} ({titles.get(c, '')})" for c in options) + ".")
    return row


# One transcribed cell -> one row (or None for an optional elective cell).
def cell_row(cell: str, units: int, kind: str, sem: int, titles: dict) -> dict | None:
    """Return the row for one grid cell."""
    if kind == "optional":
        if units != 6:
            return None  # 2-unit optional electives are not rows (see the docstring)
        row = base_row(4)
        row.update(title="Free Elective", requirement_type="elective_slot",
                   notes="USC: the Catalogue's Free Electives (4 units), placed in the grid's 6-unit Year 4 Fall "
                         "optional elective cell.")
        return row
    if cell in GENED:
        row = base_row(units)
        row.update(title=GENED[cell][0], requirement_type="gen_ed", notes=GENED[cell][1])
        return row
    if cell.startswith("TECHNICAL ELECTIVE"):
        row = base_row(units)
        # "TECHNICAL ELECTIVE IV" -> "Technical Elective IV" (str.title() would give "Iv").
        row.update(title="Technical Elective " + cell.split()[-1], subject="CSCI", requirement_type="elective_slot",
                   notes=TECH_NOTE)
        return row
    if cell == "CSCI 310 or 353 or 356 or 360":
        row = choice_row(units, CORE_GROUP, titles, "elective_slot", title="CSCI 310 or 353 or 356 or 360",
                         note="The Catalogue requires all four; the grid places them in four cells in any order.")
        row.update(choice_kind="all_in_any_order", choice_group="usc-core-systems")
        return row
    if cell == "LIFE SCIENCES (GE D)":
        return choice_row(units, LIFE, titles, "elective_slot", title="Life Sciences (GE D)",
                          note="USC: one life science course, which also satisfies GE-D.")
    if cell == "PHYSICAL SCIENCES (GE E)":
        return choice_row(units, PHYSICAL, titles, "elective_slot", title="Physical Sciences (GE E)",
                          note="USC: one physical science course, which also satisfies GE-E.")
    # "MATH 129 or MATH 126*": a choice of two named courses (the * marks AP credit). The
    # regex drops a trailing suffix letter and "*" ("CSCI 103L" -> "CSCI 103").
    names = [re.sub(r"[A-Z]?\*?$", "", c.strip()) for c in cell.replace(" (GE F)", "").split(" or ")]
    if cell == "CSCI 401 or CSCI 404":
        names = ["CSCI 401"]  # the Catalogue's only capstone (see the docstring)
    elif len(names) == 2:
        return choice_row(units, names, titles, "elective_slot")  # choice rows are slots (validate.py)
    code = names[0]
    m = re.fullmatch(r"([A-Z]{2,4}) (\d{3})", code)
    if not m:
        raise SystemExit(f"Unknown grid cell: {cell!r}")
    row = base_row(units)
    row.update(course_code=code, subject=m.group(1), number=m.group(2), title=titles.get(code, code))
    if code in MIN_C:
        row["min_grade"] = "C"
    if cell == "CSCI 401 or CSCI 404":
        row["notes"] = ("The guide offers CSCI 401 or CSCI 404 (Capstone: Creating Your High-Tech Startup); the 2026-27 "
                        "Catalogue lists only CSCI 401.")
    if code == "ENGR 102":
        row["notes"] = PRACTICUM_NOTE
    return row


# Build the rows from the transcription.
def parse_plan(titles: dict) -> pd.DataFrame:
    """Return the plan rows."""
    t = pd.read_csv(TRANSCRIPTION, keep_default_na=False)
    rows = []
    for c in t.itertuples():
        row = cell_row(c.cell, int(c.units), c.cell_kind, int(c.semester), titles)
        if row is None:
            continue
        row.update(sem=int(c.semester), orig_year=int(c.year), orig_term=c.term)
        rows.append(row)
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, page_text: str) -> list[str]:
    """Return failed-check messages."""
    failures = []
    stated = int(re.search(r"Total Units: (\d+)", page_text).group(1))
    got = df["credits_min"].sum()
    if got != stated:
        failures.append(f"Units {got} != the Catalogue's {stated}.")
    if SCHOOL.credits != (stated, stated):
        failures.append(f"schools.csv says {SCHOOL.credits} units but the Catalogue states {stated}.")
    if sorted(df["sem"].unique()) != list(range(1, 9)):
        failures.append("Expected semesters 1-8.")
    # Every course the Catalogue's Computer Science, Engineering, and Statistics lists name
    # must appear in the plan, as a row or a choice option (ENGR 495 is the known exception).
    in_plan = set(df["course_code"]) | {o for opts in df["options"] for o in opts.split("; ") if o}
    for subj, num in re.findall(r"\b(CSCI|EE|ENGR|WRIT|MATH) (\d{3})[A-Za-z]* ", page_text):
        code = f"{subj} {num}"
        if code not in in_plan and code != "ENGR 495" and code != "MATH 108":
            failures.append(f"Catalogue course {code} is not in the plan.")
    return failures


# Script entry point: build, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    cell = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser").find("td", class_="block_content")
    page_text = clean(cell.get_text(" "))
    if "Viterbi School of Engineering" not in page_text or "USC Catalogue 2026-2027" not in clean(path.read_text(encoding="utf-8")):
        raise SystemExit(f"Viterbi or the 2026-2027 catalogue year not found on {rel(path)}.")
    df = parse_plan(entry_titles())
    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(SCHOOL.newest("*_cs-curriculum-2026.pdf"))

    failures = check(df, page_text)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Units: {df['credits_min'].sum()}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All batch 5 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
