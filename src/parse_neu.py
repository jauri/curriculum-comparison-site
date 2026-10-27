"""Parse Northeastern's BSCS sample plan of study into one row per course or slot.

Northeastern's school-specific plan parser (step 13). Reads the newest saved archived
2025-2026 catalog page (data/raw/neu/*_bscs-catalog-2025-26.html) and writes
data/processed/neu/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

The page's "Plan of Study" tab has two sample plans; the first, "Four Years, Two Co-ops
in Spring/Summer First Half", is used (chosen by the user in step 13). It is a
CourseLeaf "sc_plangrid" table laid out differently from UIC's: each year has FOUR term
columns side by side (Fall, Spring, Summer 1, Summer 2), each a pair of cells (course,
hours). An empty term cell is one cell with colspan="2", so a cell's term is found by
adding up colspans from the left, not by counting cells.

Modeling decisions (step 13):
- The grid names courses by code only. Titles and hours come from Northeastern's
  archived 2025-26 course pages (parse_neu_descriptions.catalog_courses), the same
  catalog year as the plan.
- "CS 2100 and CS 2101" (a course and its 1-hour lab or seminar, listed as one 5-hour
  line) becomes two required rows, each with its catalog hours; the parser checks they
  add up to the grid's hours.
- "MATH 1365 or 1465" is one elective_slot row with options "MATH 1365; MATH 1465"
  (the shorthand number takes the subject before it).
- "Co-op" cells (0 hours) become one row per co-op term: requirement_type coop,
  is_coop = true, orig_term_type coop, and no course code (Northeastern's plan names no
  co-op course; UC's does).
- Summer 1 and Summer 2 are kept as separate terms (orig_term "Summer 1" / "Summer 2"),
  so the plan has 10 academic terms. normalize.py's rule needs exactly 8, so how the
  half-summer terms fold into 8 semesters is a separate, reviewed decision.

Usage:
    python src/parse_neu.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel
from parse_neu_descriptions import catalog_courses

SCHOOL = load_school("neu")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN_HEADING = "Sample Plan of Study: Four Years, Two Co-ops in Spring/Summer First Half"
PLAN = f"{PLAN_HEADING}, archived 2025-2026 catalog"
# One Northeastern course code: 2-4 capital letters, a space, 4 digits (e.g. "CS 2100").
CODE = re.compile(r"\b([A-Z]{2,4}) (\d{4})\b")
# Slot labels as Northeastern writes them -> (title, requirement_type).
SLOTS = {
    "General Elective": ("General Elective", "elective_slot"),
    "Science Requirement": ("Science Requirement", "elective_slot"),
    "Computing and Social Issues": ("Computing and Social Issues", "elective_slot"),
    "Concentration Course": ("Concentration Course", "elective_slot"),
    "Khoury Elective": ("Khoury Elective", "elective_slot"),
    "Presentation Requirement": ("Presentation Requirement", "elective_slot"),
    "Security Course": ("Security Course", "elective_slot"),
}
# Notes that explain each slot, condensed from the 2025-26 requirement lists on the page.
SLOT_NOTES = {
    "General Elective": "Northeastern: 28 semester hours of general electives.",
    "Science Requirement": "Northeastern: any two courses (8 hours, with labs) from biology, chemistry, "
        "geology/environmental science, mathematics (e.g. MATH 1342, 2331, 3081), or physics.",
    "Computing and Social Issues": "Northeastern: one course from a list such as PHIL 1145 Technology and Human "
        "Values, HIST 2220 History of Technology, CY 4170 Law, Ethics, and Policy of Data and Digital Technologies.",
    "Concentration Course": "Northeastern: four courses in one concentration (e.g. Artificial Intelligence, "
        "Foundations, Human-Centered Computing, Software, Systems).",
    "Khoury Elective": "Northeastern: 8 hours of CS 2500 or higher, CY 2000 or higher, or DS 2500 or higher "
        "(with listed exceptions).",
    "Presentation Requirement": "Northeastern: one course such as COMM 1112 Public Speaking, COMM 1113 Business and "
        "Professional Speaking, or THTR 1130 Introduction to Acting.",
    "Security Course": "Northeastern: one of CY 2550 Foundations of Cybersecurity, CY 3740 Systems Security, "
        "CY 4740 Network Security.",
}
# Slots whose requirement is a short closed list of courses, so the slot row gets those
# codes as `options` (a choice row), like "MATH 1365 or 1465". Step 13: this lets the
# Security Course match the information-security concept, since every option is a
# security course. The page's own sentence is checked in main(), so the list traces to
# the source. Longer lists (Computing and Social Issues, Presentation) stay plain slots.
SLOT_OPTIONS = {"Security Course": ["CY 2550", "CY 3740", "CY 4740"]}
SLOT_OPTIONS_TEXT = {"Security Course": "Security Required Course Complete one of the following: 4 CY 2550 "
                     "Foundations of Cybersecurity CY 3740 Systems Security CY 4740 Network Security"}


# Text of a cell with non-breaking spaces made normal.
def text(cell) -> str:
    """Return a cell's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", cell.get_text(" ").replace("\xa0", " ")).strip()


# The (term name, cell text) pairs of one grid row. Columns are found by adding up
# colspans: an empty term is a single cell spanning both of its columns.
def row_cells(tr, terms: list[str]) -> list[tuple[str, str, str]]:
    """Return (term, course text, hours text) for each filled term cell of a row."""
    col, cells = 0, []
    tds = tr.find_all(["td", "th"])
    i = 0
    while i < len(tds):
        span = int(tds[i].get("colspan", 1))
        if span == 1 and i + 1 < len(tds):
            # A filled term: this cell is the course, the next is its hours.
            cells.append((terms[col // 2], text(tds[i]), text(tds[i + 1])))
            col, i = col + 2, i + 2
        else:
            col, i = col + span, i + 1
    return [c for c in cells if c[1]]


# Build the rows for one filled term cell: a course, a course + lab pair, a choice, a
# co-op term, or a slot. `catalog` maps codes to (title, hours) from the course pages.
def cell_rows(label: str, hours: int, catalog: dict) -> list[dict]:
    """Return one or more row dicts for a grid cell."""
    def base(h):
        return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": h, "credits_max": h,
                "requirement_type": "required", "gened_tag": "", "min_grade": "", "counts_toward_total": True,
                "notes": "", "options": "", "is_coop": False}

    if label == "Co-op":
        r = base(0)
        r.update(title="Co-op", requirement_type="coop", is_coop=True,
                 notes="Northeastern co-op work term (no course code in the plan).")
        return [r]
    if " or " in label:
        # "MATH 1365 or 1465": a bare number takes the subject of the code before it.
        subject = CODE.search(label).group(1)
        codes = [p if CODE.search(p) else f"{subject} {p}" for p in label.split(" or ")]
        titles = [catalog[c][0] for c in codes]
        r = base(hours)
        r.update(subject=subject, title=f"{' or '.join(codes)} ({titles[0]})", requirement_type="elective_slot",
                 options="; ".join(codes), notes=f"Student chooses one: {' | '.join(titles)}.")
        return [r]
    codes = [f"{s} {n}" for s, n in CODE.findall(label)]
    if codes:
        rows = []
        for code in codes:
            title, h = catalog[code]
            r = base(int(h))
            r.update(course_code=code, subject=code.split()[0], number=code.split()[1], title=title)
            if len(codes) > 1:
                r["notes"] = f"Listed in the plan as '{label}' ({hours} hours together)."
            rows.append(r)
        if sum(r["credits_min"] for r in rows) != hours:
            raise SystemExit(f"'{label}': catalog hours don't add up to the grid's {hours}.")
        return rows
    if label not in SLOTS:
        raise SystemExit(f"Unknown slot label in the plan grid: {label!r}. Add it to SLOTS.")
    title, rtype = SLOTS[label]
    r = base(hours)
    r.update(title=title, requirement_type=rtype, notes=SLOT_NOTES[title],
             options="; ".join(SLOT_OPTIONS.get(title, [])))  # "" for slots without a closed list
    return [r]


# Walk the chosen grid: track the year and the term columns from the heading rows, and
# read each course row's filled cells. Rows are collected per term, so the table lists
# a term's courses together (the grid interleaves terms across a row).
def parse_plan(soup, catalog: dict) -> tuple[pd.DataFrame, dict, int]:
    """Return (rows, {(year, term): stated hours}, stated total) from the plan grid."""
    heading = next(h for h in soup.find_all("h2") if text(h) == PLAN_HEADING)  # next(): first match
    grid = heading.find_next("table", class_="sc_plangrid")
    rows, term_hours, year, terms, total = [], {}, None, [], None
    for tr in grid.find_all("tr"):
        classes = tr.get("class") or []  # rows without a class attribute give None
        if "plangridyear" in classes:
            year = int(text(tr).split()[-1])  # "Year 2" -> 2
        elif "plangridterm" in classes:
            # Every other header cell is a term name; the others say "Hours" (or are empty).
            terms = [text(th) for th in tr.find_all("th")[::2] if text(th)]  # [::2] takes every second cell
        elif "plangridsum" in classes:
            sums = [text(td) for td in tr.find_all("td")[1::2]]  # hours cells are the 2nd of each pair
            for term, s in zip(terms, sums):
                if s:
                    term_hours[(year, term)] = int(s)
        elif "plangridtotal" in classes:
            total = int(re.search(r"\d+", text(tr)).group(0))
        else:
            for term, label, hours in row_cells(tr, terms):
                for r in cell_rows(label, int(hours), catalog):
                    coop = r.pop("is_coop")
                    r.update(orig_year=year, orig_term=term, orig_calendar_year="",
                             orig_term_type="coop" if coop else "academic", is_coop=coop)
                    rows.append(r)
    df = pd.DataFrame(rows)
    order = {t: i for i, t in enumerate(["Fall", "Spring", "Summer 1", "Summer 2"])}
    # Stable sort by (year, term) keeps each term's courses in their grid order.
    df = df.sort_values(["orig_year", "orig_term"], key=lambda s: s.map(order) if s.name == "orig_term" else s,
                        kind="mergesort").reset_index(drop=True)
    return df, term_hours, total


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, term_hours: dict, stated: int) -> list[str]:
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
    general = df[df["title"] == "General Elective"]["credits_min"].sum()
    if general != 28:
        failures.append(f"General elective hours {general} != the 28 the requirements list.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    if SCHOOL.college not in text(soup):
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(path)}.")
    for title, sentence in SLOT_OPTIONS_TEXT.items():
        if sentence not in text(soup):
            raise SystemExit(f"The {title} list changed on {rel(path)}; review SLOT_OPTIONS.")
    df, term_hours, stated = parse_plan(soup, catalog_courses())

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    academic = df[~df["is_coop"]].groupby(["orig_year", "orig_term"], sort=False)["credits_min"].sum()
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (plan total {stated})")
    print(f"Academic terms ({len(academic)}): " + ", ".join(f"Y{y} {t} {h}" for (y, t), h in academic.items()))
    failures = check(df, term_hours, stated)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 13 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
