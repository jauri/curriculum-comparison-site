"""Parse Wisconsin's Computer Sciences BS four-year plan into one row per course or slot.

Wisconsin's school-specific plan parser (step 13, batch 2). Reads the newest saved
2026-2027 Guide page (data/raw/wisc/*_bs-cs-guide.html) and writes
data/processed/wisc/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

The page is a CourseLeaf Guide page with:
- "sc_courselist" tables: the major requirements, under headings such as "Linear
  Algebra" or "Theory of Computer Science" with "Complete one:" option lists. Used for
  course titles, for the options of the plan's choice slots, and for a cross-check that
  every named required course is in the plan.
- one "sc_plangrid" table, the Four-Year Plan. Unlike UIUC's or TAMU's grids, each row
  holds TWO terms side by side (Fall code, credits, Spring code, credits), and the code
  cells hold only a code or a slot label, with no titles. Rows are tagged plangridyear,
  plangridterm, plangridsum (each term's credits), and plangridtotal ("Total Credits 120").

Titles: a course's title comes from the requirement tables when the course is listed
there, otherwise from its saved Guide subject page (data/raw/wisc/*_courses-*.html),
whose titles are in capitals ("PROGRAMMING I") and are converted to title case.

Modeling decisions (step 13):
- Cross-listed codes ("COMP SCI/E C E 354") use the first subject (COMP SCI 354); the
  other listing goes in notes.
- "Linear Algebra", "Probability or Statistics", and "COMP SCI Theory (COMP SCI 577
  recommended)" are choice slots: their options come from the requirement table with the
  same heading ("Complete one:"), so they get `options` and choice_kind "choose".
- "COMP SCI Software/Hardware", "COMP SCI Applications", and "COMP SCI Elective" choose
  from lists of 12 or more courses, so they are slots without options (the "too many to
  list" rule in specs/03-processing.md).
- Three slots are "3-4" credits. The plan's term sums and its 120 total use the low end,
  so the rows keep the range (credits_min 3, credits_max 4) and the parse checks compare
  the term sums against credits_min. schools.csv records 120-123.
- INTER-LS 210 and COMP SCI 368 are marked optional in the plan; they stay course rows
  (their credits are inside the 120) with the plan's label in notes.

Usage:
    python src/parse_wisc.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("wisc")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Four-Year Plan, 2026-2027 Guide"

YEARS = {"First Year": 1, "Second Year": 2, "Third Year": 3, "Fourth Year": 4}
TERMS = ["Fall", "Spring"]  # left and right halves of each grid row
# One Wisconsin code, possibly cross-listed: "COMP SCI 300", "COMP SCI/E C E 354",
# "STAT/MATH 309", "INTER-LS 210". Subjects are capital letters with single spaces or
# hyphens inside ("E C E", "INTER-LS"); several are joined by "/". The number follows.
CODE = re.compile(r"\b([A-Z][A-Z-]*(?: [A-Z][A-Z-]*)*(?:/[A-Z][A-Z-]*(?: [A-Z][A-Z-]*)*)*) (\d{3})\b")
# Slot labels as the plan writes them -> (title, requirement_type, heading of the
# requirement table that lists the options, or None for slots without options).
SLOTS = {
    "Communications Part A": ("Communication Part A", "gen_ed", None),
    "Communication Part B": ("Communication Part B", "gen_ed", None),
    "Ethnic Studies": ("Ethnic Studies", "gen_ed", None),
    "First-Semester Language": ("World Language (first semester)", "gen_ed", None),
    "Second Semester Language": ("World Language (second semester)", "gen_ed", None),
    "Third Semester Language": ("World Language (third semester)", "gen_ed", None),
    "Fourth Semester Language": ("World Language (fourth semester)", "gen_ed", None),
    "Linear Algebra": ("Linear Algebra", "elective_slot", "Linear Algebra"),
    "Probability or Statistics": ("Probability or Statistics", "elective_slot", "Probability or Statistics"),
    "COMP SCI Theory (COMP SCI 577 recommended)": ("COMP SCI Theory", "elective_slot", "Theory of Computer Science"),
    "COMP SCI Software/Hardware": ("COMP SCI Software/Hardware", "elective_slot", None),
    "COMP SCI Applications": ("COMP SCI Applications", "elective_slot", None),
    "COMP SCI Elective": ("COMP SCI Elective", "elective_slot", None),
    "Social Science Breadth": ("Social Science Breadth", "gen_ed", None),
    "Humanities Breadth": ("Humanities Breadth", "gen_ed", None),
    "Literature Breadth": ("Literature Breadth", "gen_ed", None),
    "Biological Science Breadth": ("Biological Science Breadth", "gen_ed", None),
    "Physical Science Breadth": ("Physical Science Breadth", "gen_ed", None),
    "Elective": ("Elective", "elective_slot", None),
}
# Notes for each slot, condensed from the requirement text on the same page.
SLOT_NOTES = {
    "Communication Part A": "UW general education: one course with the Communication A designation (or a "
        "qualifying placement score).",
    "Communication Part B": "UW general education: one course with the Communication B designation.",
    "Ethnic Studies": "UW general education: one 3+ credit course with the Ethnic Studies designation.",
    "Linear Algebra": "Wisconsin major requirement: complete one of MATH 320, 340, 345, 341, or 375 (3-5 credits; "
        "the plan gives 3).",
    "Probability or Statistics": "Wisconsin major requirement: complete one course from a list of nine "
        "probability and statistics courses.",
    "COMP SCI Theory": "Wisconsin major requirement: complete one of COMP SCI 577 (Introduction to Algorithms, "
        "recommended by the plan) or COMP SCI 520 (Introduction to Theory of Computing).",
    "COMP SCI Software/Hardware": "Wisconsin major requirement: complete two courses (6-8 credits) from a list "
        "of 12 (e.g. software engineering, operating systems, compilers, databases, networks, security).",
    "COMP SCI Applications": "Wisconsin major requirement: complete one course from a list of 13 applications "
        "courses (e.g. numerical methods, optimization, artificial intelligence, graphics, computer vision, "
        "human-computer interaction).",
    "COMP SCI Elective": "Wisconsin major requirement: complete two courses (6-8 credits) from the Electives "
        "list, which includes courses from the other lists and further CS and cross-listed courses.",
    "Social Science Breadth": "L&S BS breadth: 12 credits with the Social Science designation.",
    "Humanities Breadth": "L&S BS breadth: 12 credits with the Humanities or Literature designation, at least 6 "
        "of them Literature.",
    "Literature Breadth": "L&S BS breadth: 12 credits with the Humanities or Literature designation, at least 6 "
        "of them Literature.",
    "Biological Science Breadth": "L&S BS breadth: 12 credits of natural science, including biological and "
        "physical science courses.",
    "Physical Science Breadth": "L&S BS breadth: 12 credits of natural science, including biological and "
        "physical science courses.",
    "Elective": "Free electives to reach the 120 degree credits.",
}
LANGUAGE_NOTE = ("L&S BS language requirement: the third unit of a language other than English (placement or "
                 "high school study may satisfy it). The plan places four semesters of language.")
OPTIONAL_NOTE = "Marked in the plan as '{}'; its credit is part of the plan's 120."
# Roman numerals stay capitalized when an all-caps Guide title is converted.
ROMAN = {"I", "II", "III", "IV", "V"}
SMALL = {"and", "of", "the", "for", "to", "in", "a", "an", "with", "on"}


# Text of a cell with non-breaking and zero-width spaces made normal. CourseLeaf puts a
# zero-width space (​) after the "/" of a cross-listing, which would break CODE.
def text(cell) -> str:
    """Return a cell's visible text, whitespace-collapsed."""
    t = cell.get_text(" ").replace("\xa0", " ").replace("​", "")
    t = re.sub(r"\s*/\s*", "/", t)  # "COMP SCI/ E C E" -> "COMP SCI/E C E"
    return re.sub(r"\s+", " ", t).strip()


# "PROGRAMMING I" -> "Programming I": title case, small words lowercased after the first,
# Roman numerals kept upper. str.title() alone would give "Programming I" but also
# "And", so the small words are fixed afterwards.
def title_case(caps: str) -> str:
    """Return an all-caps Guide title in title case."""
    words = []
    for i, w in enumerate(caps.split()):
        if w in ROMAN or "&" in w:  # "L&S" stays as written
            words.append(w)
        elif i and w.lower() in SMALL:
            words.append(w.lower())
        else:
            words.append(w.capitalize())
    return " ".join(words)


# Split a possibly cross-listed code into its listings: "COMP SCI/E C E 354" ->
# ["COMP SCI 354", "E C E 354"].
def listings(subjects: str, number: str) -> list[str]:
    """Return every code of a cross-listed course, first listing first."""
    return [f"{s} {number}" for s in subjects.split("/")]


# Titles of the courses on the saved Guide subject pages, keyed by every listing code.
def guide_titles() -> dict[str, str]:
    """Return {code: title} from data/raw/wisc/*_courses-*.html."""
    titles = {}
    for path in sorted(SCHOOL.raw.glob("*_courses-*.html")):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        for block in soup.select("div.courseblock"):
            m = CODE.match(text(block.select_one(".courseblockcode")))
            heading = text(block.select_one(".courseblocktitle"))
            caps = heading.split("—", 1)[-1].strip()  # the title follows an em dash
            if m:
                for code in listings(*m.groups()):
                    titles[code] = title_case(caps)
    return titles


# Read the requirement tables: {heading: [(code, title, cross-listings)]} for every
# table, where a row's code is its first listing. "orclass" rows ("or COMP SCI 538")
# are alternatives and are kept with their own code.
def requirement_tables(soup) -> dict[str, list[tuple[str, str, list[str]]]]:
    """Return the requirement tables' courses, keyed by the heading above each table."""
    tables = {}
    for table in soup.find_all("table", class_="sc_courselist"):
        heading = text(table.find_previous(["h2", "h3", "h4", "h5"]))
        courses = []
        for tr in table.find_all("tr"):
            # The title cell has no class here (unlike other CourseLeaf sites); it is the
            # cell right after the code cell.
            code_cell = tr.find("td", class_="codecol")
            title_cell = code_cell.find_next_sibling("td") if code_cell else None
            m = CODE.search(text(code_cell)) if code_cell else None
            if m and title_cell:
                codes = listings(*m.groups())
                courses.append((codes[0], text(title_cell), codes[1:]))
        tables[heading] = courses
    return tables


# A blank row dict with the defaults every row starts from. hours is "3" or "3-4".
def base_row(hours: str) -> dict:
    """Return a required-course row with credits from an hours string."""
    lo, _, hi = hours.partition("-")  # "3-4" -> ("3", "-", "4"); "3" -> ("3", "", "")
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": int(lo),
            "credits_max": int(hi or lo), "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": ""}


# Turn one plan cell into a row. A cell is a slot label (looked up in SLOTS first, since
# "COMP SCI Theory (COMP SCI 577 recommended)" contains a code) or a course code with an
# optional "(Optional ... Course)" label.
def parse_cell(label: str, hours: str, titles: dict, tables: dict) -> dict:
    """Return the row for one term's cell in a plan-grid row."""
    row = base_row(hours)
    if label in SLOTS:
        title, rtype, table = SLOTS[label]
        notes = LANGUAGE_NOTE if title.startswith("World Language") else SLOT_NOTES.get(title, "")
        row.update(title=title, requirement_type=rtype, notes=notes)
        if table:
            codes = [code for code, _, _ in tables[table]]
            subjects = {c.rsplit(" ", 1)[0] for c in codes}  # rsplit: the subject is everything before the number
            row.update(options="; ".join(codes), subject=subjects.pop() if len(subjects) == 1 else "")
        return row
    m = CODE.match(label)
    if not m:
        raise SystemExit(f"Unknown slot label in the plan grid: {label!r}. Add it to SLOTS.")
    codes = listings(*m.groups())
    code = codes[0]
    subj, num = code.rsplit(" ", 1)
    row.update(course_code=code, subject=subj, number=num, title=titles.get(code, ""))
    notes = []
    if len(codes) > 1:
        notes.append(f"Cross-listed as {', '.join(codes[1:])}.")
    extra = re.search(r"\((Optional[^)]*)\)", label)  # e.g. "(Optional Programming Course)"
    if extra:
        notes.append(OPTIONAL_NOTE.format(extra.group(1)))
    row["notes"] = " ".join(notes)
    return row


# Walk the plan grid. Each course row has four cells: Fall code, Fall credits, Spring
# code, Spring credits; a term's half is empty when that term has fewer courses.
def parse_plan(soup, titles: dict, tables: dict) -> tuple[pd.DataFrame, dict, int]:
    """Return (rows, {(year, term): stated credits}, stated total)."""
    grid = soup.find("table", class_="sc_plangrid")
    rows, term_hours, total, year = [], {}, None, None
    for tr in grid.find_all("tr"):
        classes = tr.get("class") or []  # rows without a class attribute give None
        cells = [text(c) for c in tr.find_all(["td", "th"])]
        if "plangridyear" in classes:
            year = YEARS[cells[0]]
        elif "plangridterm" in classes:
            continue  # "Fall | Credits | Spring | Credits"
        elif "plangridsum" in classes:
            # cells: ["", fall credits, "", spring credits]; [1::2] takes every other cell from 1.
            for term, hours in zip(TERMS, cells[1::2]):
                term_hours[(year, term)] = int(hours)
        elif "plangridtotal" in classes:
            total = int(re.search(r"\d+", cells[0]).group())
        else:
            # A half with no course can be one merged (colspan) cell, so pad to four cells.
            cells += [""] * (4 - len(cells))
            # Pair the cells as (label, hours) per term: cells[0:2] is Fall, cells[2:4] Spring.
            for term, (label, hours) in zip(TERMS, [cells[0:2], cells[2:4]]):
                if not label:
                    continue  # this term has no course in this row
                r = parse_cell(label, hours, titles, tables)
                r.update(orig_year=year, orig_term=term)
                rows.append(r)
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, term_hours, total


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, term_hours: dict, total: int, tables: dict) -> list[str]:
    """Return failed-check messages."""
    failures = []
    low, high = int(df["credits_min"].sum()), int(df["credits_max"].sum())
    if low != total:
        failures.append(f"Credits (low end) {low} != the plan's Total Credits {total}.")
    if SCHOOL.credits != (low, high):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the plan rows sum to {low}-{high}.")
    for (y, t), hours in term_hours.items():
        got = df[(df["orig_year"] == y) & (df["orig_term"] == t)]["credits_min"].sum()
        if got != hours:
            failures.append(f"Year {y} {t}: {got} credits, plan says {hours}.")
    if len(term_hours) != 8:
        failures.append(f"Expected 8 terms, found {len(term_hours)}.")
    untitled = df[(df["course_code"] != "") & (df["title"] == "")]["course_code"].tolist()
    failures += [f"No title found for {c}." for c in untitled]
    # Every course in the fixed requirement tables must be in the plan.
    in_plan = set(df["course_code"])
    for heading in ["Foundational Math Courses", "Basic Computer Sciences"]:
        for code, _, _ in tables.get(heading, []):
            if code not in in_plan:
                failures.append(f"Required course {code} ({heading}) is not in the plan.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    if SCHOOL.college not in text(soup):
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(path)}.")
    tables = requirement_tables(soup)
    # Requirement-table titles (proper case) take precedence over the Guide's capitals.
    # {**a, **b} merges two dicts, with b's values winning on shared keys.
    titles = {**guide_titles(), **{code: title for rows in tables.values() for code, title, _ in rows}}
    df, term_hours, total = parse_plan(soup, titles, tables)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()}-{df['credits_max'].sum()} (plan states {total})")
    failures = check(df, term_hours, total, tables)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 13 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
