"""Parse UIC's CS BS sample course schedule into one row per course or requirement slot.

UIC's school-specific plan parser (phase 2, step 10). Reads the newest saved 2026-2027
catalog page (data/raw/uic/*_bs-cs-catalog.html) and writes
data/processed/uic/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

The page is a CourseLeaf catalog page with two kinds of tables:
- "sc_courselist" tables: the degree requirements (used here for the stated total and a
  cross-check that every named required course is in the schedule).
- one "sc_plangrid" table: the Sample Course Schedule, rows tagged by CSS class:
  plangridyear ("Freshman Year"), plangridterm ("First Semester"), course rows,
  plangridsum (a term's hours), and plangridtotal (the plan's total hours).

Modeling decisions (made with the user in step 10; see PROGRESS.md):
- A choice of courses ("CS 111 or CS 112 or CS 113") is ONE elective_slot row, with
  the option codes in `options` (same idea as UC's science choice).
- ENGR 100 is in the plan but its hour "does not count toward the total hours required
  for graduation" (the page's footnote), so it gets counts_toward_total = False.
- UIC's schedule has no calendar years, so orig_calendar_year is blank, and plan years
  are numbered 1-4 from the "Freshman" ... "Senior" headings.

Usage:
    python src/parse_uic.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("uic")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Sample Course Schedule, 2026-2027 Undergraduate Catalog"

YEARS = {"Freshman Year": 1, "Sophomore Year": 2, "Junior Year": 3, "Senior Year": 4}
TERMS = {"First Semester": "Fall", "Second Semester": "Spring"}  # standard semester order
# One UIC course code, e.g. "CS 251" or "MATH 180": capital-letter subject, space, 3 digits.
CODE = re.compile(r"\b([A-Z]{2,4}) (\d{3})\b")
# Slot labels as UIC writes them -> (title used in the table, requirement_type). UIC
# spells the humanities elective two ways ("Social Science" / "Social Sciences"), so both
# map to one title; that makes them one requirement for descriptions and matching.
SLOTS = {
    "Science Elective": ("Science Elective", "elective_slot"),
    "General Education Core course": ("General Education Core course", "gen_ed"),
    "Required Mathematics course": ("Required Mathematics course", "elective_slot"),
    "Humanities/Social Science/Art Elective": ("Humanities/Social Sciences/Art Elective", "gen_ed"),
    "Humanities/Social Sciences/Art Elective": ("Humanities/Social Sciences/Art Elective", "gen_ed"),
    "Technical Elective": ("Technical Elective", "elective_slot"),
    "Free Elective": ("Free Elective", "elective_slot"),
}
# Notes that explain a slot, from the requirement tables on the same page.
SLOT_NOTES = {
    "Science Elective": "UIC: select two courses (8 hours) from the approved list (e.g. BIOS 110, CHEM 122/123, PHYS 141).",
    "General Education Core course": "UIC requires one course in each of five categories: Exploring World Cultures, "
                                     "Understanding the Creative Arts, Understanding the Past, Understanding the "
                                     "Individual and Society, Understanding U.S. Society. The schedule doesn't say which goes where.",
    "Required Mathematics course": "UIC: 9 hours from an approved list, including at least one of IE 342 or STAT 381.",
    "Technical Elective": "UIC: six courses (18 hours), at most one outside the CS rubric.",
    "Free Elective": "UIC: 9 hours of free electives in total.",
}
ENGR_100_NOTE = ("UIC: ENGR 100 is a one-semester-hour course, but the hour does not count toward the total "
                 "hours required for graduation (counts_toward_total = false). Transfer students take ENGR 101.")


# Text of a cell with non-breaking spaces (CourseLeaf uses &nbsp; in codes) made normal.
def text(cell) -> str:
    """Return a cell's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", cell.get_text(" ").replace("\xa0", " ")).strip()


# Turn one course row of the plan grid into a row dict. The code cell holds a course
# code, several codes joined by "or" (a choice), or a slot label with no code at all.
# The title cell holds the title; CourseLeaf appends footnote letters in <sup> tags,
# which are removed first so "Engineering Success Seminar for Freshmen a" loses the "a".
def parse_row(tr) -> dict:
    """Parse a plan-grid course row into course/slot fields."""
    code_cell = tr.find("td", class_="codecol")
    title_cell = tr.find("td", class_="titlecol")
    for sup in tr.find_all("sup"):
        sup.decompose()  # decompose() deletes the tag and its text from the tree
    label = text(code_cell)
    title = text(title_cell) if title_cell else ""
    hours = int(text(tr.find("td", class_="hourscol")))
    codes = [f"{s} {n}" for s, n in CODE.findall(label)]  # findall gives (subject, number) pairs

    row = {"course_code": "", "subject": "", "number": "", "title": title, "credits_min": hours,
           "credits_max": hours, "requirement_type": "required", "gened_tag": "", "min_grade": "",
           "counts_toward_total": True, "notes": "", "options": ""}
    if len(codes) == 1:
        subj, num = codes[0].split()
        row.update(course_code=codes[0], subject=subj, number=num)
        if codes[0] == "ENGR 100":
            row.update(counts_toward_total=False, notes=ENGR_100_NOTE)
    elif len(codes) > 1:
        # A choice: one slot row, titled with the codes and the first option's title.
        # All options share the subject here (CS 111/112/113), so it is kept.
        subjects = {c.split()[0] for c in codes}
        row.update(subject=subjects.pop() if len(subjects) == 1 else "",
                   title=f"{label} ({title.split(' or ')[0]})", requirement_type="elective_slot",
                   options="; ".join(codes), notes=f"Student chooses one: {title.replace(' or ', ' | ')}.")
    else:
        if label not in SLOTS:
            raise SystemExit(f"Unknown slot label in the plan grid: {label!r}. Add it to SLOTS.")
        slot_title, rtype = SLOTS[label]
        row.update(title=slot_title, requirement_type=rtype, notes=SLOT_NOTES.get(slot_title, ""))
    return row


# Walk the plan grid row by row, tracking the current year and term from the heading
# rows, and collect the stated hours per term and in total for the checks.
def parse_plan(soup) -> tuple[pd.DataFrame, dict, int]:
    """Return (rows, {(year, term): stated hours}, stated total) from the plan grid."""
    grid = soup.find("table", class_="sc_plangrid")
    rows, term_hours, total, year, term = [], {}, None, None, None
    for tr in grid.find_all("tr"):
        classes = tr.get("class") or []  # rows without a class attribute give None
        if "plangridyear" in classes:
            year = YEARS[text(tr)]
        elif "plangridterm" in classes:
            # The first term heading row also contains the "Hours" column header.
            term = TERMS[text(tr.find("th"))]
        elif "plangridsum" in classes:
            term_hours[(year, term)] = int(text(tr.find("td", class_="hourscol")))
        elif "plangridtotal" in classes:
            total = int(text(tr.find("td", class_="hourscol")))
        elif tr.find("td", class_="codecol"):
            r = parse_row(tr)
            r.update(orig_year=year, orig_term=term, orig_calendar_year="",
                     orig_term_type="academic", is_coop=False)
            rows.append(r)
    return pd.DataFrame(rows), term_hours, total


# Named courses in the requirement tables (sc_courselist), for the cross-check that the
# schedule includes every required course. A row whose code cell starts with "or" is an
# alternative to the row above (ENGR 101 for ENGR 100, CS 112 for CS 111), so only the
# first code of a row is taken. The "Required Mathematics" and "Science Electives"
# tables list options, not requirements, so they are skipped.
def required_codes(soup) -> set[str]:
    """Return the course codes listed as required in the degree requirement tables."""
    codes = set()
    for table in soup.find_all("table", class_="sc_courselist"):
        heading = text(table.find_previous(["h2", "h3"]))
        if heading in ("Required Mathematics Courses", "Science Electives", "Technical Electives"):
            continue
        for tr in table.find_all("tr"):
            cell = tr.find("td", class_="codecol")
            if cell is None or text(cell).startswith("or"):
                continue
            found = CODE.findall(text(cell))
            if found:
                codes.add(" ".join(found[0]))
    return codes


# Run the step 10 checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, term_hours: dict, stated: int, required: set[str]) -> list[str]:
    """Return failed-check messages."""
    failures = []
    counted = df[df["counts_toward_total"]]
    if counted["credits_min"].sum() != stated:
        failures.append(f"Counted credits {counted['credits_min'].sum()} != the plan's total {stated}.")
    if SCHOOL.credits != (stated, stated):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the page states {stated}.")
    # Each term's hours row on the page should equal the term's counted credits (UIC's
    # own sums leave ENGR 100 out, so the first term reads 14, not 15).
    for (y, t), hours in term_hours.items():
        got = counted[(counted["orig_year"] == y) & (counted["orig_term"] == t)]["credits_min"].sum()
        if got != hours:
            failures.append(f"Year {y} {t}: counted {got} hours, page says {hours}.")
    in_plan = set(df["course_code"]) | {c for o in df["options"] if o for c in o.split("; ")}
    failures += [f"Required course {c} is not in the sample schedule." for c in sorted(required - in_plan)]
    if len(term_hours) != 8:
        failures.append(f"Expected 8 terms, found {len(term_hours)}.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    df, term_hours, stated = parse_plan(soup)
    required = required_codes(soup)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    counted = df[df["counts_toward_total"]]
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits counted: {counted['credits_min'].sum()} (UIC states {stated}); "
          f"not counted: {', '.join(df.loc[~df['counts_toward_total'], 'course_code'])}")
    print(f"Required courses in the requirement tables: {len(required)} (each checked against the schedule)")
    failures = check(df, term_hours, stated, required)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 10 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
