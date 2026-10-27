"""Parse Texas A&M's CS BS plan of study into one row per course or requirement slot.

Texas A&M's school-specific plan parser (step 13). Reads the newest saved 2026-2027
catalog page (data/raw/tamu/*_bs-cs-catalog.html) and writes
data/processed/tamu/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

The page is a CourseLeaf catalog page with TWO "sc_plangrid" tables: the first year
common to all College of Engineering majors (31-32 hours), then the CS second through
fourth years (95 hours). Each grid is followed by a <dl> of numbered footnotes, and the
page ends with "Total Program Hours 126". Rows are tagged by CSS class like UIC's
(plangridyear, plangridterm, plangridsum, plangridtotal), with two TAMU habits:

- "Select one of the following:" carries the hours, and the options follow as rows
  with an empty hours cell. A slot label can have options the same way ("High Impact
  Experience", 0 hours, with CSCE 399 under it).
- Cross-listed courses are written "ENGR 216/PHYS 216"; the first code is used and the
  other is kept in notes.

Modeling decisions (step 13):
- Footnote 1 says "A grade of C or better is required", so rows marked 1 get
  min_grade = C.
- The first-year spring "Select one of the following: CHEM 120 | University Core
  Curriculum" (3-4 hours) is a University Core Curriculum slot of 3 hours. Footnote 4
  says CHEM 120 is for the BMEN, CHEN, and MSEN majors; a CS student takes a core
  course, which makes the plan total the stated 126 (footnote 3 also counts 21 core
  hours, which includes this one).
- Other "Select one" choices are one elective_slot row with the option codes in
  `options`, the same rule as UIC and OSU.

Usage:
    python src/parse_tamu.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("tamu")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Plan of Study, 2026-2027 Undergraduate Catalog (first year common to Engineering, then CS years 2-4)"

YEARS = {"First Year": 1, "Second Year": 2, "Third Year": 3, "Fourth Year": 4}
TERMS = {"Fall": "Fall", "Spring": "Spring"}
# One TAMU course code: 3-4 capital letters, a space, 3 digits (e.g. "CSCE 221").
CODE = re.compile(r"\b([A-Z]{3,4}) (\d{3})\b")
SELECT = "Select one of the following:"
# Slot labels as TAMU writes them (footnote numbers removed) -> (title, requirement_type).
SLOTS = {
    "University Core Curriculum": ("University Core Curriculum", "gen_ed"),
    "Science elective": ("Science elective", "elective_slot"),
    "Complementary elective": ("Complementary elective", "elective_slot"),
    "Computer science elective": ("Computer science elective", "elective_slot"),
    "High Impact Experience": ("High-Impact Experience", "elective_slot"),
}
# Notes that explain each slot, condensed from the grid footnotes on the same page.
SLOT_NOTES = {
    "University Core Curriculum": "TAMU footnote 3: 21 core hours in the plan, including 3 creative arts, 3 social "
        "and behavioral sciences, 3 language, philosophy and culture, 6 American history, and 6 government/"
        "political science; international/cultural diversity and cultural discourse may overlap.",
    "Science elective": "TAMU footnote 6: see an advisor for the list of acceptable science courses (7 hours in the plan).",
    "Complementary elective": "TAMU footnote 7: chosen with a departmental advisor to fit the student's plans after "
        "graduation, and approved on a filed degree plan (9 hours).",
    "Computer science elective": "TAMU footnote 8: 18 hours: 3 systems, 3 software and languages, 3 information and "
        "applications, and 9 upper-level computer science and engineering electives.",
    "High-Impact Experience": "TAMU footnote 9: every student must complete a high-impact experience to graduate "
        "(0 hours in the plan); CSCE 399 records it. The list of options is kept by the CSE advising office.",
}
FIRST_YEAR_CORE_NOTE = ("The grid offers 'Select one of the following: CHEM 120 or University Core Curriculum' "
                        "(3-4 hours). TAMU footnote 4 says CHEM 120 is for the BMEN, CHEN, and MSEN majors, so "
                        "a CS student takes a 3-hour core course here.")


# Text of a cell with non-breaking spaces made normal.
def text(cell) -> str:
    """Return a cell's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", cell.get_text(" ").replace("\xa0", " ")).strip()


# Read and remove a row's footnote markers. TAMU puts them in <sup> tags, e.g.
# <sup>1,4</sup>, so the numbers are collected and then the tags deleted, which keeps
# them out of titles and labels.
def pop_footnotes(tr) -> set[str]:
    """Return the footnote numbers of a row and remove their <sup> tags."""
    marks = set()
    for sup in tr.find_all("sup"):
        marks |= {m.strip() for m in text(sup).split(",") if m.strip()}
        sup.decompose()  # decompose() deletes the tag and its text from the tree
    return marks


# Read one grid row into (label, title, hours, footnotes). hours is None for the
# option rows under a "Select one" row, whose hours cell is empty.
def read_row(tr) -> tuple[str, str, str | None, set[str]]:
    """Return a course row's code-cell text, title, hours text (or None), and footnotes."""
    marks = pop_footnotes(tr)
    label = text(tr.find("td", class_="codecol"))
    title_cell = tr.find("td", class_="titlecol")
    hours = text(tr.find("td", class_="hourscol"))
    return label, text(title_cell) if title_cell else "", hours or None, marks


# A blank row dict with the defaults every row starts from.
def base_row(hours: str) -> dict:
    """Return a row with credits from an hours string like "3" or "3-4"."""
    lo, _, hi = hours.partition("-")  # "3-4" -> ("3", "-", "4"); "3" -> ("3", "", "")
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": int(lo),
            "credits_max": int(hi or lo), "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": ""}


# Build the row for a named course. "ENGR 216/PHYS 216" is one cross-listed course:
# the first code is the row's code and the second goes in notes. "ENGL 103 or ENGL 104"
# in one cell is a choice: one elective_slot row with both codes in `options`.
def course_row(label: str, title: str, hours: str, marks: set[str]) -> dict:
    """Return the row for a named (possibly cross-listed) course, or an inline choice."""
    codes = [f"{s} {n}" for s, n in CODE.findall(label)]
    row = base_row(hours)
    grade = "C" if "1" in marks else ""
    if " or " in label:
        subjects = {c.split()[0] for c in codes}
        row.update(subject=subjects.pop() if len(subjects) == 1 else "", min_grade=grade,
                   title=f"{label} ({title.split(' or ')[0]})", requirement_type="elective_slot",
                   options="; ".join(codes), notes=f"Student chooses one: {title.replace(' or ', ' | ')}.")
        return row
    subj, num = codes[0].split()
    row.update(course_code=codes[0], subject=subj, number=num, title=title, min_grade=grade)
    if len(codes) > 1:
        row["notes"] = f"Cross-listed as {', '.join(codes[1:])}."
    return row


# Build the slot row for a "Select one" block or a labeled slot, given its options
# (list of (label, title) pairs from the rows under it).
def choice_row(label: str, hours: str, marks: set[str], options: list[tuple[str, str]], year: int) -> dict:
    """Return the slot row for a choice block or a labeled slot with options."""
    row = base_row(hours)
    codes = [f"{s} {n}" for lab, _ in options for s, n in CODE.findall(lab)]
    if label == SELECT and year == 1 and any(lab.startswith("University Core Curriculum") for lab, _ in options):
        # The first-year CHEM 120 / core choice: a 3-hour core slot for CS (see docstring).
        row.update(title="University Core Curriculum", requirement_type="gen_ed",
                   credits_min=3, credits_max=3, notes=FIRST_YEAR_CORE_NOTE)
    elif label == SELECT:
        titles = [t for _, t in options]
        row.update(title=f"{' or '.join(codes)} ({titles[0]})", requirement_type="elective_slot",
                   options="; ".join(codes), min_grade="C" if "1" in marks else "",
                   notes=f"Student chooses one: {' | '.join(titles)}.")
        subjects = {c.split()[0] for c in codes}
        row["subject"] = subjects.pop() if len(subjects) == 1 else ""
    else:
        if label not in SLOTS:
            raise SystemExit(f"Unknown slot label in the plan grid: {label!r}. Add it to SLOTS.")
        title, rtype = SLOTS[label]
        row.update(title=title, requirement_type=rtype, options="; ".join(codes),
                   min_grade="C" if "1" in marks else "", notes=SLOT_NOTES[title])
    return row


# Walk both grids. A row with hours either is a course (code cell has a code) or opens
# a slot; following rows without hours are that slot's options. The slot row is built
# once its options are known: when the next row with hours (or a heading) arrives.
def parse_plan(soup) -> tuple[pd.DataFrame, dict, list[str]]:
    """Return (rows, {(year, term): stated hours text}, [stated total per grid])."""
    rows, term_hours, totals = [], {}, []
    year = term = None
    pending = None  # (label, hours, footnotes, options, year, term) of an open slot

    # Close the open slot (if any) and add its row.
    def flush():
        nonlocal pending  # flush assigns the enclosing function's variable, not a new local
        if pending:
            label, hours, marks, options, y, t = pending
            r = choice_row(label, hours, marks, options, y)
            r.update(orig_year=y, orig_term=t)
            rows.append(r)
            pending = None

    for grid in soup.find_all("table", class_="sc_plangrid"):
        for tr in grid.find_all("tr"):
            classes = tr.get("class") or []  # rows without a class attribute give None
            if "plangridyear" in classes:
                flush()
                year = YEARS[text(tr)]
            elif "plangridterm" in classes:
                flush()
                term = TERMS[text(tr.find("th"))]  # the first term row also holds the hours header
            elif "plangridsum" in classes:
                flush()
                term_hours[(year, term)] = text(tr.find("td", class_="hourscol"))
            elif "plangridtotal" in classes:
                flush()
                totals.append(text(tr.find("td", class_="hourscol")))
            elif tr.find("td", class_="codecol"):
                label, title, hours, marks = read_row(tr)
                if hours is None:
                    if pending is None:
                        raise SystemExit(f"Option row {label!r} with no open slot above it.")
                    pending[3].append((label, title))
                    continue
                flush()
                if CODE.search(label):
                    r = course_row(label, title, hours, marks)
                    r.update(orig_year=year, orig_term=term)
                    rows.append(r)
                else:
                    pending = (label, hours, marks, [], year, term)
    flush()
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, term_hours, totals


# Does a credit sum fall inside a stated range like "15-16" (or equal "17")?
def in_range(value: int, stated: str) -> bool:
    """Return True if value is within the stated hours text."""
    lo, _, hi = stated.partition("-")
    return int(lo) <= value <= int(hi or lo)


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, term_hours: dict, totals: list[str], stated: int) -> list[str]:
    """Return failed-check messages."""
    failures = []
    total = df["credits_min"].sum()
    if df["credits_min"].sum() != df["credits_max"].sum():
        failures.append("Some rows still have a credit range; the plan should be fixed at the stated total.")
    if total != stated:
        failures.append(f"Credits {total} != the page's Total Program Hours {stated}.")
    if SCHOOL.credits != (stated, stated):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the page states {stated}.")
    for (y, t), hours in term_hours.items():
        got = df[(df["orig_year"] == y) & (df["orig_term"] == t)]["credits_min"].sum()
        if not in_range(got, hours):
            failures.append(f"Year {y} {t}: {got} hours, page says {hours}.")
    # Each grid's own total: the first year (31-32) and years 2-4 (95).
    grid_sums = [df[df["orig_year"] == 1]["credits_min"].sum(), df[df["orig_year"] > 1]["credits_min"].sum()]
    for got, said in zip(grid_sums, totals):
        if not in_range(got, said):
            failures.append(f"A grid sums to {got} hours, page says {said}.")
    gen_ed = df[df["requirement_type"] == "gen_ed"]["credits_min"].sum()
    if gen_ed != 21:
        failures.append(f"University Core Curriculum hours {gen_ed} != 21 (footnote 3).")
    if len(term_hours) != 8:
        failures.append(f"Expected 8 terms, found {len(term_hours)}.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page = text(soup)
    if SCHOOL.college not in page:
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(path)}.")
    m = re.search(r"Total Program Hours (\d+)", page)
    if not m:
        raise SystemExit(f"'Total Program Hours' not found on {rel(path)}.")
    stated = int(m.group(1))
    df, term_hours, totals = parse_plan(soup)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (TAMU states {stated}; grids state {', '.join(totals)})")
    failures = check(df, term_hours, totals, stated)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 13 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
