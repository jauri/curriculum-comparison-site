"""Parse UC Berkeley's EECS BS freshman program into one row per course or slot.

UC Berkeley's school-specific plan parser (step 13). Reads the newest saved Berkeley
Engineering page for EECS (data/raw/ucb/*_eecs-major-program.html, saved through Chrome
by collect_ucb.py) and writes data/processed/ucb/plan_parsed.csv with the columns in
common.PARSED_COLUMNS.

The page is a WordPress page, not a catalog. The "2026-2027 Freshman Undergraduate
Program" is the first <table>: a "Course | Fall | Spring" grid where
- a one-cell row is a year heading ("Freshman Year" ... "Senior Year");
- a course row has the course text and one cell per term, holding units ("4", "3-5"),
  "–" (not that term), or nothing;
- a "Total" row gives each term's units.
Notes follow the table as numbered paragraphs (1 = natural science elective, 2 = H/SS,
3 = physics, 4-5 = upper-division and engineering units, 6 = ethics, 7 = free electives).

Modeling decisions (step 13):
- A row with units in both terms (Humanities/Social Sciences, "3-4 | 3-4") becomes one
  row per term.
- "X, or Y" choices are one elective_slot row with the option codes in `options`; a
  bare number ("61CL") takes the subject before it. "5B+5BL" are two options taken
  together (note 3).
- ELENG 66 and ELENG 64 are BOTH required, in either order, so the program lists
  "ELENG 66 or ELENG 64" in sophomore spring and again in junior fall. Each listing is a
  slot row with both options, and the note says both are taken.
- Credit total (decided with the user): the rows sum to 104-114 units, while the page
  says "A minimum of 120 units is required for graduation"; note 7 says free electives
  "may be necessary" to reach it. The registry records the plan's 104-114 and the 120
  minimum is kept in notes.
- The page's own sophomore-fall total says 13-16, but its rows (COMPSCI 61C 4, MATH 54
  4, physics 3-4, H/SS 3-4) give 14-16. The rows win (the specs' rule for a plan that
  disagrees with itself); the mismatch is listed in KNOWN_PAGE_TOTALS so the check
  still runs and would catch any other change.
- The page is laid out by year and term but has no calendar years, so
  orig_calendar_year is blank.

Usage:
    python src/parse_ucb.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("ucb")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "2026-2027 Freshman Undergraduate Program in Electrical Engineering & Computer Science"

YEARS = {"Freshman Year": 1, "Sophomore Year": 2, "Junior Year": 3, "Senior Year": 4}
TERMS = ["Fall", "Spring"]  # the order of the grid's unit columns
# One Berkeley course code: a subject of 4-7 capital letters, a space, then a number of
# 1-3 digits with up to two letters ("COMPSCI 61BL", "PHYSICS 5A", "MATH 54").
CODE = re.compile(r"\b([A-Z]{4,7}) (\d{1,3}[A-Z]{0,2})\b")
# A shorthand option after "or": just a number with letters, e.g. "61CL".
BARE = re.compile(r"^(\d{1,3}[A-Z]{0,2})\b")
# Slot labels as the page writes them (footnote marks removed) -> (title, requirement_type).
SLOTS = {
    "Natural Science Elective": ("Natural Science Elective", "elective_slot"),
    "Reading & Composition Part A Course": ("Reading & Composition Part A", "gen_ed"),
    "Reading & Composition Part B Course": ("Reading & Composition Part B", "gen_ed"),
    "Humanities/Social Sciences Courses": ("Humanities/Social Sciences course", "gen_ed"),
    "Ethics/Social Implications of Technology": ("Ethics/Social Implications of Technology", "elective_slot"),
    "Electrical Engineering and Computer Sciences Upper Division Technical Electives":
        ("EECS Upper Division Technical Electives", "elective_slot"),
    "Electrical Engineering and Computer Sciences Upper Division Technical Elective":
        ("EECS Upper Division Technical Electives", "elective_slot"),
    "Free Electives": ("Free Electives", "elective_slot"),
}
# Notes that explain each slot, condensed from the numbered notes under the table.
SLOT_NOTES = {
    "Natural Science Elective": "Berkeley note 1: one course such as ASTRON 7A/7B, BIOLOGY 1A+1AL or 1B, CHEM 1A+1AL, "
        "1B, 3A+3AL, 4A, MCB 32+32L, PHYSICS 7C or 5C+5CL, or an upper-division science course of 3+ units.",
    "Reading & Composition Part A": "Berkeley note 2: approved R&C course, letter grade C- or better, by the end of "
        "the freshman year. Part of the Humanities/Social Sciences requirement.",
    "Reading & Composition Part B": "Berkeley note 2: approved R&C course, letter grade C- or better, by the end of "
        "the sophomore year. Part of the Humanities/Social Sciences requirement.",
    "Humanities/Social Sciences course": "Berkeley note 2: four approved H/SS courses beyond the two R&C courses, "
        "with conditions listed at engineering.berkeley.edu/hss.",
    "Ethics/Social Implications of Technology": "Berkeley note 6: one course such as COMPSCI 195, ENGIN 125 or 185, "
        "PHILOS 121, or ISF 100D/100G; starred courses also count as upper-division H/SS.",
    "EECS Upper Division Technical Electives": "Berkeley notes 4-5: at least 20 upper-division EECS units, one course "
        "with a major design experience (e.g. COMPSCI 162, 164, 169, 184, 186; ELENG 140, 143), and at least 40 "
        "engineering units overall (note 5 still names EECS 16A/16B, which the 2026-27 program replaced with ELENG "
        "66/64).",
    "Free Electives": "Berkeley note 7: any course from any department. Free electives may be necessary to reach the "
        "120-unit minimum; the program's rows sum to 104-114 units.",
}
# The page's own sentence saying the pair is taken in either order. main() checks it is
# still on the page, because it is the source for marking the two rows all_in_any_order.
ELENG_ORDER_TEXT = "the order in which these courses are taken does not matter"
ELENG_NOTE = ("Berkeley: ELENG 66 and ELENG 64 are both required, in either order ('must take complete series but "
              f"{ELENG_ORDER_TEXT}'); the program lists the pair in sophomore spring and again in junior fall.")
# Term totals on the page that disagree with the page's own rows: (year, term) ->
# (stated units, units the rows give). See the docstring.
KNOWN_PAGE_TOTALS = {(2, "Fall"): ((13, 16), (14, 16))}
PHYSICS_B_NOTE = "Berkeley note 3: PHYSICS 5B is taken together with PHYSICS 5BL (5A must be followed by 5B and 5BL)."


# Text of a cell with non-breaking spaces made normal.
def text(cell) -> str:
    """Return a cell's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", cell.get_text(" ").replace("\xa0", " ")).strip()


# Remove footnote markers. The page writes them as <sup> tags ("Natural Science
# Elective<sup>1</sup>"); some appear as plain trailing digits after a label
# ("Elective 4 , 5"), which the regex strips from labels that end in words.
def strip_marks(cell) -> str:
    """Return a cell's text without footnote marks."""
    for sup in cell.find_all("sup"):
        sup.decompose()  # decompose() deletes the tag and its text from the tree
    return re.sub(r"(?<=[a-z])\s*\d(?:\s*,\s*\d)*\s*$", "", text(cell))  # (?<=[a-z]): only after a word


# Units text -> (min, max), or None for "–" or an empty cell.
def units(cell_text: str):
    """Return (min, max) units for a cell like "4" or "3-5", or None."""
    m = re.fullmatch(r"(\d+)(?:-(\d+))?", cell_text.replace("–", "-").strip())
    return (int(m.group(1)), int(m.group(2) or m.group(1))) if m else None


# The option codes of a course cell such as "PHYSICS 7B – Physics ..., or PHYSICS 5B –
# Introductory ...+5BL – ..." -> ["PHYSICS 7B", "PHYSICS 5B", "PHYSICS 5BL"]. Each
# ", or " part starts with a code or a bare number; "+5BL" adds a co-taken course.
def option_codes(label: str) -> list[str]:
    """Return the course codes named in a course cell, in order."""
    codes, subject = [], None
    for part in re.split(r",? or ", label):
        for piece in part.split("+"):
            piece = piece.strip()
            m = CODE.match(piece)
            if m:
                subject = m.group(1)
                codes.append(f"{m.group(1)} {m.group(2)}")
            elif subject and BARE.match(piece):
                codes.append(f"{subject} {BARE.match(piece).group(1)}")
    return codes


# The catalog title of the first course in a cell: the text after "CODE – " up to the
# next ", or" / "+" / "(".
def first_title(label: str) -> str:
    """Return the first course title written in a course cell."""
    after = label.split(" – ", 1)[1] if " – " in label else label
    return re.split(r",? or |\+|\s\(", after)[0].strip()


# Build the row for one course cell in one term.
def course_row(label: str, lo: int, hi: int) -> dict:
    """Return a row dict for a course, choice, or slot cell."""
    row = {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": lo, "credits_max": hi,
           "requirement_type": "required", "gened_tag": "", "min_grade": "", "counts_toward_total": True,
           "notes": "", "options": ""}
    codes = option_codes(label)
    if not codes:
        if label not in SLOTS:
            raise SystemExit(f"Unknown slot label in the program table: {label!r}. Add it to SLOTS.")
        title, rtype = SLOTS[label]
        row.update(title=title, requirement_type=rtype, notes=SLOT_NOTES[title],
                   min_grade="C-" if title.startswith("Reading & Composition") else "")
        return row
    if len(codes) == 1:
        subj, num = codes[0].split()
        row.update(course_code=codes[0], subject=subj, number=num, title=first_title(label))
        return row
    subjects = {c.split()[0] for c in codes}
    if "+" in label:
        shown = " or ".join([codes[0], " + ".join(codes[1:])])  # "PHYSICS 7B or PHYSICS 5B + PHYSICS 5BL"
    else:
        shown = " or ".join(codes)
    note = f"Student chooses one: {shown}."
    if set(codes) == {"ELENG 66", "ELENG 64"}:
        note = ELENG_NOTE
        # Both are required; the two listings only let students pick the order (step 13).
        row.update(choice_kind="all_in_any_order", choice_group="eleng-66-64")
    elif "+" in label:
        note += " " + PHYSICS_B_NOTE
    row.update(subject=subjects.pop() if len(subjects) == 1 else "", title=f"{shown} ({first_title(label)})",
               requirement_type="elective_slot", options="; ".join(codes), notes=note)
    return row


# Walk the first table: year headings, course rows (one row per term with units), and
# the "Total" rows that give each term's stated units.
def parse_plan(soup) -> tuple[pd.DataFrame, dict]:
    """Return (rows, {(year, term): (min, max) stated units})."""
    table = soup.find_all("table")[0]
    rows, term_units, year = [], {}, None
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        first = strip_marks(cells[0])
        if len(cells) == 1 or first in YEARS:
            year = YEARS.get(first, year)
            continue
        if first == "Course":
            continue  # the header row
        values = [units(text(c)) for c in cells[1:3]]
        if first == "Total":
            for term, u in zip(TERMS, values):
                term_units[(year, term)] = u
            continue
        for term, u in zip(TERMS, values):
            if u:
                r = course_row(first, *u)  # *u unpacks (min, max) into the two arguments
                r.update(orig_year=year, orig_term=term)
                rows.append(r)
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    # Group each term's rows together (Fall before Spring within a year), keeping the
    # table's order inside a term (stable mergesort).
    df = df.sort_values(["orig_year", "orig_term"], key=lambda s: s.map(TERMS.index) if s.name == "orig_term" else s,
                        kind="mergesort").reset_index(drop=True)
    return df, term_units


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, term_units: dict, page: str) -> list[str]:
    """Return failed-check messages."""
    failures = []
    for (y, t), stated in term_units.items():
        sel = df[(df["orig_year"] == y) & (df["orig_term"] == t)]
        got = (int(sel["credits_min"].sum()), int(sel["credits_max"].sum()))
        if KNOWN_PAGE_TOTALS.get((y, t)) == (stated, got):
            print(f"Known page total: Year {y} {t} says {stated[0]}-{stated[1]}, rows give {got[0]}-{got[1]}.")
        elif got != stated:
            failures.append(f"Year {y} {t}: {got[0]}-{got[1]} units, page says {stated[0]}-{stated[1]}.")
    total = (int(df["credits_min"].sum()), int(df["credits_max"].sum()))
    if SCHOOL.credits != total:
        failures.append(f"schools.csv says {SCHOOL.credits} units but the program's rows sum to {total}.")
    if "A minimum of 120 units is required for graduation" not in page:
        failures.append("The page no longer states the 120-unit minimum; review the credit note.")
    if ELENG_ORDER_TEXT not in page:
        failures.append("The page no longer says ELENG 66/64 may be taken in either order; review choice_kind.")
    if len(term_units) != 8:
        failures.append(f"Expected 8 terms, found {len(term_units)}.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page = text(soup)
    if PLAN not in page:
        raise SystemExit(f"'{PLAN}' not found on {rel(path)}; the page may have moved to a new year.")
    df, term_units = parse_plan(soup)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Units: {df['credits_min'].sum()}-{df['credits_max'].sum()} (page states a 120-unit minimum)")
    failures = check(df, term_units, page)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 13 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
