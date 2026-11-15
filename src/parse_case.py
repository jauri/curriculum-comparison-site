"""Parse Case Western Reserve's Computer Science BS sample plan into one row per course or slot.

Case Western's school-specific plan parser (batch 5). Reads the newest saved bulletin
page (data/raw/case/*_bs-cs-bulletin.html, 2026-2027 CWRU General Bulletin) and writes
data/processed/case/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

The page is a CourseLeaf bulletin page laid out like Colorado's: one "sc_plangrid"
table ("Sample Plan of Study") with year rows ("plangridyear": "First Year" ...),
term rows ("plangridterm": "Fall", "Spring"), per-term "plangridsum" rows, and a
"plangridtotal" row ("Total Credit Hours 122"). Course rows hold a code link; slot rows
hold a span.comment label ("Open Elective", "Technical Elective"). Several
"sc_courselist" tables list the requirements; the four "Breadth Area" blocks and the
"Required Statistics Course" block give slot options.

Modeling decisions (batch 5, for the user's review):
- "MATH 122 or MATH 124", "MATH 223 or MATH 227", and "MATH 201 or MATH 307" are
  elective_slot rows with both codes in `options` (choose one), titled as the plan does
  with both titles joined by " or ".
- CSDS 132, PHYS 121, and PHYS 122 stay required course rows; the requirements list's
  alternatives (CSDS 134 & CSDS 235; PHYS 115/123, PHYS 116/124) go in notes.
- "Academic Inquiry Seminar, Breadth, or Elective course" and "Breadth, or Elective
  course" (footnote a: the Unified General Education Requirement) are gen_ed rows.
  "Breadth" there means general education breadth, not the CS breadth areas.
- The eight "Computer Science Breadth course" slots are elective_slot rows. Students
  take two from each of four areas, so the slot is a choice from a mixed list; the
  areas and their courses go in notes, not `options` (spec 03).
- "Statistics Elective" is an elective_slot with the seven statistics courses in
  `options`; "Technical Elective" (six slots; any CSDS course or the approved Group 1
  and 2 lists) and "Open Elective" (free elective) are elective_slot rows.

Usage:
    python src/parse_case.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("case")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Sample Plan of Study, Computer Science BS, 2026-2027 CWRU General Bulletin"

YEARS = {"First Year": 1, "Second Year": 2, "Third Year": 3, "Fourth Year": 4}
TERMS = {"Fall": "Fall", "Spring": "Spring"}
# One CWRU course code: 3-4 capital letters, a space, 3 digits (e.g. "CSDS 132").
CODE = re.compile(r"\b([A-Z]{3,4}) (\d{3})\b")
# Alternatives the requirements list accepts for three plan courses (condensed by hand
# from the "or" rows and the Science Requirement block of the saved page).
ALTERNATIVES = {
    "CSDS 132": "CWRU: CSDS 134 & CSDS 235 (Programming in Python, then The Java Programming Language) may "
                "replace it.",
    "PHYS 121": "CWRU: one of PHYS 115, PHYS 121, or PHYS 123; the science requirement may also be met by a "
                "biology, chemistry, or geological sciences minor or major.",
    "PHYS 122": "CWRU: one of PHYS 116, PHYS 122, or PHYS 124.",
}
GENED_NOTE = ("CWRU footnote a: the Unified General Education Requirement (academic inquiry seminars and "
              "breadth courses), or an elective.")
TECH_NOTE = ("CWRU: any CSDS course, or a course from the approved technical electives (Group 1, or at most "
             "two from Group 2); with the breadth and core courses, at least 20 computer science and related "
             "courses and 63 credit hours.")
FREE_NOTE = "CWRU: an open (free) elective."
SECURE_NOTE = ("CWRU: one course from the secure computing list (CSDS 344, 356, 427, 444, 448, or MATH 408) "
               "is also required; it can double-count as a breadth or technical elective.")


# Text of a tag with non-breaking spaces made normal and whitespace collapsed.
def text(tag) -> str:
    """Return a tag's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", tag.get_text(" ").replace("\xa0", " ")).strip()


# Read every requirements list into {area header: [(code cell, title), ...]}. Headers
# ("areaheader") start a block; subheaders ("Choose two of the following:") are skipped
# so their rows stay in the area's block. Comment rows with no code are skipped.
# A block never runs past its table: the technical elective lists (Group 1, Group 2)
# are tables without an area header, so `current` is reset at each table and their
# rows are not read into the block before them.
def requirement_blocks(soup) -> dict[str, list[tuple[str, str]]]:
    """Return the requirements lists grouped by area header."""
    blocks = {}
    for table in soup.find_all("table", class_="sc_courselist"):
        current = None
        for tr in table.find_all("tr"):
            classes = tr.get("class") or []  # rows without a class attribute give None
            if "areaheader" in classes:
                current = text(tr.find("td")).rstrip(":")  # "Required Statistics Course:" -> without the colon
                blocks[current] = []
                continue
            code_cell = tr.find("td", class_="codecol")
            if current is None or code_cell is None or "areasubheader" in classes:
                continue
            title_cell = code_cell.find_next_sibling("td")
            blocks[current].append((text(code_cell), text(title_cell) if title_cell else ""))
    return blocks


# A blank row dict with the defaults every row starts from.
def base_row(hours: str) -> dict:
    """Return a row with credits from an hours string like "3"."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": int(hours),
            "credits_max": int(hours), "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": ""}


# Build the row for a labeled slot from its plan label and the requirements lists.
def slot_row(label: str, hours: str, blocks: dict) -> dict:
    """Return the row for one slot label of the plan grid."""
    row = base_row(hours)
    if label in ("Academic Inquiry Seminar, Breadth, or Elective course", "Breadth, or Elective course"):
        row.update(title="General education breadth or elective", requirement_type="gen_ed", notes=GENED_NOTE)
    elif label == "Computer Science Breadth course":
        areas = [h for h in blocks if h.startswith("Breadth Area")]
        row.update(title="Computer science breadth course", requirement_type="elective_slot",
                   notes="CWRU: eight breadth courses, at least two from each area. " + " ".join(
                       f"{a}: {', '.join(c for c, _ in blocks[a])}." for a in areas) + " " + SECURE_NOTE)
    elif label == "Statistics Elective":
        codes = [c for c, _ in blocks["Required Statistics Course"]]
        row.update(title="Statistics elective", requirement_type="elective_slot", options="; ".join(codes))
    elif label == "Technical Elective":
        row.update(title="Technical elective", requirement_type="elective_slot", notes=TECH_NOTE)
    elif label == "Open Elective":
        row.update(title="Open elective", requirement_type="elective_slot", notes=FREE_NOTE)
    else:
        raise SystemExit(f"Unknown slot label in the plan grid: {label!r}. Add it to slot_row().")
    return row


# Walk the plan grid: year and term headings set the placement, sum rows give each
# term's stated hours, and every other row is a course, an "A or B" choice, or a slot.
def parse_plan(soup, blocks: dict) -> tuple[pd.DataFrame, dict, str]:
    """Return (rows, {(year, term): stated hours}, stated total)."""
    rows, term_hours, total = [], {}, ""
    year = term = None
    for tr in soup.find("table", class_="sc_plangrid").find_all("tr"):
        classes = tr.get("class") or []
        if "plangridyear" in classes:
            year = YEARS[text(tr)]
        elif "plangridterm" in classes:
            term = TERMS[text(tr.find("th"))]  # the first term row also holds the hours header
        elif "plangridsum" in classes:
            term_hours[(year, term)] = text(tr.find("td", class_="hourscol"))
        elif "plangridtotal" in classes:
            total = text(tr.find("td", class_="hourscol"))
        else:
            for sup in tr.find_all("sup"):
                sup.decompose()  # drop footnote markers ("... Elective course a") before reading labels
            hours = text(tr.find("td", class_="hourscol"))
            code_cell = tr.find("td", class_="codecol")
            label = text(code_cell)
            codes = [f"{s} {n}" for s, n in CODE.findall(label)]
            if len(codes) == 1 and CODE.fullmatch(label):
                row = base_row(hours)
                row.update(course_code=label, subject=codes[0].split()[0], number=codes[0].split()[1],
                           title=text(code_cell.find_next_sibling("td")), notes=ALTERNATIVES.get(label, ""))
            elif len(codes) == 2 and " or " in label:
                # "MATH 122 or MATH 124" with "Title A or Title B": a choose-one slot.
                row = base_row(hours)
                row.update(title=text(code_cell.find_next_sibling("td")), subject=codes[0].split()[0],
                           requirement_type="elective_slot", options="; ".join(codes))
            else:
                row = slot_row(label, hours, blocks)
            row.update(orig_year=year, orig_term=term)
            rows.append(row)
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, term_hours, total


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, term_hours: dict, total: str, blocks: dict) -> list[str]:
    """Return failed-check messages."""
    failures = []
    got = df["credits_min"].sum()
    if str(got) != total:
        failures.append(f"Credits {got} != the plan's Total Credit Hours {total}.")
    if SCHOOL.credits != (got, got):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the plan sums to {got}.")
    for (y, t), hours in term_hours.items():
        s = df[(df["orig_year"] == y) & (df["orig_term"] == t)]["credits_min"].sum()
        if str(s) != hours:
            failures.append(f"Year {y} {t}: {s} hours, page says {hours}.")
    if len(term_hours) != 8:
        failures.append(f"Expected 8 terms, found {len(term_hours)}.")
    # Eight breadth courses (two from each of four areas) and 20 CS courses in all:
    # 6 core + 8 breadth + 6 technical electives.
    breadth = (df["title"] == "Computer science breadth course").sum()
    if breadth != 8:
        failures.append(f"{breadth} computer science breadth slots; the requirements say eight.")
    core = [c for c, _ in blocks["Required Core Courses"] if CODE.fullmatch(c)]
    missing = sorted(set(core) - set(df["course_code"]))
    if missing:
        failures.append(f"Core courses not in the plan: {', '.join(missing)}.")
    cs = len(core) + breadth + (df["title"] == "Technical elective").sum()
    if cs != 20:
        failures.append(f"{cs} CS and related courses (core + breadth + technical); the requirements say 20.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page = text(soup)
    if SCHOOL.college not in page:
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(path)}.")
    if "2026-2027 CWRU General Bulletin" not in page:
        raise SystemExit(f"'2026-2027 CWRU General Bulletin' not found on {rel(path)}; check the bulletin year.")
    blocks = requirement_blocks(soup)
    df, term_hours, total = parse_plan(soup, blocks)
    failures = check(df, term_hours, total, blocks)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (plan states {total})")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All batch 5 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
