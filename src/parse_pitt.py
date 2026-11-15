"""Parse Pitt's Sample Plan of Study into one row per course or requirement slot.

Pitt's school-specific plan parser (batch 5). Reads the newest saved 2026-2027
Undergraduate Catalog program page (data/raw/pitt/*_bs-cs-catalog.html, saved through
Chrome) and writes data/processed/pitt/plan_parsed.csv with the columns in
common.PARSED_COLUMNS.

The Sample Plan of Study is an HTML table: a header row (FALL, SPRING) and one row per
year ("YEAR 1" ... "YEAR 4"), each holding two cells. A cell lists its courses as
"CMPINF 0401 (4 cr) MATH 0220 (4 cr) ... TOTAL: 16 credits", so each entry is a name
followed by "(N cr)", and the cell ends with the term's stated total.

Modeling decisions (batch 5, for the user's review):
- "GER" (General Education Requirement, note 1) is a gen_ed slot; "Elective" is a free
  elective slot; "CS UL n" (upper-level elective, 1500 or higher) is a CS elective slot.
- "CS UL 7 or Elective": the major requires six upper-level electives, and note 4 says a
  seventh counts toward departmental honors, so this is a free elective slot (notes say
  so).
- "Capstone" is a choice of the capstone courses the page lists (CS 1900, 1906, 1950,
  1980); the page also allows two co-op rotations, which CS 1906 stands for.
- MATH 0280's alternative MATH 1180 (Linear Algebra 1) goes in notes.
- The plan assumes an introductory programming course before CMPINF 0401 (usually high
  school experience; such preparatory courses don't count toward the major), so no row
  is added for it; CMPINF 0401's notes say so.
- Credits are the plan's row sums (122), which match its term totals. The program page
  states no degree total (only "Total Major Credits: 54"); schools.csv records 122.

Usage:
    python src/parse_pitt.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from acalog import clean, read_entry
from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("pitt")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Sample Plan of Study, Computer Science, BS, 2026-2027 Undergraduate Catalog"

# One plan entry: a name, then its credits in parentheses, e.g. "CS 0445 (3 cr)",
# "GER (3 cr)", "CS UL 7 or Elective (3 cr)". The non-greedy (.+?) stops at the first
# "(N cr)", so consecutive entries split cleanly.
ENTRY = re.compile(r"(.+?) \((\d+) cr\)")
CODE = re.compile(r"^([A-Z]{2,6}) (\d{4})$")  # "CMPINF 0401", "CS 1501"
CAPSTONE_OPTIONS = ["CS 1900", "CS 1906", "CS 1950", "CS 1980"]
# Slot names -> (title, requirement_type, notes).
SLOTS = {
    "GER": ("General Education Requirement (GER)", "gen_ed",
            "Pitt: a School of Computing and Information general education course (note 1); one course must "
            "satisfy the Diversity Requirement (note 3)."),
    "Elective": ("Elective", "elective_slot",
                 "Pitt: free elective; electives may be used for the SCI requirement of a secondary field of study, "
                 "such as a minor or certificate (note 2)."),
    "CS UL": ("CS Upper-Level Elective", "elective_slot",
              "Pitt: one of six required upper-level CS electives (18 credits, numbered 1500 or higher; internships, "
              "directed studies, capstone and co-op courses don't count)."),
    "CS UL 7 or Elective": ("CS Upper-Level Elective or Elective", "elective_slot",
                            "Pitt: the major requires six upper-level electives; a seventh counts toward CS "
                            "departmental honors (note 4), otherwise this is a free elective."),
    "Capstone": ("Capstone Experience", "elective_slot",
                 "Pitt: an approved 3-credit internship (CS 1900), directed research project (CS 1950), team project "
                 "course (CS 1980), or at least two co-op rotations (CS 1906). A capstone course may not replace an "
                 "upper-level elective."),
}
NOTES = {
    "CMPINF 0401": "The plan assumes an introductory programming course before CMPINF 0401 (usually high school "
                   "experience, or a service course such as CS 0007, which doesn't count toward the major).",
    "MATH 0280": "Students may take MATH 1180 (Linear Algebra 1) instead of MATH 0280.",
}


# Titles of the saved course entries ("CS 1501 - ALGORITHMS AND DATA STRUCTURES 2"),
# in the catalog's capitals.
def entry_titles() -> dict:
    """Return {code: title} from the saved entries."""
    titles = {}
    for path in sorted((SCHOOL.raw / "courses").glob("*_*.html")):
        entry = read_entry(path)
        if entry:
            titles[f"{entry[0]} {entry[1]}"] = entry[2]
    return titles


# One row for one plan entry.
def entry_row(name: str, credits: int, titles: dict) -> dict:
    """Return the row for a plan entry such as 'CS 0445' or 'GER'."""
    row = {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": credits,
           "credits_max": credits, "requirement_type": "required", "gened_tag": "", "min_grade": "",
           "counts_toward_total": True, "notes": "", "options": ""}
    m = CODE.match(name)
    if m:
        row.update(course_code=name, subject=m.group(1), number=m.group(2), title=titles.get(name, name),
                   notes=NOTES.get(name, ""))
        if m.group(1) == "CS" or name == "CMPINF 0401":
            row["min_grade"] = "C"  # CS major courses need a C or better (Individual Course Grades)
        return row
    key = "CS UL" if re.fullmatch(r"CS UL \d", name) else name  # "CS UL 1" ... "CS UL 6"
    if key not in SLOTS:
        raise SystemExit(f"Unknown plan entry: {name!r}")
    title, rtype, note = SLOTS[key]
    row.update(title=title, requirement_type=rtype, notes=note)
    if key == "CS UL":
        row["subject"] = "CS"
    if key == "Capstone":
        row.update(subject="CS", options="; ".join(CAPSTONE_OPTIONS),
                   notes=note + " Options: " + " | ".join(f"{c} ({titles.get(c, '')})" for c in CAPSTONE_OPTIONS))
    return row


# Find the plan table and turn every cell into rows; return the rows and each term's
# stated total.
def parse_plan(soup: BeautifulSoup, titles: dict) -> tuple[pd.DataFrame, dict]:
    """Return (rows, {semester: stated total})."""
    # The plan is the only table whose text has both "YEAR 1" and "TOTAL:".
    table = next(t for t in soup.find_all("table") if "YEAR 1" in t.get_text() and "TOTAL:" in t.get_text())
    rows, totals = [], {}
    for tr in table.find_all("tr"):
        cells = [clean(c.get_text(" ")) for c in tr.find_all(["td", "th"])]
        m = re.fullmatch(r"YEAR (\d)", cells[0])
        if not m:
            continue  # the FALL / SPRING header row
        year = int(m.group(1))
        for side, cell in enumerate(cells[1:3]):  # side 0 = Fall, 1 = Spring
            sem = 2 * year - 1 + side
            body, total = cell.split("TOTAL:")
            totals[sem] = int(re.search(r"\d+", total).group(0))
            for name, cr in ENTRY.findall(body):
                row = entry_row(name.strip(), int(cr), titles)
                row.update(sem=sem, orig_year=year, orig_term="Fall" if side == 0 else "Spring")
                rows.append(row)
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, totals


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, totals: dict, page_text: str) -> list[str]:
    """Return failed-check messages."""
    failures = []
    for k, n in totals.items():
        s = df[df["sem"] == k]["credits_min"].sum()
        if s != n:
            failures.append(f"Semester {k}: {s} credits, plan says {n}.")
    if sorted(totals) != list(range(1, 9)):
        failures.append(f"Expected semesters 1-8, found {sorted(totals)}.")
    got = df["credits_min"].sum()
    if SCHOOL.credits != (got, got):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the plan sums to {got}.")
    # Every core course the page lists must be in the plan, and six CS UL slots.
    for code in re.findall(r"((?:CS|CMPINF) \d{4}) - ", page_text.split("Core Courses", 1)[1].split("Upper-Level", 1)[0]):
        if code not in set(df["course_code"]):
            failures.append(f"Core course {code} is not in the plan.")
    if (df["title"] == "CS Upper-Level Elective").sum() != 6:
        failures.append("Expected six CS upper-level elective slots.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page_text = clean(soup.get_text(" "))
    if SCHOOL.college not in page_text or "2026-2027 Undergraduate Catalog" not in page_text:
        raise SystemExit(f"College '{SCHOOL.college}' or the catalog year not found on {rel(path)}.")
    df, totals = parse_plan(soup, entry_titles())
    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    failures = check(df, totals, page_text)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All batch 5 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
