"""Parse Colorado Boulder's CS BS plan of study into one row per course or requirement slot.

Colorado's school-specific plan parser (batch 4). Reads the newest saved catalog page
(data/raw/colorado/*_bs-cs-catalog.html, 2026-2027 University Catalog) and writes
data/processed/colorado/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

The page is a CourseLeaf catalog page with two tables that matter:
- the "Recommended Four-Year Plan of Study" (one "sc_plangrid" table, eight terms,
  "Total Credit Hours 128"), tagged by CSS class like Texas A&M's grid (plangridyear,
  plangridterm, plangridsum, plangridtotal);
- the requirements list ("sc_courselist"), grouped under area headers ("Computer
  Science Core", "Senior Capstone", "Logic", ...), where alternatives follow a course
  as "or ..." rows (class "orclass").

The plan grid names some courses and leaves the rest as labeled slots ("CSCI Core
course (2 of 5)", "Ethics", "Natural science elective"). Each slot's options are read
from the matching block of the requirements list, so they come from the page, not from
this script.

Modeling decisions (batch 4, for the user's review):
- A plan course with "( or other approved course )" after its title (CSCI 2824, 2820,
  3022) stays a required course row; the requirements list's alternatives for it go in
  notes, as they are substitutes, not a choice the plan offers.
- Slots whose block lists a few courses of one kind ("Logic", "Ethics", the two
  "Senior Capstone" terms) are elective_slot rows with the block's course codes in
  `options`. The five "CSCI Core course" slots (14 mixed topics) and the "Natural
  science sequence option" (physics, chemistry, or biology) list their options in notes
  instead (spec 03, "a slot with a short list of one kind of option"). A Senior Capstone
  option is a two-course sequence ("CSCI 4308 & CSCI 4318"), so Capstone I lists the
  first course of each sequence and Capstone II the second.
- Humanities/social sciences electives and the college-approved writing course are
  gen_ed; natural science, computer science, and free electives are elective_slot.
- Footnote markers in the grid are <sup> tags; they are removed from labels.

Usage:
    python src/parse_colorado.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("colorado")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Recommended Four-Year Plan of Study, 2026-2027 University Catalog"

YEARS = {"First Year": 1, "Second Year": 2, "Third Year": 3, "Fourth Year": 4}
TERMS = {"Fall Semester": "Fall", "Spring Semester": "Spring"}
# One CU course code: 4 capital letters, a space, 4 digits (e.g. "CSCI 2270").
CODE = re.compile(r"\b([A-Z]{4}) (\d{4})\b")
# The plan's note on three courses that accept substitutes.
OTHER_APPROVED = re.compile(r"\(\s*or other approved course\s*\)")
# Grid footnotes (shown under the grid), condensed into the notes of the slots they mark.
HSS_NOTE = ("CU footnote: chosen from the college-approved humanities and social sciences (HSS) electives; "
            "the college's humanities, social sciences, and writing requirement is 18 credits in all.")
WRITING_NOTE = "CU footnote: chosen from the list of college-approved writing courses."
CS_ELECTIVE_NOTE = ("CU: approved coursework that brings total computer science credit hours to at least 58; "
                    "see the department website for the list.")
NATSCI_NOTE = ("CU: additional natural science electives to reach 17 credits of physics and natural science "
               "with lab.")
FREE_NOTE = "CU: additional coursework to bring the cumulative total to at least 128 credit hours."


# Text of a tag with non-breaking spaces made normal and whitespace collapsed.
def text(tag) -> str:
    """Return a tag's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", tag.get_text(" ").replace("\xa0", " ")).strip()


# Read the requirements list into {area header: [(code cell, title, is_or_row), ...]}.
# An area header row has class "areaheader" (or "areasubheader" for a nested one); course
# rows follow it until the next header. Headers can nest ("Logic & Ethics", then the
# subheader "Logic"), and only the innermost one matters here, so each header or
# subheader simply starts a new block.
def requirement_blocks(soup) -> dict[str, list[tuple[str, str, bool]]]:
    """Return the requirements list grouped by area header."""
    blocks, current = {}, None
    for tr in soup.find("table", class_="sc_courselist").find_all("tr"):
        classes = tr.get("class") or []
        if "areaheader" in classes or "areasubheader" in classes:
            for sup in tr.find_all("sup"):
                sup.decompose()  # "Humanities/Social Sciences/Writing 2" -> without the footnote
            current = text(tr.find("td"))
            blocks[current] = []
            continue
        code_cell = tr.find("td", class_="codecol")
        if current is None or code_cell is None:
            continue  # the table's hidden first row, or a comment row with no code
        title_cell = code_cell.find_next_sibling("td")
        blocks[current].append((text(code_cell), text(title_cell) if title_cell else "", "orclass" in classes))
    return blocks


# The alternatives the requirements list gives for one required course: the "or" rows
# right after its own row, e.g. CSCI 2824 -> MATH 2001, APPM 3170, ECEN 2703.
def alternatives(blocks: dict, code: str) -> list[str]:
    """Return the "or" codes listed under a course in the requirements list."""
    for rows in blocks.values():
        for i, (cell, _, is_or) in enumerate(rows):  # enumerate gives each row's position
            if not is_or and cell == code:
                alts = []
                for later_cell, _, later_or in rows[i + 1:]:
                    if not later_or:
                        break  # the next required course ends this course's alternatives
                    alts.append(later_cell.removeprefix("or ").strip())
                return alts
    return []


# Codes of a block's rows. `which` picks, for "A & B" sequences, the first ("0") or
# second ("1") course; "all" keeps every code. or-rows are included (they are options).
def block_codes(blocks: dict, header: str, which: str = "all") -> list[str]:
    """Return the course codes listed under one area header."""
    codes = []
    for cell, _, _ in blocks[header]:
        found = [f"{s} {n}" for s, n in CODE.findall(cell)]
        if which == "all":
            codes += found
        elif len(found) > int(which):
            codes.append(found[int(which)])
    return list(dict.fromkeys(codes))  # dict.fromkeys drops repeats, keeping order


# A blank row dict with the defaults every row starts from.
def base_row(hours: str) -> dict:
    """Return a row with credits from an hours string like "3"."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": int(hours),
            "credits_max": int(hours), "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": ""}


# Build the row for a labeled slot from its plan label and the requirements list.
def slot_row(label: str, hours: str, marks: set[str], blocks: dict) -> dict:
    """Return the row for a slot label like "CSCI Core course (2 of 5)"."""
    row = base_row(hours)
    low = label.lower()
    if low.startswith("csci core course"):
        n = re.search(r"\((\d) of 5\)", label).group(1)
        # A long, mixed list (HCI, AI, databases, robotics, ...): kept in notes, not options
        # (spec 03, "a slot with a short list of one kind of option").
        row.update(title=f"Computer science core course ({n} of 5)", requirement_type="elective_slot",
                   notes="CU: five courses from the approved Computer Science Core list (15-18 credits): " +
                         ", ".join(block_codes(blocks, "Computer Science Core")) + ".")
    elif low.startswith("csci senior capstone"):
        part = "1" if low.endswith(" ii") else "0"  # Capstone II takes each sequence's second course
        row.update(title=f"Senior capstone {'II' if part == '1' else 'I'}", requirement_type="elective_slot",
                   options="; ".join(block_codes(blocks, "Senior Capstone", part)),
                   notes="CU: one two-semester capstone sequence: " +
                         " | ".join(f"{c.removeprefix('or ')} ({t})" for c, t, _ in blocks["Senior Capstone"]) + ".")
    elif low == "logic (recommmend prior to discrete structures)" or low.startswith("logic"):
        row.update(title="Logic", requirement_type="elective_slot", options="; ".join(block_codes(blocks, "Logic")),
                   notes="CU recommends taking it before Discrete Structures.")
    elif low == "ethics":
        row.update(title="Ethics", requirement_type="elective_slot", options="; ".join(block_codes(blocks, "Ethics")))
    elif low == "natural science sequence option":
        # Physics, chemistry, or biology sequences: a mixed list, so notes only (spec 03).
        row.update(title="Natural science sequence", requirement_type="elective_slot",
                   notes="CU: a two-course sequence with lab after PHYS 1110: " + " | ".join(
                       f"{c.removeprefix('or ')} ({t})" for c, t, _ in blocks["Physics & Natural Science with Lab"][2:]) + ".")
    elif low == "natural science elective":
        row.update(title="Natural science elective", requirement_type="elective_slot", notes=NATSCI_NOTE)
    elif low == "humanities and social sciences elective":
        row.update(title="Humanities and social sciences elective", requirement_type="gen_ed", notes=HSS_NOTE)
    elif low == "college-approved writing course":
        row.update(title="College-approved writing course", requirement_type="gen_ed", notes=WRITING_NOTE)
    elif low == "computer science elective":
        row.update(title="Computer science elective", requirement_type="elective_slot", notes=CS_ELECTIVE_NOTE)
    elif low == "free elective":
        row.update(title="Free elective", requirement_type="elective_slot", notes=FREE_NOTE)
    else:
        raise SystemExit(f"Unknown slot label in the plan grid: {label!r}. Add it to slot_row().")
    if row["options"]:
        subjects = {c.split()[0] for c in row["options"].split("; ")}
        row["subject"] = subjects.pop() if len(subjects) == 1 else ""
    return row


# Walk the plan grid: year and term headings set the placement, sum rows give each
# term's stated hours, and every other row is a course or a slot.
def parse_plan(soup, blocks: dict) -> tuple[pd.DataFrame, dict, str]:
    """Return (rows, {(year, term): stated hours}, stated total)."""
    rows, term_hours, total = [], {}, ""
    year = term = None
    for tr in soup.find("table", class_="sc_plangrid").find_all("tr"):
        classes = tr.get("class") or []  # rows without a class attribute give None
        if "plangridyear" in classes:
            year = YEARS[text(tr)]
        elif "plangridterm" in classes:
            term = TERMS[text(tr.find("th"))]  # the first term row also holds the hours header
        elif "plangridsum" in classes:
            term_hours[(year, term)] = text(tr.find("td", class_="hourscol"))
        elif "plangridtotal" in classes:
            total = text(tr.find("td", class_="hourscol"))
        else:
            marks = {text(s) for s in tr.find_all("sup")}
            for sup in tr.find_all("sup"):
                sup.decompose()  # drop footnote markers before reading labels
            hours = text(tr.find("td", class_="hourscol"))
            code_cell = tr.find("td", class_="codecol")
            label = text(code_cell) if code_cell else text(tr.find("td"))
            m = CODE.fullmatch(label)
            if m:
                title = text(code_cell.find_next_sibling("td"))
                row = base_row(hours)
                row.update(course_code=label, subject=m.group(1), number=m.group(2),
                           title=OTHER_APPROVED.sub("", title).strip())
                if OTHER_APPROVED.search(title):
                    alts = alternatives(blocks, label)
                    row["notes"] = ("Plan: 'or other approved course'. The requirements list accepts "
                                    f"{', '.join(alts)}.")
            else:
                row = slot_row(label, hours, marks, blocks)
            row.update(orig_year=year, orig_term=term)
            rows.append(row)
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, term_hours, total


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, term_hours: dict, total: str) -> list[str]:
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
    core = df["title"].str.startswith("Computer science core course").sum()
    if core != 5:
        failures.append(f"{core} computer science core slots, the plan has five ('1 of 5' ... '5 of 5').")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page = text(soup)
    if SCHOOL.college not in page:
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(path)}.")
    if "2026-2027 University Catalog" not in page:
        raise SystemExit(f"'2026-2027 University Catalog' not found on {rel(path)}; check the catalog year.")
    blocks = requirement_blocks(soup)
    df, term_hours, total = parse_plan(soup, blocks)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (plan states {total})")
    failures = check(df, term_hours, total)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All batch 4 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
