"""Parse Carnegie Mellon's CS BS Sample Course Sequence into one row per course or slot.

CMU's school-specific plan parser (step 13, batch 3). Reads the newest saved 2026-2027
catalog page (data/raw/cmu/*_bs-cs-catalog.html) and writes
data/processed/cmu/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

The page is a CourseLeaf catalog page. After the requirement tables ("sc_courselist")
and the "Summary of Degree Requirements" (360 units), the "Sample Course Sequence"
heading is followed by EIGHT more sc_courselist tables, one per semester in order
(Freshman Fall, Freshman Spring, ..., Senior Spring); each table's "listsum" row states
the semester's units. A row has a code cell ("15-122", or a placeholder such as
"xx-xxx" or "15-xxx" for a slot), a title cell, and a units cell.

CMU counts UNITS, not credit hours: a course's units are its expected hours of work per
week (a typical course is 9 or 12 units), and the degree needs 360. Units are divided by
3 to get credit-hour equivalents (decided with the user in step 13, batch 3: 360 units
-> 120 credits), rounded to 2 decimals, and the units are kept in each row's notes so
every value traces back to the page.

Modeling decisions (step 13, batch 3):
- The sample is "for a student who already has credit for introductory programming and
  one semester of calculus"; students without that credit "will take 15-112 and/or
  21-120 in their first semester". Both are added to the first semester as
  placement-dependent rows with counts_toward_total = false (the OSU CSE 1223
  precedent from step 10), so the plan shows them without changing the sample's total.
  Their units come from their own course pages.
- 07-131 is in the sample as "(optional, not required for CS major)": it stays as a
  course row with counts_toward_total = false.
- Placeholder rows are slots. The constrained electives (Logic/Languages, Systems,
  Artificial Intelligence), the probability course, and the technical communication
  course list their options on the page, and the options are given in `options`
  (SLOT_OPTIONS), so the slot can match the course concept(s) its options teach. The
  Domains elective's options span unrelated areas, so it has none (it is a CS elective).
- The counted sample (363 units: 365 minus the optional 07-131) is 3 units over the
  360-unit minimum, so the counted total is 363 / 3 = 121 credits.

Usage:
    python src/parse_cmu.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("cmu")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Sample Course Sequence, 2026-2027 Undergraduate Catalog"
UNITS_PER_CREDIT = 3  # 9 CMU units ~ a 3-credit course; 360 units -> 120 credits

# The eight semester tables, in page order.
TERMS = [(1, "Fall"), (1, "Spring"), (2, "Fall"), (2, "Spring"),
         (3, "Fall"), (3, "Spring"), (4, "Fall"), (4, "Spring")]
# A CMU course number: two-digit department, hyphen, three digits ("15-122").
CODE = re.compile(r"^(\d{2})-(\d{3})$")
# A title's trailing parenthetical: "(if not offered, substitute 21-127 )".
PAREN = re.compile(r"\s*\(([^()]*)\)\s*$")

CONSTRAINED = " Constrained electives may be taken in any order and in any semester (the page's * note)."
# Slot titles as the sample writes them (trailing "*" removed) -> (title, type, notes).
SLOTS = {
    "SCS Major Intro Mini": ("SCS Major Intro Mini", "elective_slot",
        "CMU: a 5-unit first-year mini-course introducing an SCS major (02-180, 05-180, 07-180, or 16-180); two "
        "of them may together count as one SCS elective."),
    "Humanities and Arts Elective": ("Humanities and Arts Elective", "gen_ed",
        "CMU: 63 units from the College of Humanities & Social Sciences and/or the College of Fine Arts (some "
        "Tepper courses qualify), per the SCS General Education Requirements."),
    "Science/Engineering Course": ("Science/Engineering Course", "elective_slot",
        "CMU: 36 units offered by the Mellon College of Science and/or the College of Engineering, per the SCS "
        "General Education Requirements."),
    "Minor Requirement / Free Elective": ("Minor Requirement / Free Elective", "elective_slot",
        "CMU: the degree requires a minor outside SCS or a concentration within SCS (63 units with free "
        "electives); a free elective is any CMU course."),
    "Computer Science: Domains Elective": ("CS Domains Elective", "elective_slot",
        "CMU: one of 02-251, 05-391, 11-324, 15-322, 15-330 (Computer Security), 15-362 (Computer Graphics), "
        "15-455 (Complexity Theory), or 17-313 (Foundations of Software Engineering)." + CONSTRAINED),
    "Probability Course": ("Probability Course", "elective_slot",
        "CMU: one of 15-259 (Probability and Computing), 21-325, 21-425, 36-218, or 36-225 and 36-226."
        + CONSTRAINED),
    "Computer Science: Logic/Languages Elective": ("CS Logic/Languages Elective", "elective_slot",
        "CMU: one of 15-311, 15-312 (Foundations of Programming Languages), 15-316, 15-317 (Constructive "
        "Logic), 15-414, 17-355, 17-363, or 80-413." + CONSTRAINED),
    "Technical Communications Course": ("Technical Communications Course", "elective_slot",
        "CMU: one of 07-300 (Research and Innovation in Computer Science), 17-200 (Ethics and Policy Issues in "
        "Computing), or 76-270 (Writing for the Professions)."),
    "Computer Science: Systems Elective": ("CS Software Systems Elective", "elective_slot",
        "CMU: one of 15-410 (Operating System Design and Implementation), 15-411 (Compiler Design), 15-418 "
        "(Parallel Computer Architecture and Programming), 15-440 (Distributed Systems), 15-441 (Networking), "
        "or 15-445 (Database Systems); min. 12 units." + CONSTRAINED),
    "Computer Science: Artificial Intelligence Elective": ("CS Artificial Intelligence Elective", "elective_slot",
        "CMU: one of 07-280, 10-301 (Introduction to Machine Learning), 11-411, 11-485, 15-382, 15-386, 16-280, "
        "16-384, or 16-385." + CONSTRAINED),
    "School of Computer Science Elective": ("SCS Elective", "elective_slot",
        "CMU: two SCS courses (15-, 02-, 05-, 07-, 10-, 11-, 16-, or 17-) at the 200 level or above, at least 9 "
        "units each, with listed exceptions."),
}
# Options of the slots whose page lists them (requirement tables, "Units" lists). A pair
# that must be taken together ("36-225 & 36-226") is listed by its first course.
SLOT_OPTIONS = {
    "Probability Course": ["15-259", "21-325", "21-425", "36-218", "36-225"],
    "CS Logic/Languages Elective": ["15-311", "15-312", "15-316", "15-317", "15-414", "17-355", "17-363", "80-413"],
    "Technical Communications Course": ["07-300", "17-200", "76-270"],
    "CS Software Systems Elective": ["15-410", "15-411", "15-418", "15-440", "15-441", "15-445"],
    "CS Artificial Intelligence Elective": ["07-280", "10-301", "11-411", "11-485", "15-382", "15-386", "16-280",
                                            "16-384", "16-385"],
}
# Rows added from the sample's own note (see the module docstring): code -> note.
PLACEMENT_ROWS = {
    "15-112": "Taken in the first semester by students without credit for introductory programming (the "
              "sample's note); the sample assumes that credit, so these units are not in its total. "
              "15-112 is the prerequisite for 15-122.",
    "21-120": "Taken in the first semester by students without credit for one semester of calculus (the "
              "sample's note); the sample assumes that credit, so these units are not in its total. "
              "21-120 is a required Mathematics course.",
}


# Text of an element with non-breaking spaces made normal and whitespace collapsed.
def text(el) -> str:
    """Return an element's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", el.get_text(" ").replace("\xa0", " ")).strip()


# CMU units -> credit-hour equivalent, rounded to 2 decimals; whole numbers stay ints
# so most rows read "4", not "4.0".
def credits(units: int):
    """Return units / 3, as an int when whole."""
    c = round(units / UNITS_PER_CREDIT, 2)
    return int(c) if c == int(c) else c


# Units and title of a course from its block on a saved department course page:
# <dt>15-112 Fundamentals of ...</dt><dd>All Semesters: 12 units<br/>...</dd>.
def course_page_units(code: str) -> tuple[int, str]:
    """Return (units, title) for a course code, read from data/raw/cmu/*_courses-*.html."""
    for path in sorted(SCHOOL.raw.glob("*_courses-*.html")):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        for dt in soup.select("dl.courseblock dt"):
            if text(dt).startswith(code + " "):
                m = re.search(r"(\d+) units", text(dt.find_next_sibling("dd")))
                return int(m.group(1)), text(dt)[len(code) + 1:]
    raise SystemExit(f"{code} not found on the saved course pages.")


# A blank row dict for a given number of units.
def base_row(units: int) -> dict:
    """Return a required-course row with credits from units."""
    c = credits(units)
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": c, "credits_max": c,
            "requirement_type": "required", "gened_tag": "", "min_grade": "", "counts_toward_total": True,
            "notes": f"{units} CMU units.", "options": "", "units": units}


# Turn one sample row (code cell, title cell, units) into a plan row.
def parse_row(code: str, title: str, units: int) -> dict:
    """Return the plan row for one sample-sequence row."""
    row = base_row(units)
    m = CODE.match(code)
    if m:
        paren = PAREN.search(title)
        if paren:
            title = title[: paren.start()]
            row["notes"] += f" The sample adds: '{paren.group(1).strip()}'."
            if paren.group(1).startswith("optional"):
                row["counts_toward_total"] = False
        row.update(course_code=code, subject=m.group(1), number=m.group(2), title=title)
        return row
    key = title.rstrip("*").strip()
    if key not in SLOTS:
        raise SystemExit(f"Unknown slot in the sample sequence: {code} {title!r}. Add it to SLOTS.")
    slot_title, rtype, notes = SLOTS[key]
    row.update(title=slot_title, requirement_type=rtype, notes=f"{row['notes']} {notes}",
               options="; ".join(SLOT_OPTIONS.get(slot_title, [])))
    return row


# Read the eight semester tables that follow the "Sample Course Sequence" heading.
def parse_plan(soup) -> tuple[pd.DataFrame, list[int]]:
    """Return (rows, stated units per semester)."""
    heading = next(h for h in soup.find_all(["h2", "h3"]) if text(h) == "Sample Course Sequence")
    tables = heading.find_all_next("table", class_="sc_courselist")[: len(TERMS)]
    rows, stated = [], []
    for (year, term), table in zip(TERMS, tables):
        for tr in table.find_all("tr"):
            cells = [text(td) for td in tr.find_all("td")]
            if "listsum" in (tr.get("class") or []):
                stated.append(int(cells[-1]))
                continue
            r = parse_row(cells[0], cells[1], int(cells[2]))
            r.update(orig_year=year, orig_term=term)
            rows.append(r)
    for code, note in PLACEMENT_ROWS.items():
        units, title = course_page_units(code)
        r = base_row(units)
        dept, num = code.split("-")
        r.update(course_code=code, subject=dept, number=num, title=title, counts_toward_total=False,
                 notes=f"{units} CMU units. {note}", orig_year=1, orig_term="Fall")
        rows.insert(0, r)  # list order is page order; these come before the first semester's rows
    df = pd.DataFrame(rows)
    for col in ["credits_min", "credits_max"]:
        # A plain list in an object Series keeps whole numbers as ints in the CSV.
        # (DataFrame() made the column float, so whole numbers are turned back into ints.)
        df[col] = pd.Series([int(x) if x == int(x) else x for x in df[col]], index=df.index, dtype=object)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, stated


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, stated: list[int], minimum: int, page: str) -> list[str]:
    """Return failed-check messages."""
    failures = []
    if len(stated) != 8:
        failures.append(f"Expected 8 semester tables, found {len(stated)}.")
    in_sample = df[~df["course_code"].isin(PLACEMENT_ROWS)]  # the sample's own rows
    for (year, term), units in zip(TERMS, stated):
        got = in_sample[(in_sample["orig_year"] == year) & (in_sample["orig_term"] == term)]["units"].sum()
        if got != units:
            failures.append(f"Year {year} {term}: {got} units, the page says {units}.")
    counted = df[df["counts_toward_total"]]["units"].sum()
    if counted < minimum:
        failures.append(f"Counted units {counted} are below the {minimum}-unit minimum.")
    expected = round(counted / UNITS_PER_CREDIT)
    if SCHOOL.credits != (expected, expected):
        failures.append(f"schools.csv says {SCHOOL.credits} credits; the counted sample is {counted} units "
                        f"= {expected} credits.")
    if abs(df[df["counts_toward_total"]]["credits_min"].sum() - expected) > 0.05:
        failures.append("Rounded credits do not add up to the counted units / 3.")
    if "requirements are for students entering Fall 2026" not in page:
        failures.append("The page no longer says its requirements are for students entering Fall 2026.")
    # The named core courses must all be in the plan.
    for code in ["07-128", "15-122", "15-150", "15-210", "15-213", "15-251", "15-451", "15-151", "21-120",
                 "21-122", "21-241", "21-259", "99-101"]:
        if code not in set(df["course_code"]):
            failures.append(f"Required course {code} is not in the plan.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page = text(soup)
    if SCHOOL.college not in page:
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(path)}.")
    m = re.search(r"Minimum number of units required for the degree: (\d+)", page)
    if not m:
        raise SystemExit(f"The degree's minimum units are not stated on {rel(path)}.")
    df, stated = parse_plan(soup)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    failures = check(df, stated, int(m.group(1)), page)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    counted = df[df["counts_toward_total"]]["units"].sum()
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Units: {counted} counted (minimum {m.group(1)}) = {counted / UNITS_PER_CREDIT:g} credits")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 13 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
