"""Parse UT Austin's CS BS plan of study into one row per course or requirement slot.

UT Austin's school-specific plan parser (step 13). Reads the newest saved 2026-2028
catalog page for the BSCompSci, Computer Science Option
(data/raw/utaustin/*_bscompsci-cs-option-catalog.html) and writes
data/processed/utaustin/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

The page is a CourseLeaf catalog page, like UIC's:
- one "sc_plangrid" table: the Plan of Study, with rows tagged by CSS class:
  plangridyear ("Year 1"), plangridterm ("Semester 1"), course rows, plangridsum (a
  term's hours), and plangridtotal (the plan's total hours, 120).
- "sc_courselist" tables: the degree requirements, used here for the cross-check that
  every named required course is in the plan.

Modeling decisions (same rules as the step 10 pilot):
- A choice ("M 408C or M 408N", "SDS 321 or M 362K") is ONE elective_slot row with the
  option codes in `options`.
- UT writes course codes with a space inside the subject ("C S 312"); they are kept
  exactly as written. In UT's numbers the first digit is the credit hours (C S 312 is a
  3-hour course), which parse_utaustin_descriptions.py relies on.
- Rows labeled with a Texas Core Curriculum code in parentheses ("U.S. History (060)")
  are gen_ed slots with that code in `gened_tag`.
- UT's plan has no calendar years, so orig_calendar_year is blank; plan years are 1-4
  from the "Year N" headings, and "Semester 1" / "Semester 2" are Fall / Spring.

Usage:
    python src/parse_utaustin.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("utaustin")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Plan of Study, 2026-2028 Undergraduate Catalog (Computer Science Option)"

TERMS = {"Semester 1": "Fall", "Semester 2": "Spring"}  # standard semester order
# One UT course code: a subject of capital letters that may contain single spaces
# ("C S", "M", "GOV"), a space, then three digits and optional letters ("103F", "310L").
# (?:[A-Z] )* allows the "C " in "C S"; the trailing \b stops it from eating a title word.
CODE = re.compile(r"\b((?:[A-Z] )*[A-Z]+) (\d{3}[A-Z]{0,2})\b")
# A Texas Core Curriculum component code at the end of a slot label, e.g. "(060)".
CORE = re.compile(r"\((0\d0)\)")
# Slot labels as UT writes them (after footnotes are removed) -> (title, requirement_type).
SLOTS = {
    "U.S. History (060)": ("U.S. History (060)", "gen_ed"),
    "Social and Behavioral Sciences (080)": ("Social and Behavioral Sciences (080)", "gen_ed"),
    "First-Year Signature Course (090) approved by departmental advisor": ("First-Year Signature Course (090)", "gen_ed"),
    "Visual and Performing Arts (050)": ("Visual and Performing Arts (050)", "gen_ed"),
    "Natural Science and Technology, Part I (030)": ("Natural Science and Technology, Part I (030)", "gen_ed"),
    "Humanities (040)": ("Humanities (040)", "gen_ed"),
    "Foreign Language and Culture": ("Foreign Language and Culture", "gen_ed"),
    "Hours chosen from: Upper-division C S": ("Upper-division C S elective", "elective_slot"),
    "Math or Science course": ("Math or Science course", "elective_slot"),
    "Free Elective": ("Free Elective", "elective_slot"),
}
# Notes that explain a slot, from the requirement tables on the same page.
SLOT_NOTES = {
    "Natural Science and Technology, Part I (030)": "UT: the major requires a two-course science sequence (6 hours): "
        "BIO 311C/311D, BIO 315H/325H, CH 301/302, or a physics sequence with labs (e.g. PHY 303K/303L).",
    "Foreign Language and Culture": "UT: 6 hours: a beginning foreign language course and a culture course of the same "
        "language area, or two courses in one foreign culture (or beginning proficiency).",
    "Upper-division C S elective": "UT: 12 hours of additional upper-division C S for the major, plus 12 more for the "
        "Computer Science Option concentration (8 courses in the plan).",
    "Math or Science course": "UT: 3 hours from an additional biology, chemistry, or physics sequence course, GEO 303 or "
        "GEO 301, or upper-division mathematics (excluding M 325K, 340L, 341, 362K).",
    "Free Elective": "UT: coursework to reach the 120 hours the degree requires.",
}
# Minimum grades stated in the major requirements ("minimum grade of C- within two attempts").
MIN_GRADES = {"C S 311": "C-", "C S 314": "C-", "C S 331": "C-", "C S 429": "C-", "C S 439": "C-"}


# Text of a cell with non-breaking spaces (CourseLeaf uses &nbsp; in codes) made normal.
def text(cell) -> str:
    """Return a cell's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", cell.get_text(" ").replace("\xa0", " ")).strip()


# Turn one course row of the plan grid into a row dict. The code cell holds one code,
# codes joined by "or" (a choice), or a slot label with no code (then it spans the
# title column too, colspan="2"). Footnote markers in <sup> tags are removed first.
def parse_row(tr) -> dict:
    """Parse a plan-grid course row into course/slot fields."""
    for sup in tr.find_all("sup"):
        sup.decompose()  # decompose() deletes the tag and its text from the tree
    label = text(tr.find("td", class_="codecol"))
    title_cell = tr.find("td", class_="titlecol")
    title = text(title_cell) if title_cell else ""
    hours = int(text(tr.find("td", class_="hourscol")))
    codes = [f"{s} {n}" for s, n in CODE.findall(label)]  # findall gives (subject, number) pairs

    row = {"course_code": "", "subject": "", "number": "", "title": title, "credits_min": hours,
           "credits_max": hours, "requirement_type": "required", "gened_tag": "", "min_grade": "",
           "counts_toward_total": True, "notes": "", "options": ""}
    if len(codes) == 1:
        subj, num = codes[0].rsplit(" ", 1)  # rsplit: the subject itself may contain a space
        row.update(course_code=codes[0], subject=subj, number=num, min_grade=MIN_GRADES.get(codes[0], ""))
    elif len(codes) > 1:
        # A choice: one slot row, titled with the codes and the first option's title.
        # The subject is kept only when every option shares it.
        subjects = {c.rsplit(" ", 1)[0] for c in codes}
        row.update(subject=subjects.pop() if len(subjects) == 1 else "",
                   title=f"{label} ({title.split(' or ')[0]})", requirement_type="elective_slot",
                   options="; ".join(codes), notes=f"Student chooses one: {title.replace(' or ', ' | ')}.")
    else:
        if label not in SLOTS:
            raise SystemExit(f"Unknown slot label in the plan grid: {label!r}. Add it to SLOTS.")
        slot_title, rtype = SLOTS[label]
        core = CORE.search(slot_title)
        row.update(title=slot_title, requirement_type=rtype, gened_tag=core.group(1) if core else "",
                   notes=SLOT_NOTES.get(slot_title, ""))
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
            year = int(text(tr).split()[-1])  # "Year 3" -> 3
        elif "plangridterm" in classes:
            term = TERMS[text(tr.find("th"))]  # the first term row also holds the "Hours" header
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


# Named required courses in the major's requirement table, for the cross-check that the
# plan includes each one. Only the "Major-Computer Science" list is used: it names the
# CS core (C S 311, 314, 331, 429, 439). Its math and science entries are sequences to
# choose from, so a code is taken only from rows that are a single course with hours
# (not "or" alternatives and not rows inside a "Choose a sequence" block).
def required_codes(soup) -> set[str]:
    """Return the CS core course codes listed in the major requirements."""
    codes = set()
    for table in soup.find_all("table", class_="sc_courselist"):
        if not text(table.find_previous(["h2", "h3"])).startswith("Major-"):
            continue
        for tr in table.find_all("tr"):
            cell, hours = tr.find("td", class_="codecol"), tr.find("td", class_="hourscol")
            if cell is None or hours is None or not text(hours) or text(cell).startswith("or"):
                continue
            found = CODE.findall(text(cell))
            if found and found[0][0] == "C S":
                codes.add(" ".join(found[0]))
    return codes


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, term_hours: dict, stated: int, required: set[str]) -> list[str]:
    """Return failed-check messages."""
    failures = []
    if df["credits_min"].sum() != stated:
        failures.append(f"Credits {df['credits_min'].sum()} != the plan's total {stated}.")
    if SCHOOL.credits != (stated, stated):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the page states {stated}.")
    for (y, t), hours in term_hours.items():
        got = df[(df["orig_year"] == y) & (df["orig_term"] == t)]["credits_min"].sum()
        if got != hours:
            failures.append(f"Year {y} {t}: {got} hours, page says {hours}.")
    in_plan = set(df["course_code"]) | {c for o in df["options"] if o for c in o.split("; ")}
    failures += [f"Required course {c} is not in the plan." for c in sorted(required - in_plan)]
    if not required:
        failures.append("No required courses found in the major requirement table.")
    if len(term_hours) != 8:
        failures.append(f"Expected 8 terms, found {len(term_hours)}.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    if SCHOOL.college not in text(soup):
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(path)}.")
    df, term_hours, stated = parse_plan(soup)
    required = required_codes(soup)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (UT states {stated})")
    print(f"Required CS core courses: {', '.join(sorted(required))} (each checked against the plan)")
    failures = check(df, term_hours, stated, required)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 13 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
