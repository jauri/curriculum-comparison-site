"""Parse UT Dallas's CS BS four-year plan into one row per course or requirement slot.

UT Dallas's school-specific plan parser (batch 4). Reads the newest saved "4-Year Plan
Example" (data/raw/utd/*_bs-cs-four-year.html, 2026 Undergraduate Catalog) and the
degree-requirements page (*_bs-cs-program.html, which states the college and the 124
semester credit hours), and writes data/processed/utd/plan_parsed.csv with the columns
in common.PARSED_COLUMNS.

The plan is one HTML table that shows two semesters side by side. Each year has a
heading row ("Freshman Year", spanning all 11 columns), a header row ("Semester 1 -
Fall | Notes | Preferred | Core | SCH | (spacer) | Semester 2 - Spring | ..."), course
rows, and a "Total" row. Columns 0-4 are the fall semester and 6-10 the spring; column 5
is a spacer cell with a rowspan. Two layout habits need care:
- Choice pairs are written as a course row followed by an "or MATH 2413" row, and their
  shared SCH cell has rowspan="2". The table is first expanded into a full grid (every
  rowspan copied down), so each row can be read by column position.
- Texas core slots are written by their statewide component code, "040 Core". They get
  the component's name with the code in parentheses, "Language, Philosophy and Culture
  (040)", as UT Austin's parser does (the codes are the Texas Core Curriculum's; the
  program page lists the same components by name).

Modeling decisions (batch 4, for the user's review):
- "MATH 2417 or MATH 2413" (Calculus I, or Differential Calculus) and "MATH 2419 or
  MATH 2414" are one elective_slot row each, with both codes in `options` (choice rule
  of specs/03-processing.md).
- The plan's numbered notes are copied into the notes of the rows they mark.
- The plan's "CS 3337" is read as CS 3377 (PLAN_TYPOS): no CS 3337 exists, and the
  requirements page's major core lists CS 3377, which the plan otherwise lacks.

Usage:
    python src/parse_utd.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("utd")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Four-Year Degree Plan (Example), 2026 Undergraduate Catalog"

YEARS = {"Freshman Year": 1, "Sophomore Year": 2, "Junior Year": 3, "Senior Year": 4}
# A UTD course code: 2-4 capital letters, a space, 4 digits (e.g. "CS 1337").
CODE = re.compile(r"\b([A-Z]{2,4}) (\d{4})\b")
# Texas Core Curriculum component codes -> names (the program page lists the names).
CORE = {
    "010": "Communication", "020": "Mathematics", "030": "Life and Physical Sciences",
    "040": "Language, Philosophy and Culture", "050": "Creative Arts", "060": "American History",
    "070": "Government/Political Science", "080": "Social and Behavioral Sciences",
    "090": "Component Area Option",
}
# Plan codes that are typos -> the course the degree-requirements page names instead.
# "CS 3337" has an empty catalog page and is not in the requirements; the requirements'
# major core lists CS 3377 Systems Programming in UNIX and Other Environments, which the
# plan otherwise lacks. check() confirms both facts on the saved pages (for the user's review).
PLAN_TYPOS = {"CS 3337": "CS 3377"}
# Plan slot labels -> (title, requirement_type, notes from the program page).
SLOTS = {
    "Free Elective": ("Free Elective", "elective_slot",
                      "UTD: 13 free elective hours, lower or upper division; the plan must reach 45 upper-division hours."),
    "Major Technical Elective": ("Major Technical Elective", "elective_slot",
                                 "UTD: 9 hours of 4000-level computer science (or closely related, advisor-approved) courses."),
}
# Fall uses columns 0-4, spring 6-10: label, notes, preferred, core, SCH.
SIDES = {"Fall": 0, "Spring": 6}


# Text of a cell with whitespace collapsed.
def text(cell) -> str:
    """Return a cell's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", cell.get_text(" ").replace("\xa0", " ")).strip()


# Expand an HTML table into a list of rows of equal width, copying a cell with
# rowspan="n" into the n rows it covers and a colspan cell across its columns. A row
# whose one cell spans the full width (a year heading or a blank separator) ends any
# rowspan still open: the page's spacer cells claim more rows than their year has.
def expand(table, width: int = 11) -> list[list[str]]:
    """Return the table as a grid of cell texts."""
    grid, open_spans = [], {}  # open_spans: column -> [rows left, text]
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) == 1 and int(cells[0].get("colspan", 1)) == width:
            open_spans = {}
            grid.append([text(cells[0])] * width)
            continue
        row, col = {}, 0
        cell_iter = iter(cells)  # iter(): take cells one at a time as free columns appear
        while col < width:
            if col in open_spans:
                row[col] = open_spans[col][1]
                open_spans[col][0] -= 1
                if open_spans[col][0] == 0:
                    del open_spans[col]
                col += 1
                continue
            cell = next(cell_iter, None)  # next() with a default: None once cells run out
            if cell is None:
                break
            span, rows = int(cell.get("colspan", 1)), int(cell.get("rowspan", 1))
            for k in range(span):
                row[col + k] = text(cell)
                if rows > 1:
                    open_spans[col + k] = [rows - 1, text(cell)]
            col += span
        grid.append([row.get(i, "") for i in range(width)])
    return grid


# Read the plan's numbered notes ("NOTES: 1 Curriculum Requirements can ... 2 ...") into
# {number: text}. They are a separate table after the plan.
def read_notes(soup) -> dict[str, str]:
    """Return the plan's footnotes by number."""
    notes_text = text(soup.find_all("table")[1]).removeprefix("NOTES:").strip()
    # re.split with a capture group keeps the separators: ["", "1", "text", "2", "text", ...].
    parts = re.split(r"(?:^|\s)(\d) (?=[A-Z])", notes_text)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


# A blank row dict with the defaults every row starts from.
def base_row(hours: str) -> dict:
    """Return a row with credits from an SCH cell like "4"."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": int(hours),
            "credits_max": int(hours), "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": ""}


# Notes text for a row's note numbers ("1 , 3" -> "UTD note 1: ... UTD note 3: ...").
def note_text(marks: str, notes: dict) -> str:
    """Return the joined footnote texts for a Notes cell."""
    return " ".join(f"UTD note {n}: {notes[n]}" for n in re.findall(r"\d", marks))


# Walk the grid side by side. A row's fall half and spring half are read separately;
# an "or ..." label adds an option to the row just read on that side.
def parse_plan(grid: list[list[str]], notes: dict, titles: dict) -> tuple[pd.DataFrame, dict]:
    """Return (rows, {(year, term): stated SCH})."""
    rows, totals = [], {}
    year = None
    last = {}  # side -> the row dict most recently added on that side (for "or" rows)
    for g in grid:
        if g[0] in YEARS:
            year = YEARS[g[0]]
            continue
        if g[0].startswith("Semester") or not any(g):
            continue
        for term, c in SIDES.items():
            label, marks, _, core, sch = g[c:c + 5]
            if label == "Total":
                totals[(year, term)] = int(sch)
            elif label.startswith("or "):
                code = label.removeprefix("or ").strip()
                prev = last[term]
                first = prev["course_code"] or prev["options"]
                prev.update(course_code="", number="", requirement_type="elective_slot",
                            options=f"{first}; {code}",
                            title=f"{first} or {code} ({prev['title']})",
                            notes=(prev["notes"] + f" Student chooses one: {first} ({prev['title']}) | "
                                   f"{code} ({titles.get(code, '')}).").strip())
            elif label:
                row = base_row(sch)
                m = CODE.fullmatch(label)
                core_m = re.fullmatch(r"(\d{3}) Core", label)
                if m:
                    fixed = PLAN_TYPOS.get(label, label)
                    fm = CODE.fullmatch(fixed)
                    row.update(course_code=fixed, subject=fm.group(1), number=fm.group(2),
                               title=titles.get(fixed, ""), notes=note_text(marks, notes))
                    if fixed != label:
                        row["notes"] = (f"The plan prints '{label}', which has no catalog entry; the degree "
                                        f"requirements list {fixed} instead. " + row["notes"]).strip()
                elif core_m:
                    row.update(title=f"{CORE[core_m.group(1)]} ({core_m.group(1)})", requirement_type="gen_ed",
                               gened_tag=core_m.group(1),
                               notes="UTD: any course from this Texas Core Curriculum component (see advisor).")
                elif label in SLOTS:
                    title, rtype, note = SLOTS[label]
                    row.update(title=title, requirement_type=rtype, notes=note)
                else:
                    raise SystemExit(f"Unknown plan label: {label!r}. Add it to SLOTS.")
                row.update(orig_year=year, orig_term=term)
                rows.append(row)
                last[term] = row
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, totals


# Course titles from the saved per-course pages (courses/<date>_CS1337.html). Each page's
# <title> reads "Computer Science I - UT Dallas 2026 Undergraduate Catalog - ...", so the
# title is the text before " - UT Dallas" and the code comes from the file name
# ("..._CS1337.html" -> "CS 1337": letters, then a space, then the digits).
def course_titles() -> dict[str, str]:
    """Return {course code: catalog title} from the saved course pages."""
    titles = {}
    for path in sorted((SCHOOL.raw / "courses").glob("*_*.html")):
        key = re.fullmatch(r"([A-Z]+)(\d{4})", path.stem.split("_", 1)[1])
        head = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser").title
        title = text(head).split(" - UT Dallas")[0] if head else ""
        if key and title:
            titles[f"{key.group(1)} {key.group(2)}"] = title  # later dates overwrite earlier ones
    return titles


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, totals: dict, stated: int, program: str) -> list[str]:
    """Return failed-check messages."""
    failures = []
    for typo, fixed in PLAN_TYPOS.items():
        if typo in program or fixed not in program:
            failures.append(f"Typo fix {typo} -> {fixed} no longer matches the requirements page; review it.")
    got = df["credits_min"].sum()
    if got != stated:
        failures.append(f"Credits {got} != the program page's {stated} semester credit hours.")
    if SCHOOL.credits != (stated, stated):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the program page states {stated}.")
    for (y, t), sch in totals.items():
        s = df[(df["orig_year"] == y) & (df["orig_term"] == t)]["credits_min"].sum()
        if s != sch:
            failures.append(f"Year {y} {t}: {s} SCH, plan says {sch}.")
    if len(totals) != 8:
        failures.append(f"Expected 8 semester totals, found {len(totals)}.")
    untitled = df[(df["course_code"] != "") & (df["title"] == "")]["course_code"].tolist()
    if untitled:
        failures.append(f"No saved course page title for: {', '.join(untitled)}.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    plan_path = SCHOOL.newest("*_bs-cs-four-year.html")
    program_path = SCHOOL.newest(SCHOOL.credits_source)
    program = text(BeautifulSoup(program_path.read_text(encoding="utf-8"), "html.parser"))
    if SCHOOL.college not in program:
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(program_path)}.")
    m = re.search(r"Degree Requirements \((\d+) semester credit hours\)", program)
    if not m:
        raise SystemExit(f"Stated semester credit hours not found on {rel(program_path)}.")
    soup = BeautifulSoup(plan_path.read_text(encoding="utf-8"), "html.parser")
    df, totals = parse_plan(expand(soup.find_all("table")[0]), read_notes(soup), course_titles())

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(plan_path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (program page states {m.group(1)})")
    failures = check(df, totals, int(m.group(1)), program)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All batch 4 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
