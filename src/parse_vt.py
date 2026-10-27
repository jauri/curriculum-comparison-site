"""Parse Virginia Tech's CS BS roadmap into one row per course or requirement slot.

Virginia Tech's school-specific plan parser (step 13, batch 3). Reads the newest saved
2026-2027 Academic Catalog page (data/raw/vt/*_bs-cs-catalog.html, saved through
Chrome) and writes data/processed/vt/plan_parsed.csv with the columns in
common.PARSED_COLUMNS.

The page is a CourseLeaf catalog page with tabs:
- "Program Curriculum" (#programcurriculumtextcontainer): the requirement tables
  (degree core, major, additional, electives, Pathways general education; 123 total)
  followed by the elective lists and numbered footnotes;
- "Roadmap" (#roadmaptextcontainer): ONE "sc_plangrid" table for all eight semesters,
  one semester after another (not side by side as at Penn State). Rows are tagged by
  CSS class: plangridyear ("First Year"), plangridterm ("Fall Semester"), plangridsum
  (the semester's credits), plangridtotal ("Total Credits 123"). A course row has a
  code cell, a title cell, and a credits cell; a slot row has a label cell and a
  credits cell.

Details of VT's text:
- Minimum grades are written in the title, "Introduction to Software Design ( C )" or
  "( C- )": they become min_grade and are removed from the title.
- Footnote numbers are <sup> elements ("Elective 3" = footnote 3, on 5000-level
  courses); they are dropped from labels.
- Generic CS slots are written as a code-like cell plus a title: "CS 3/4/5XXX" +
  "Elective", "CS 4XXX" + "Capstone". These are slots, not courses.

Modeling decisions (step 13, batch 3):
- "MATH 2534 or MATH 3034" and "MATH 2204 or CMDA 2005" are choices: one elective_slot
  row with the option codes in `options`.
- The statistics, CS theory, and professional writing electives list their courses on
  the page, so those courses are the slots' `options` (SLOT_OPTIONS): each slot can
  then match the course concept(s) its options teach. The other elective lists (CS
  technical electives, capstones) are long or mixed and stay in notes.
- "Pathways 2, 3, 6a, or 7" rows are gen_ed slots. Pathways Concept 7 is suspended
  from Fall 2025, as the page says, so those rows are humanities, social science, or
  design and arts courses in practice; noted on the rows.
- ENGE 3900 (Bridge Experience, 0 credits) records the required Career Bridge
  Experience (internship, co-op, or research; footnote 4). It stays a course row with
  0 credits.

Usage:
    python src/parse_vt.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("vt")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Roadmap (Plan of Study Grid), 2026-2027 Academic Catalog"

YEARS = {"First Year": 1, "Second Year": 2, "Third Year": 3, "Fourth Year": 4}
TERMS = {"Fall Semester": "Fall", "Spring Semester": "Spring"}
# One VT course code: subject, space, 4 digits ("CS 1114", "ENGE 1215").
CODE = re.compile(r"^([A-Z]{2,4}) (\d{4})$")
# "MATH 2534 or MATH 3034": two full codes joined by " or ".
CHOICE = re.compile(r"^([A-Z]{2,4} \d{4}) or ([A-Z]{2,4} \d{4})$")
# A minimum grade at the end of a title: "( C )" or "( C- )".
GRADE = re.compile(r"\s*\(\s*([A-D][+-]?)\s*\)$")

PATHWAYS_NOTE = ("VT Pathways to General Education: six hours each in Concept 2 (Critical Thinking in the "
                 "Humanities) and Concept 3 (Reasoning in the Social Sciences), three in Concept 6a (Critique and "
                 "Practice in the Arts), and Concept 7 (Identity and Equity in the United States), which the "
                 "catalog says is suspended effective Fall 2025.")
# Slot labels (code cell + title cell for the generic CS slots) -> (title, type, notes).
SLOTS = {
    "Natural Science Elective": ("Natural Science Elective", "elective_slot",
        "VT Pathways Concept 4: two natural science courses with labs from a two-semester sequence: BIOL "
        "1105/1115 and 1106/1116, CHEM 1035/1045 and 1036/1046, or PHYS 2305 and 2306."),
    "Pathways 2, 3, 6a, or 7": ("Pathways General Education (Concept 2, 3, 6a, or 7)", "gen_ed", PATHWAYS_NOTE),
    "Communications Elective": ("Communications Elective", "elective_slot",
        "VT: COMM 2004 (Public Speaking) or COMM 2014 (Communication Principles of Teamwork)."),
    "Advanced Natural Science Elective": ("Advanced Natural Science Elective", "elective_slot",
        "VT: one more natural science course (4 credits), beyond the two-course sequence."),
    "CS 3/4/5XXX Elective": ("CS 3000-5000 Level Elective", "elective_slot",
        "VT: 6 credits of CS courses at the 3000 level or above (5000-level courses need a 3.0 GPA and approval, "
        "footnote 3)."),
    "CS 4/5XXX Elective": ("CS 4000-5000 Level Elective", "elective_slot",
        "VT: 3 credits of CS courses at the 4000 level or above (5000-level courses need a 3.0 GPA and approval, "
        "footnote 3)."),
    "Professional Writing Elective": ("Professional Writing Elective", "elective_slot",
        "VT: one of ENGL 3764 (Technical Writing), 3804, 3814, 3824, 3834, 3844, or 4824."),
    "Statistics Elective": ("Statistics Elective", "elective_slot",
        "VT: one of STAT 4705 (Probability and Statistics for Engineers), STAT 4105, STAT 4714, STAT 4604, "
        "STAT 3704, or CMDA 2006."),
    "CS Theory Elective": ("CS Theory Elective", "elective_slot",
        "VT: one of CS 4104 (Data and Algorithm Analysis), CS 4114 (Formal Languages and Automata Theory), "
        "CS 4124 (Theory of Computation), CS 4134 (Quantum Computation), CS 5104, or CS 5114."),
    "CS Technical Elective": ("CS Technical Elective", "elective_slot",
        "VT: one course from a list of technical courses in and outside CS (e.g. ECE, MATH, STAT, CMDA, BIT, "
        "GEOG, MUS), such as machine learning, numerical methods, cryptography, robotics, or data analytics."),
    "CS 4XXX Capstone": ("CS Capstone", "elective_slot",
        "VT: one capstone course, e.g. CS 4094 (Computer Science Capstone), CS 4274 (Secure Computing), "
        "CS 4284 (Systems & Networking), CS 4664 (Data-Centric Computing), CS 4704 (Software Engineering), "
        "CS 4784 (Human-Computer Interaction), or ENGE 4735/4736 (Interdisciplinary Design)."),
    "Free Elective": ("Free Elective", "elective_slot",
        "VT: 7 credits of free electives; the BS also requires 30 credits of non-technical courses "
        "(footnote 1)."),
}
# Options of the slots whose lists are short and of one kind (from the page's lists).
SLOT_OPTIONS = {
    "Statistics Elective": ["STAT 4705", "STAT 4105", "STAT 4714", "STAT 4604", "STAT 3704", "CMDA 2006"],
    "CS Theory Elective": ["CS 4104", "CS 4114", "CS 4124", "CS 4134", "CS 5104", "CS 5114"],
    "Professional Writing Elective": ["ENGL 3764", "ENGL 3804", "ENGL 3814", "ENGL 3824", "ENGL 3834", "ENGL 3844",
                                      "ENGL 4824"],
}
NOTES = {
    "ENGE 3900": "Records the required Career Bridge Experience (internship, co-op, or undergraduate research; "
                 "VT footnote 4); 0 credits.",
    "ENGE 1215": "The requirements also allow ENGE 1414 (Foundations of Engineering Practice) for ENGE 1215 & 1216.",
    "ENGE 1216": "The requirements also allow ENGE 1414 (Foundations of Engineering Practice) for ENGE 1215 & 1216.",
    "MATH 3134": "The requirements also allow MATH 3124 (Modern Algebra).",
}


# Text of an element with non-breaking spaces made normal and whitespace collapsed.
def text(el) -> str:
    """Return an element's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", el.get_text(" ").replace("\xa0", " ")).strip()


# Turn one roadmap row's cells (code or label, optional title, credits) into a row.
def parse_row(cells: list[str]) -> dict:
    """Return the plan row for a roadmap course or slot row."""
    hours = float(cells[-1])
    row = {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": hours, "credits_max": hours,
           "requirement_type": "required", "gened_tag": "", "min_grade": "", "counts_toward_total": True,
           "notes": "", "options": ""}
    label, title = cells[0], (cells[1] if len(cells) == 3 else "")
    grade = GRADE.search(title)
    if grade:
        row["min_grade"] = grade.group(1)
        title = title[: grade.start()]
    m, pair = CODE.match(label), CHOICE.match(label)
    if m:
        row.update(course_code=label, subject=m.group(1), number=m.group(2), title=title, notes=NOTES.get(label, ""))
    elif pair:
        codes = list(pair.groups())
        subjects = {c.split()[0] for c in codes}
        titles = title.split(" or ")
        row.update(subject=subjects.pop() if len(subjects) == 1 else "", title=f"{' or '.join(codes)} ({titles[0]})",
                   requirement_type="elective_slot", options="; ".join(codes),
                   notes=f"Student chooses one: {' | '.join(titles)}.")
    else:
        key = f"{label} {title}".strip()  # "CS 4XXX" + "Capstone" -> "CS 4XXX Capstone"
        if key not in SLOTS:
            raise SystemExit(f"Unknown slot label in the roadmap: {key!r}. Add it to SLOTS.")
        slot_title, rtype, notes = SLOTS[key]
        row.update(title=slot_title, requirement_type=rtype, notes=notes,
                   options="; ".join(SLOT_OPTIONS.get(slot_title, [])))
    return row


# Walk the roadmap grid. The <sup> footnote marks are removed first so labels read
# "Elective", not "Elective 3".
def parse_plan(grid) -> tuple[pd.DataFrame, dict, int]:
    """Return (rows, {(year, term): stated credits}, stated total)."""
    for sup in grid.find_all("sup"):
        sup.decompose()
    rows, term_hours, year, term, total = [], {}, None, None, None
    for tr in grid.find_all("tr"):
        classes = tr.get("class") or []
        cells = [text(td) for td in tr.find_all(["td", "th"])]
        if "plangridyear" in classes:
            year = YEARS[cells[0]]
        elif "plangridterm" in classes:
            term = TERMS[cells[0]]
        elif "plangridsum" in classes:
            term_hours[(year, term)] = float(cells[-1])
        elif "plangridtotal" in classes:
            total = int(cells[-1])
        else:
            r = parse_row([c for c in cells if c != ""])  # drop the empty spacer cells
            r.update(orig_year=year, orig_term=term)
            rows.append(r)
    df = pd.DataFrame(rows)
    for col in ["credits_min", "credits_max"]:
        df[col] = df[col].astype(int)  # VT's roadmap has whole credits only
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, term_hours, total


# Codes of the named courses in the requirement tables (first table group, up to the
# "Total Credits" row; the elective lists after it are options, not requirements).
# "or ..." rows are alternatives and are skipped.
def required_codes(container) -> set[str]:
    """Return the first course code of each required row in the program curriculum."""
    codes = set()
    for table in container.find_all("table", class_="sc_courselist"):
        for tr in table.find_all("tr"):
            cells = [text(td) for td in tr.find_all("td")]
            if cells and cells[0] == "Total Credits":
                return codes
            if cells and CODE.match(cells[0].split(" & ")[0]):
                for code in cells[0].split(" & "):  # "ENGE 1215 & ENGE 1216": both required
                    codes.add(code)
    return codes


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, term_hours: dict, total: int, required: set[str]) -> list[str]:
    """Return failed-check messages."""
    failures = []
    got = df["credits_min"].sum()
    if got != total:
        failures.append(f"Credits {got} != the roadmap's Total Credits {total}.")
    if SCHOOL.credits != (total, total):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the roadmap states {total}.")
    for (y, t), stated in term_hours.items():
        g = df[(df["orig_year"] == y) & (df["orig_term"] == t)]["credits_min"].sum()
        if g != stated:
            failures.append(f"Year {y} {t}: {g} credits, roadmap says {stated:g}.")
    if len(term_hours) != 8:
        failures.append(f"Expected 8 semesters, found {len(term_hours)}.")
    in_plan = set(df["course_code"]) | {o for opts in df["options"] if opts for o in opts.split("; ")}
    for code in sorted(required - in_plan):
        failures.append(f"Required course {code} is not in the roadmap.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page = text(soup)
    if SCHOOL.college not in page or "2026-2027 Academic Catalog" not in page:
        raise SystemExit(f"College '{SCHOOL.college}' or the 2026-2027 catalog not found on {rel(path)}.")
    grid = soup.select_one("#roadmaptextcontainer table.sc_plangrid")
    df, term_hours, total = parse_plan(grid)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (VT states {total})")
    failures = check(df, term_hours, total, required_codes(soup.select_one("#programcurriculumtextcontainer")))
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 13 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
