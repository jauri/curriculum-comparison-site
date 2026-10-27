"""Parse UIUC's CS BS sample sequence into one row per course or requirement slot.

UIUC's school-specific plan parser (step 13, batch 2). Reads the newest saved 2026-2027
catalog page (data/raw/uiuc/*_bs-cs-catalog.html) and writes
data/processed/uiuc/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

The page is a CourseLeaf catalog page, laid out differently from UIC's and TAMU's:
- "sc_courselist" tables: the degree requirements. Used for the stated total ("Total
  Hours of Curriculum to Graduate 128") and to cross-check that every named required
  course is in the sample sequence.
- EIGHT "sc_plangrid" tables, one per semester. Each has a <caption> ("First Semester"
  or "Second Semester") and sits under an <h3>/<h4> heading naming the year ("First
  Year" ... "Fourth Year"). Each row has ONE cell holding "CS 124 - Introduction to
  Computer Science I" (code and title in the same cell, joined by " - ") and an hours
  cell; the footer row "Semester Hours" states the semester's total.

Modeling decisions (step 13):
- "MATH 221 - Calculus I or MATH 220 - Calculus" and "CS 210 ... or CS 211 ..." are
  choices: one elective_slot row with the option codes in `options`, the rule used for
  every school.
- The first two semesters hold "Composition I or General Education (...)" (4 hours)
  and "General Education (...) or Composition I course" (3 hours): the student takes
  Composition I in one of them and a gen-ed course in the other. Their options are
  slot names, not course codes, so they are not modeled as a choice group. Composition I
  is placed in semester 1, where the plan gives 4 hours (the requirements list Composition I
  at 4-6 hours, and the other gen-ed courses at 3), and the swap is explained in both
  rows' notes.
- CS 100 is "optional, highly recommended" and counts as a free elective, so it stays a
  course row (its hour is part of the 128) with that text moved to notes.
- MATH 257 is in the plan; the requirements also allow MATH 415 or MATH 416, which is
  noted on the row.

Usage:
    python src/parse_uiuc.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("uiuc")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Sample Sequence, 2026-2027 Course Catalog"

YEARS = {"First Year": 1, "Second Year": 2, "Third Year": 3, "Fourth Year": 4}
TERMS = {"First Semester": "Fall", "Second Semester": "Spring"}  # standard semester order
# One UIUC course code, e.g. "CS 124" or "MATH 221": capital-letter subject, space, 3 digits.
CODE = re.compile(r"\b([A-Z]{2,4}) (\d{3})\b")
# "CODE - Title" pieces of a cell, possibly several joined by " or ". The lookahead
# (?=...) ends a title at the next " or CODE" or at the end of the cell without
# consuming it, so findall returns each (subject, number, title) in turn.
PIECE = re.compile(r"([A-Z]{2,4}) (\d{3}) - (.+?)(?= or [A-Z]{2,4} \d{3} - |$)")

COMP_NOTE = ("UIUC's semester 1 reads 'Composition I or General Education (choose a Humanities or "
             "Social/Behavioral Science course)' (4 hours) and semester 2 'General Education (...) or "
             "Composition I course' (3 hours): Composition I goes in one semester and a gen-ed course in "
             "the other. Placed here because Composition I is 4-6 hours and gen-ed courses are 3.")
# Slot labels as UIUC writes them, lowercased (the plan capitalizes "choose" both ways)
# -> (title, requirement_type, notes).
SLOTS = {
    "science elective course": ("Science Elective", "elective_slot",
        "UIUC: one course from the Natural Science & Technology list, in addition to PHYS 211 and 212 "
        "(exceptions: ASTR 100, PHYS 101/102, CHEM 101)."),
    "composition i or general education (choose a humanities or social/behavioral science course)":
        ("Composition I", "gen_ed", COMP_NOTE),
    "general education (choose a humanities or social/behavioral science course) or composition i course":
        ("General Education course (Humanities or Social/Behavioral Science)", "gen_ed", COMP_NOTE),
    "general education course (choose a humanities or social/behavioral science course with cultural studies designation)":
        ("General Education course (Humanities or Social/Behavioral Science, Cultural Studies)", "gen_ed",
         "UIUC general education: Humanities & the Arts (6 hours), Social & Behavioral Sciences (6 hours), "
         "and one course in each of three Cultural Studies categories; Advanced Composition (3 hours) is "
         "also required and not placed in the plan."),
    "language other than english (3rd level) course": ("Language Other Than English (3rd level)", "gen_ed",
        "UIUC language requirement: completion of the third semester of a language other than English "
        "(0-15 hours, depending on high school study or placement)."),
    "free elective course": ("Free Elective", "elective_slot",
        "UIUC: additional course work, subject to the Grainger College of Engineering restrictions on "
        "free electives, to reach 128 hours."),
    "cs technical elective course": ("CS Technical Elective", "elective_slot",
        "UIUC: at least six technical electives (18 hours) from CS 397 and the CS 400-level courses, "
        "with at least one course in each of several focus areas."),
    "cs advanced elective course": ("CS Advanced Elective", "elective_slot",
        "UIUC: at least two advanced electives (6 hours), taken for a letter grade, distinct from the "
        "technical electives."),
}
NOTES = {
    "MATH 257": "UIUC's requirements also allow MATH 415 or MATH 416 for this course.",
    "ENG 100": "External transfer students take ENG 300 instead.",
}


# Text of a cell with non-breaking spaces (CourseLeaf uses &nbsp; in codes) made normal.
def text(cell) -> str:
    """Return a cell's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", cell.get_text(" ").replace("\xa0", " ")).strip()


# A blank row dict with the defaults every row starts from.
def base_row(hours: int) -> dict:
    """Return a required-course row with the given hours."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": hours,
            "credits_max": hours, "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": ""}


# Turn one plan cell into a row: one course ("CS 124 - Intro..."), a choice of courses
# joined by " or ", or a slot label with no course code.
def parse_cell(label: str, hours: int) -> dict:
    """Return the row for a plan-grid cell."""
    row = base_row(hours)
    pieces = PIECE.findall(label)
    if len(pieces) == 1:
        subj, num, title = pieces[0]
        code = f"{subj} {num}"
        # CS 100's title carries "(Optional course, highly recommended, Free Elective)";
        # rpartition(" (") splits at the LAST " (" so the parenthetical goes to notes.
        if title.endswith(")") and "Optional" in title:
            title, _, extra = title.rpartition(" (")
            row["notes"] = f"UIUC: {extra.rstrip(')')}; its hour counts as a free elective."
        row.update(course_code=code, subject=subj, number=num, title=title)
        row["notes"] = row["notes"] or NOTES.get(code, "")
    elif len(pieces) > 1:
        codes = [f"{s} {n}" for s, n, _ in pieces]
        titles = [t for _, _, t in pieces]
        subjects = {s for s, _, _ in pieces}
        row.update(subject=subjects.pop() if len(subjects) == 1 else "",
                   title=f"{' or '.join(codes)} ({titles[0]})", requirement_type="elective_slot",
                   options="; ".join(codes), notes=f"Student chooses one: {' | '.join(titles)}.")
        if codes[0] == "MATH 221":
            row["notes"] += (" UIUC: MATH 220 is for students with no calculus background; 4 of its 5 hours "
                             "count toward the degree.")
    else:
        key = label.lower()
        if key not in SLOTS:
            raise SystemExit(f"Unknown slot label in the plan grid: {label!r}. Add it to SLOTS.")
        title, rtype, notes = SLOTS[key]
        row.update(title=title, requirement_type=rtype, notes=notes)
    return row


# Walk the eight semester grids. The year comes from the nearest <h3>/<h4> above each
# grid whose text is a year name; find_all_previous walks back through the document,
# so the second grid of a year (whose nearest heading is the first grid's caption)
# still finds the year heading.
def parse_plan(soup) -> tuple[pd.DataFrame, dict]:
    """Return (rows, {(year, term): stated hours})."""
    rows, term_hours = [], {}
    for grid in soup.find_all("table", class_="sc_plangrid"):
        # next() with a default: the first heading above whose text is a year, or None.
        heading = next((h for h in grid.find_all_previous(["h2", "h3", "h4"]) if text(h) in YEARS), None)
        if heading is None:
            raise SystemExit(f"No year heading above plan grid {grid.get('id')}.")
        year, term = YEARS[text(heading)], TERMS[text(grid.caption)]
        for tr in grid.find("tbody").find_all("tr"):
            r = parse_cell(text(tr.find("td", class_="codecol")), int(text(tr.find("td", class_="hourscol"))))
            r.update(orig_year=year, orig_term=term)
            rows.append(r)
        term_hours[(year, term)] = int(text(grid.find("tr", class_="plangridsum").find("td")))
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, term_hours


# Codes of the named required courses in the requirement tables (orientation, math and
# science, CS core). "orclass" rows are alternatives ("or MATH 415") and are skipped;
# only a row's first code counts, so notes inside titles ("MATH 220 may be
# substituted") are ignored.
def required_codes(soup) -> set[str]:
    """Return the first course code of each non-alternative requirement row."""
    codes = set()
    for table in soup.find_all("table", class_="sc_courselist"):
        # The technical and advanced elective tables list every course a student may
        # choose from; they are slots in the plan, not required courses.
        if re.search(r"technical electives|advanced elective", text(table), re.IGNORECASE):
            continue
        for tr in table.find_all("tr"):
            cell = tr.find("td", class_="codecol")
            if cell is None or "orclass" in (tr.get("class") or []):
                continue
            m = CODE.fullmatch(text(cell))  # fullmatch: the code cell is exactly one code
            if m:
                codes.add(f"{m.group(1)} {m.group(2)}")
    return codes


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, term_hours: dict, stated: int, required: set[str]) -> list[str]:
    """Return failed-check messages."""
    failures = []
    total = df["credits_min"].sum()
    if total != stated:
        failures.append(f"Credits {total} != the page's Total Hours of Curriculum to Graduate {stated}.")
    if SCHOOL.credits != (stated, stated):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the page states {stated}.")
    for (y, t), hours in term_hours.items():
        got = df[(df["orig_year"] == y) & (df["orig_term"] == t)]["credits_min"].sum()
        if got != hours:
            failures.append(f"Year {y} {t}: {got} hours, page says {hours}.")
    if len(term_hours) != 8:
        failures.append(f"Expected 8 semester grids, found {len(term_hours)}.")
    # Every code in the plan, as a course or as an option of a choice.
    in_plan = set(df["course_code"]) | {o for opts in df["options"] if opts for o in opts.split("; ")}
    for code in sorted(required - in_plan):
        failures.append(f"Required course {code} is not in the sample sequence.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page = text(soup)
    if SCHOOL.college not in page:
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(path)}.")
    m = re.search(r"Total Hours of Curriculum to Graduate (\d+)", page)
    if not m:
        raise SystemExit(f"'Total Hours of Curriculum to Graduate' not found on {rel(path)}.")
    stated = int(m.group(1))
    df, term_hours = parse_plan(soup)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (UIUC states {stated})")
    failures = check(df, term_hours, stated, required_codes(soup))
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 13 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
