"""Parse Kentucky's CS BS curriculum into one row per course or requirement slot.

Kentucky's school-specific plan parser (batch 4). Reads the newest saved program page
(data/raw/uky/*_bs-cs-catalog.html, "Computer Science, B.S.", 2026-2027 Undergraduate
Catalog, saved through Chrome) and writes data/processed/uky/plan_parsed.csv with the
columns in common.PARSED_COLUMNS.

The "Curriculum" section is an Acalog core block whose footnotes (§, Δ, º, ‡, *) and
elective rules ([T], [S], [C], [N], [E]) come first, followed by one <div> holding the
eight semesters. Inside it, <h3> headings name the year ("Freshman Year") and <h4>
headings the term ("First Semester", "Second Semester"); between them, <li> items are:
- courses (li.acalog-course): "CS 215 - Introduction to ... 4 Credit Hours", possibly
  followed by footnote marks;
- "OR" lines (li.acalog-adhoc) joining the course before and after into a choice, and
  blank adhoc lines ending such a group;
- slot lines (no class, or acalog-adhoc-list-item): "Computer Science Elective [C]
  Credit(s): 3".
The page gives no per-semester totals, only "Total Hours: 128", which the parser checks.

Modeling decisions (batch 4, for the user's review):
- "CIS 110 OR WRD 110" (and 111) and "CS 321 OR MA 321 OR MA 322" are one elective_slot
  row each, with the codes in `options`. CIS and WRD 110 are the same course offered by
  two departments (Composition and Communication I).
- Slot letters ([C], [T], [S], [N], [E]) link each slot to the page's rule, which goes in
  its notes; UK Core slots are gen_ed.
- Footnote marks after a course go in its notes with the footnote text.

Usage:
    python src/parse_uky.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from acalog import clean
from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("uky")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Curriculum (eight semesters), 2026-2027 Undergraduate Catalog"

YEARS = {"Freshman Year": 1, "Sophomore Year": 2, "Junior Year": 3, "Senior Year": 4}
TERMS = {"First Semester": "Fall", "Second Semester": "Spring"}
# A course item: "CS 215 - Title 4 Credit Hours" then optional footnote marks.
COURSE = re.compile(r"^([A-Z]{2,4}) (\d{3}[A-Z]?) - (.+?) (\d+) Credit Hours\s*(.*)$")
# A slot item: "Computer Science Elective [C] Credit(s): 3" or "UK Core - Humanities Credit(s): 3".
SLOT = re.compile(r"^(.+?)\s*(?:\[([A-Z])\])?\s*Credit\(s\): (\d+)$")
# Footnote marks used after courses, and their text on the page (Curriculum block).
FOOTNOTES = {"§": "Transfer students take EGR 215 instead of EGR 101 and EGR 103.",
             "Δ": "EGR 101 and EGR 103 together fulfill the UK Core Arts and Creativity requirement.",
             "º": "Based on advisor consult.", "‡": "Only if enrolled in PHY 231.",
             "*": "Graduation Composition and Communication Requirement (GCCR) course."}
# Slot letters -> (row title, requirement_type, rule from the page).
SLOTS = {
    "C": ("Computer Science Elective", "elective_slot",
          "UK [C]: 15 credit hours of 300-level and above CS courses, three of them from CS 316, CS 335, CS 378, "
          "CS 405G, CS 441G, CS 460G, CS 463G, or by department approval."),
    "T": ("Technical Elective", "elective_slot",
          "UK [T]: 12 credit hours of 300-level or higher courses in computer science, electrical engineering, "
          "mathematics (including MA 214, excluding MA 308 and MA 310), Gatton College of Business and Economics, "
          "or by department approval."),
    "S": ("Science Elective", "elective_slot",
          "UK [S]: 3 credit hours from the UK Core natural science or social science lists, or department-approved."),
    "N": ("Natural Science Elective", "elective_slot",
          "UK [N]: 3 credit hours from the UK Core natural science list, or department-approved."),
    "E": ("Free Elective", "elective_slot",
          "UK [E]: 7 credit hours of any college-credit course; at least 3 outside computer science, mathematics, "
          "natural science, and engineering."),
}


# A blank row dict with the defaults every row starts from.
def base_row(credits: int) -> dict:
    """Return a row with fixed credits."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": credits,
            "credits_max": credits, "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": ""}


# Turn one course <li> into a row, with its footnote marks explained in notes.
def course_row(text: str) -> dict:
    """Return the row for a course item."""
    m = COURSE.match(text)
    if not m:
        raise SystemExit(f"Unreadable course item: {text!r}")
    row = base_row(int(m.group(4)))
    row.update(course_code=f"{m.group(1)} {m.group(2)}", subject=m.group(1), number=m.group(2), title=m.group(3))
    marks = [c for c in m.group(5) if c in FOOTNOTES]
    row["notes"] = " ".join(f"UK footnote {c}: {FOOTNOTES[c]}" for c in marks)
    return row


# Turn one slot <li> into a row.
def slot_row(text: str) -> dict:
    """Return the row for a slot item."""
    m = SLOT.match(text)
    if not m:
        raise SystemExit(f"Unreadable slot item: {text!r}")
    label, letter, credits = m.group(1).strip(), m.group(2), int(m.group(3))
    row = base_row(credits)
    if letter:
        title, rtype, note = SLOTS[letter]
        row.update(title=title, requirement_type=rtype, notes=note)
    elif label.startswith("UK Core - "):
        row.update(title=label, requirement_type="gen_ed",
                   notes="UK Core general education requirement (33 hours in all).")
    else:
        raise SystemExit(f"Unknown slot label: {label!r}")
    return row


# Merge a list of course rows joined by "OR" into one choice row.
def choice_row(rows: list[dict]) -> dict:
    """Return one elective_slot row for courses joined by OR."""
    codes = [r["course_code"] for r in rows]
    subjects = {r["subject"] for r in rows}
    row = base_row(rows[0]["credits_min"])
    row.update(title=f"{' or '.join(codes)} ({rows[0]['title']})", subject=subjects.pop() if len(subjects) == 1 else "",
               requirement_type="elective_slot", options="; ".join(codes),
               notes="UK: choose one: " + " | ".join(f"{r['course_code']} ({r['title']})" for r in rows) + ".")
    return row


# Walk the semester <div> in document order: headings set the placement, courses and
# slots become rows, and "OR" lines merge the courses around them.
def parse_plan(div) -> pd.DataFrame:
    """Return the plan rows."""
    rows, year, term = [], None, None
    group, joining = [], False  # the courses of an open OR group; True after an "OR"

    # Close the open OR group (if any) into rows.
    def flush():
        nonlocal group  # flush assigns the enclosing function's variable, not a new local
        if group:
            r = choice_row(group) if len(group) > 1 else group[0]
            r.update(orig_year=year, orig_term=term)
            rows.append(r)
        group = []

    for el in div.find_all(["h3", "h4", "li"]):
        text = clean(el.get_text(" "))
        classes = el.get("class") or []
        if el.name == "h3":
            flush()
            year = YEARS[text]
        elif el.name == "h4":
            flush()
            term = TERMS[text]
        elif "acalog-course" in classes:
            if not joining:
                flush()
            group.append(course_row(text))
            joining = False
        elif text == "OR":
            joining = True
        elif not text:
            flush()
        else:
            flush()
            r = slot_row(text)
            r.update(orig_year=year, orig_term=term)
            rows.append(r)
    flush()
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, stated: int) -> list[str]:
    """Return failed-check messages."""
    failures = []
    got = df["credits_min"].sum()
    if got != stated:
        failures.append(f"Credits {got} != the page's Total Hours {stated}.")
    if SCHOOL.credits != (stated, stated):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the page states {stated}.")
    terms = df.groupby(["orig_year", "orig_term"]).size()
    if len(terms) != 8:
        failures.append(f"Expected 8 semesters, found {len(terms)}.")
    # The slot totals the page states: 15 CS, 12 technical, 7 free elective hours.
    for title, want in [("Computer Science Elective", 15), ("Technical Elective", 12), ("Free Elective", 7)]:
        have = df[df["title"] == title]["credits_min"].sum()
        if have != want:
            failures.append(f"{title}: {have} hours in the plan, page says {want}.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page = clean(soup.get_text(" "))
    if "2026-2027 Undergraduate Catalog" not in page:
        raise SystemExit(f"'2026-2027 Undergraduate Catalog' not found on {rel(path)}.")
    # The program page doesn't name its college; the college's page must, and must list the program.
    college_path = SCHOOL.newest(SCHOOL.college_source)
    college_page = clean(BeautifulSoup(college_path.read_text(encoding="utf-8"), "html.parser").get_text(" "))
    if SCHOOL.college not in college_page or "Computer Science, B.S." not in college_page:
        raise SystemExit(f"{rel(college_path)} does not list Computer Science, B.S. under {SCHOOL.college}.")
    stated = int(re.search(r"Total Hours: (\d+)", page).group(1))
    heading = soup.find(lambda t: t.name in ("h2", "h3") and clean(t.get_text()) == "Curriculum")
    div = heading.find_parent("div", class_="acalog-core").find_next_sibling("div")
    df = parse_plan(div)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (page states {stated})")
    failures = check(df, stated)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All batch 4 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
