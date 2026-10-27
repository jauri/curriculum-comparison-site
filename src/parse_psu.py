"""Parse Penn State's CS BS suggested academic plan into one row per course or slot.

Penn State's school-specific plan parser (step 13, batch 3). Reads the newest saved
2026-2027 Undergraduate Bulletin page (data/raw/psu/*_bs-cs-bulletin.html) and writes
data/processed/psu/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

The page is a CourseLeaf bulletin page. Its "Suggested Academic Plan" tab holds one
"sc_plangrid" table per campus where the degree can be finished; the first, under the
heading "Computer Science, B.S. at University Park Campus", is the canonical plan.
Unlike UIUC's eight small grids, it is ONE table for all four years with Fall and
Spring side by side: each row has a Fall code cell and hours cell, then a Spring code
cell and hours cell. Rows are tagged by CSS class (plangridyear, plangridterm,
plangridsum for the semester totals, plangridtotal for "Total Credits 127-130").

Plan cells give only codes ("CMPSC 221 *"), not titles, so titles come from the
page's requirement tables ("sc_courselist"), which list every prescribed course with
its title. Footnote marks are in <sup> elements and are read separately:
- "*" = C or better required for the major; "‡" = C or better for General Education.
  Either sets min_grade = C.
- "#" = an Entrance to Major course; "†" = counts for both General Education and the
  degree. Both are recorded in notes.
- "1" and "2" point to the notes under the grid (400-level electives from the CS
  Undergrad Handbook lists; the "department list" general electives).

Modeling decisions (step 13, batch 3):
- "CMPSC 121 or 131", "CMPSC 122 or 132", and "CAS 100A or 100B" are choices: one
  elective_slot row with the option codes in `options`.
- Plan cells written "STAT 318" are listed in the requirements as "STAT/MATH 318"
  (cross-listed); the STAT code is kept and the cross-listing noted.
- Credit ranges ("MATH 220 2-3", "General Education Course 3-4") become credits_min /
  credits_max. The fourth-year "General Education Course (GHW)" rows are 1.5 credits
  each (health and wellness courses are often 1.5 credits), so credits are stored as
  numbers that may have a fractional part.

Usage:
    python src/parse_psu.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("psu")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Suggested Academic Plan, University Park, 2026-2027 Undergraduate Bulletin"
CAMPUS_HEADING = "Computer Science, B.S. at University Park Campus"

YEARS = {"First Year": 1, "Second Year": 2, "Third Year": 3, "Fourth Year": 4}
# A Penn State course code: subject, space, 1-3 digits, optional letter suffix
# ("ENGL 15", "CMPSC 483W", "CAS 100A", "CMPSC 150N").
CODE = re.compile(r"^([A-Z]{2,5}) (\d{1,3}[A-Z]?)\b")
# "CMPSC 121 or 131": a second option written with the number only, same subject.
OR_NUMBER = re.compile(r"^([A-Z]{2,5}) (\d{1,3}[A-Z]?) or (\d{1,3}[A-Z]?)$")
# Hours cell: "3", "1.5", or a range "2-3".
HOURS = re.compile(r"^(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?$")

# Slot labels as the plan writes them (footnote marks removed) -> (title, type, notes).
SLOTS = {
    "General Education Course": ("General Education Course", "gen_ed",
        "Penn State General Education: Foundations (GWS, GQ), Knowledge Domains (GHW, GN, GA, GH, GS), and "
        "Integrative Studies; US and IL cultural diversity courses can count within these."),
    "General Education Course (GHW)": ("General Education Course (Health and Wellness)", "gen_ed",
        "Penn State General Education, Health and Wellness (GHW) domain; the plan places 1.5 credits in each "
        "fourth-year semester."),
    "First-Year Seminar": ("First-Year Seminar", "elective_slot",
        "Penn State: 1 credit of First-Year Seminar, as specified by the college's First-Year Engagement Plan."),
    "Natural Science (GN) Elective": ("Natural Science (GN) Elective", "elective_slot",
        "Penn State: 2-3 credits from PHYS 213, PHYS 214, or the approved list of natural science courses "
        "(Supporting Courses and Related Areas)."),
    "CMPSC/CMPEN 400-Level Elective": ("CMPSC/CMPEN 400-Level Elective", "elective_slot",
        "Penn State: 18 credits chosen from a list of 400-level CMPSC, CMPEN, and EE courses (networks, "
        "architecture, databases, AI, security, numerical methods, graphics, theory, compilers, operating "
        "systems, and others); plan note 1: lists in the Computer Science Undergrad Handbook."),
    "General Elective (Department List)": ("General Elective (Department List)", "elective_slot",
        "Penn State: 6 credits from the department list; plan note 2: may include ROTC credits, co-op "
        "credits, and other credits specified in the Computer Science Undergrad Handbook."),
}
MARK_NOTES = {"#": "Entrance to Major requirement.", "†": "Satisfies both General Education and a degree requirement."}


# Text of an element with non-breaking spaces made normal and whitespace collapsed.
def text(el) -> str:
    """Return an element's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", el.get_text(" ").replace("\xa0", " ")).strip()


# Titles of the prescribed courses, from the requirement tables. A code cell may be
# cross-listed ("STAT/MATH 318"): both "STAT 318" and "MATH 318" get the title, and the
# cross-listing is remembered for notes. Alternatives ("orclass" rows, "or CMPSC 131")
# are read too, without the leading "or", since the plan offers some of them as choices.
def course_titles(soup) -> tuple[dict, dict]:
    """Return ({code: title}, {code: cross-listed form}) from the sc_courselist tables."""
    titles, cross = {}, {}
    for table in soup.find_all("table", class_="sc_courselist"):
        for tr in table.find_all("tr"):
            cells = tr.find_all("td")
            if len(cells) < 2:
                continue
            # "STAT/MATH 318" -> subjects ["STAT", "MATH"], number "318"
            m = re.fullmatch(r"([A-Z]{2,5}(?:/[A-Z]{2,5})*) (\d{1,3}[A-Z]?)", text(cells[0]).removeprefix("or "))
            if not m:
                continue
            for subj in m.group(1).split("/"):
                titles[f"{subj} {m.group(2)}"] = text(cells[1])
                if "/" in m.group(1):
                    cross[f"{subj} {m.group(2)}"] = m.group(0)
    return titles, cross


# Turn one plan cell (code cell + hours cell) into a row. The <sup> marks are read
# first and removed, so the remaining text is a code, a "CODE or NUMBER" choice, or a
# slot label.
def parse_cell(cell, hours_text: str, titles: dict, cross: dict) -> dict:
    """Return the row for one plan-grid cell."""
    marks = "".join(text(sup) for sup in cell.find_all("sup"))
    for sup in cell.find_all("sup"):
        sup.decompose()  # remove the marks from the tree so text() no longer sees them
    label = text(cell)
    h = HOURS.match(hours_text)
    lo, hi = float(h.group(1)), float(h.group(2) or h.group(1))
    notes = [MARK_NOTES[m] for m in MARK_NOTES if m in marks]
    row = {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": lo, "credits_max": hi,
           "requirement_type": "required", "gened_tag": "", "min_grade": "C" if set(marks) & {"*", "‡"} else "",
           "counts_toward_total": True, "notes": "", "options": ""}
    # A General Education designation in parentheses after a code: "MATH 141 (GQ)".
    tag = re.search(r"\((G[A-Z]{1,2})\)$", label)
    if tag and CODE.match(label):
        row["gened_tag"] = tag.group(1)
        label = label[: tag.start()].strip()
    pair = OR_NUMBER.match(label)
    if pair:
        subj, a, b = pair.groups()
        codes = [f"{subj} {a}", f"{subj} {b}"]
        row.update(subject=subj, title=f"{' or '.join(codes)} ({titles[codes[0]]})",
                   requirement_type="elective_slot", options="; ".join(codes),
                   notes=" ".join([f"Student chooses one: {' | '.join(titles[c] for c in codes)}."] + notes))
        return row
    m = CODE.match(label)
    if m and label == m.group(0):
        code = m.group(0)
        if code not in titles:
            raise SystemExit(f"Plan course {code} is not in the requirement tables; add its title.")
        if code in cross:
            notes.append(f"Cross-listed as {cross[code]}.")
        row.update(course_code=code, subject=m.group(1), number=m.group(2), title=titles[code],
                   notes=" ".join(notes))
        return row
    if label not in SLOTS:
        raise SystemExit(f"Unknown slot label in the plan grid: {label!r}. Add it to SLOTS.")
    title, rtype, slot_notes = SLOTS[label]
    row.update(title=title, requirement_type=rtype, notes=slot_notes)
    if "GHW" in label:
        row["gened_tag"] = "GHW"
    return row


# Walk the University Park grid row by row. A plangridyear row sets the year; each
# ordinary row holds up to two cells (Fall, then Spring); a plangridsum row states the
# two semesters' totals (a single number or a range like "16-17").
def parse_plan(grid, titles: dict, cross: dict) -> tuple[pd.DataFrame, dict, str]:
    """Return (rows, {(year, term): stated "lo-hi" text}, stated total text)."""
    rows, term_hours, year, total = [], {}, None, ""
    for tr in grid.find_all("tr"):
        classes = tr.get("class") or []
        if "plangridyear" in classes:
            year = YEARS[text(tr)]
        elif "plangridterm" in classes:
            continue  # the "Fall Credits Spring Credits" header row
        elif "plangridsum" in classes:
            sums = [text(td) for td in tr.find_all("td", class_="hourscol")]
            term_hours[(year, "Fall")], term_hours[(year, "Spring")] = sums
        elif "plangridtotal" in classes:
            total = text(tr).removeprefix("Total Credits").strip()
        else:
            cells = tr.find_all("td")
            # zip(cells[0::2], cells[1::2]) pairs each code cell with the hours cell after it.
            for (code_cell, hours_cell), term in zip(zip(cells[0::2], cells[1::2]), ["Fall", "Spring"]):
                if not text(code_cell):
                    continue  # an empty cell when one semester has fewer rows
                r = parse_cell(code_cell, text(hours_cell), titles, cross)
                r.update(orig_year=year, orig_term=term)
                rows.append(r)
    df = pd.DataFrame(rows)
    # Write whole numbers as integers ("3", not "3.0") like every other school's table,
    # and keep the fractional ones ("1.5").
    for col in ["credits_min", "credits_max"]:
        # A plain list in an object Series: map() would let pandas coerce the ints back to floats.
        df[col] = pd.Series([int(x) if x == int(x) else x for x in df[col]], index=df.index, dtype=object)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, term_hours, total


# "16-17" -> (16, 17); "16.5" -> (16.5, 16.5).
def bounds(s: str) -> tuple[float, float]:
    """Return the (low, high) numbers of a credit text."""
    m = HOURS.match(s)
    return float(m.group(1)), float(m.group(2) or m.group(1))


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, term_hours: dict, total: str, titles: dict) -> list[str]:
    """Return failed-check messages."""
    failures = []
    lo, hi = bounds(total)
    got = (df["credits_min"].sum(), df["credits_max"].sum())
    if got != (lo, hi):
        failures.append(f"Credits {got} != the plan's Total Credits {total}.")
    if SCHOOL.credits != (lo, hi):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the plan states {total}.")
    for (y, t), stated in term_hours.items():
        g = df[(df["orig_year"] == y) & (df["orig_term"] == t)]
        if (g["credits_min"].sum(), g["credits_max"].sum()) != bounds(stated):
            failures.append(f"Year {y} {t}: {g['credits_min'].sum()}-{g['credits_max'].sum()} credits, plan says {stated}.")
    if len(term_hours) != 8:
        failures.append(f"Expected 8 semesters, found {len(term_hours)}.")
    # Every prescribed course with a fixed code must appear in the plan (as a course or option).
    in_plan = set(df["course_code"]) | {o for opts in df["options"] if opts for o in opts.split("; ")}
    for code in ["CMPSC 150N", "CMPSC 221", "CMPSC 222", "CMPSC 315", "CMPSC 316", "CMPSC 320", "CMPSC 360",
                 "CMPSC 461", "CMPSC 465", "CMPSC 483W", "ENGL 202C", "PHYS 211", "PHYS 212", "CMPEN 270",
                 "ENGL 15", "MATH 140", "MATH 141", "MATH 220", "MATH 230", "STAT 318", "STAT 319"]:
        if code not in in_plan:
            failures.append(f"Prescribed course {code} is not in the plan.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page = text(soup)
    if SCHOOL.college not in page or "2026-2027 edition" not in page:
        raise SystemExit(f"College '{SCHOOL.college}' or the 2026-2027 edition not found on {rel(path)}.")
    # next() with a default: the first grid whose nearest heading names University Park.
    grid = next((g for g in soup.find_all("table", class_="sc_plangrid")
                 if text(g.find_previous(["h2", "h3"])) == CAMPUS_HEADING), None)
    if grid is None:
        raise SystemExit(f"No plan grid under '{CAMPUS_HEADING}' on {rel(path)}.")
    titles, cross = course_titles(soup)
    df, term_hours, total = parse_plan(grid, titles, cross)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum():g}-{df['credits_max'].sum():g} (Penn State states {total})")
    failures = check(df, term_hours, total, titles)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 13 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
