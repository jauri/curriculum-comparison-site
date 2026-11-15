"""Parse Vanderbilt's 2025-26 CS Four-Year Roadmap into one row per course or requirement slot.

Vanderbilt's school-specific plan parser (batch 5). Reads the newest saved "Four-Year
Roadmap and Checklist, Computer Science" (data/raw/vanderbilt/*_cs-roadmap-2025-26.pdf),
the 2025-26 curriculum sheets (*_cs-prerequisite-sheets-2025-26.pdf; the options behind
each slot), the 2026-27 catalog's program record (*_cs-major-program.json; the college),
and the saved course records (titles), and writes data/processed/vanderbilt/
plan_parsed.csv with the columns in common.PARSED_COLUMNS. No 2026-27 roadmap is posted,
so the 2025-26 one is used (batch 5; Georgia Tech and UVA precedent).

The roadmap is a one-page PDF with two columns of semesters ("Semester 1" left,
"Semester 2" right, and so on). As in parse_uva.py, pdfplumber's word positions split
each line into its left and right halves at the page's middle. Each entry line is
"(N hours) NAME" and each semester ends with "__ Total: N hours".

Modeling decisions (batch 5, for the user's review):
- "ES 1401-1403" (3 hours) is three one-hour modules taken in one semester (the catalog:
  "ES 1401-1403 must be completed in one semester"), so it becomes three 1-credit rows,
  each with its own catalog description.
- "CS/ECE 2201" and the other cross-listed courses use the CS code (written first).
- "CS/ECE 2281+CS/ECE 2281L" (4 hours) is split into CS 2281 (3) and the lab CS 2281L (1),
  the sheets' "Computer Architecture + Laboratory (4 hours)".
- "Liberal Arts Core – CS 1151" is CS 1151 (Computers and Ethics), which the sheets say
  may count as liberal arts core; "Open Elective – ES 2100W" is ES 2100W (Technical
  Communications), which the roadmap places in an open elective to meet the writing
  component. Both are course rows with notes.
- "Basic Science" (12 hours, three slots) is a lab-science choice slot whose notes list
  the sheets' options and recommendation; "CS Depth", "Computer Science Project",
  "Technical Elective", "Liberal Arts Core", and "Open Elective" are slots whose notes
  quote the sheets. The project slot lists its nine course options.

Usage:
    python src/parse_vanderbilt.py
"""

import json
import re

import pandas as pd
import pdfplumber

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("vanderbilt")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Four-Year Roadmap and Checklist, Computer Science, 2025-26 (Vanderbilt School of Engineering)"

ENTRY = re.compile(r"^\((\d) hours\) (.+)$")  # "(4 hours) MATH 1300"
TOTAL = re.compile(r"^__ Total: (\d+) hours$")  # "__ Total: 14 hours"
HEAD = re.compile(r"^Semester (\d)$")  # "Semester 1"
# A course name in the roadmap: subject, an optional cross-listing ("/ECE"), then the
# number with an optional letter ("MATH 1300", "CS/ECE 3251", "ES 2100W"). The first
# subject is captured, so cross-listed courses get their CS code.
CODE = re.compile(r"^([A-Z]{2,4})(?:/[A-Z]{2,4})? (\d{4}[A-Z]?)$")
PROJECT_OPTIONS = ["CS 3862", "CS 3892", "CS 4239", "CS 4249", "CS 4269", "CS 4279", "CS 4287", "CS 4289", "CS 4359"]
# Slot names -> (title, requirement_type, notes), the notes quoting the 2025-26 sheets.
SLOTS = {
    "Basic Science": ("Basic Science", "elective_slot",
                      "Vanderbilt: 12 hours from BSCI 1100, 1510, 1511, 2218, 2219; CHEM 1601, 1602; EES 1510; "
                      "MSE 1500; PHYS 1601, 1602 (with their labs), including at least one laboratory course. "
                      "Recommended: CHEM 1601 and 1601L; PHYS 1601 and 1602."),
    "CS Depth": ("CS Depth", "elective_slot",
                 "Vanderbilt: 15 hours of CS courses numbered 3000 or higher (except CS 3262), selected ECE courses, "
                 "and at most two of MATH 3320, 3620, 4600, 4620; at most 6 hours from CS 3860 and 3861."),
    "Computer Science Project": ("Computer Science Project", "elective_slot",
                                 "Vanderbilt: 3 hours from CS 3862, 3892, 4239, 4249, 4269, 4279, 4287, 4289, 4359."),
    "Technical Elective": ("Technical Elective", "elective_slot",
                           "Vanderbilt: 6 hours of engineering courses numbered 2000 or higher (with exceptions), or "
                           "Arts and Science courses numbered 2000 or higher on the mathematics and natural science "
                           "(MNS) distribution list."),
    "Liberal Arts Core": ("Liberal Arts Core", "gen_ed",
                          "Vanderbilt: 18 hours of liberal arts core (the School of Engineering's humanities and social "
                          "sciences requirement)."),
    "Open Elective": ("Open Elective", "elective_slot", "Vanderbilt: 18-20 hours of open electives."),
}
NOTES = {
    "CS 1151": "The roadmap lists it as 'Liberal Arts Core – CS 1151': the sheets say it may count as three hours of "
               "liberal arts core or open electives.",
    "ES 2100W": "The roadmap lists it as 'Open Elective – ES 2100W': a W-designated course that meets the writing "
                "component (requirement 12).",
    "MATH 2410": "The sheets allow MATH 2410 or MATH 2600 after MATH 2300 (or the MATH 2500/2501 sequence).",
    "MATH 2820": "The sheets allow MATH 2810, 2820, or 3640 for statistics/probability.",
}


# Course titles from the saved catalog records ("CS2201" -> "CS 2201": title).
def record_titles() -> dict:
    """Return {code: title} from the saved course records."""
    titles = {}
    for path in sorted((SCHOOL.raw / "courses").glob("*_*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        m = re.match(r"^([A-Z]+)(\d{4}[A-Z]?)$", record["__catalogCourseId"])
        if m:
            titles[f"{m.group(1)} {m.group(2)}"] = record["title"]
    return titles


# Group the page's words into lines for each half of the page (parse_uva.py's method).
def half_lines(page) -> list[tuple[str, str]]:
    """Return (left text, right text) for each line, top to bottom."""
    mid = page.width / 2
    lines = []  # [top, left words, right words]
    for w in sorted(page.extract_words(), key=lambda w: (round(w["top"]), w["x0"])):
        if not lines or abs(lines[-1][0] - w["top"]) > 3:  # a new line when the top moves by > 3 points
            lines.append([w["top"], [], []])
        lines[-1][1 if w["x0"] < mid else 2].append(w["text"])
    return [(" ".join(l), " ".join(r)) for _, l, r in lines]


# A blank row with fixed credits.
def base_row(credits: int) -> dict:
    """Return a row with the defaults every row starts from."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": credits,
            "credits_max": credits, "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": ""}


# A course row for one code.
def course_row(code: str, credits: int, titles: dict, note: str = "") -> dict:
    """Return the row for one course code."""
    row = base_row(credits)
    subj, num = code.split()
    row.update(course_code=code, subject=subj, number=num, title=titles.get(code, code),
               notes=note or NOTES.get(code, ""))
    return row


# Turn one roadmap entry into rows (the ES modules and the architecture pair give several).
def entry_rows(hours: int, name: str, titles: dict) -> list[dict]:
    """Return the rows for one '(N hours) NAME' entry."""
    if name == "ES 1401-1403":
        note = "The roadmap's 'ES 1401-1403' (3 hours): three one-hour modules completed in one semester."
        return [course_row(f"ES {n}", 1, titles, note) for n in (1401, 1402, 1403)]
    if name == "CS/ECE 2281+CS/ECE 2281L":
        note = "The roadmap lists 'CS/ECE 2281+CS/ECE 2281L' as one 4-hour line: the course (3) and its laboratory (1)."
        return [course_row("CS 2281", 3, titles, note), course_row("CS 2281L", 1, titles, note)]
    # "Liberal Arts Core – CS 1151", "Open Elective – ES 2100W": the course after the dash.
    name = name.split(" – ")[-1]
    m = CODE.match(name)
    if m:
        return [course_row(f"{m.group(1)} {m.group(2)}", hours, titles)]
    if name not in SLOTS:
        raise SystemExit(f"Unknown roadmap entry: {name!r}")
    title, rtype, note = SLOTS[name]
    row = base_row(hours)
    row.update(title=title, requirement_type=rtype, notes=note)
    if name in ("CS Depth", "Computer Science Project"):
        row["subject"] = "CS"
    if name == "Computer Science Project":
        row["options"] = "; ".join(PROJECT_OPTIONS)
    return [row]


# Walk the roadmap: semester headings open semesters on each side; total lines close them.
def parse_plan(page, titles: dict) -> tuple[pd.DataFrame, dict]:
    """Return (rows, {semester: stated total})."""
    rows, totals = [], {}
    sem = {0: None, 1: None}  # the open semester on the left (0) and right (1) side
    for halves in half_lines(page):
        for side, text in enumerate(halves):
            text = text.strip()
            head, total, entry = HEAD.match(text), TOTAL.match(text), ENTRY.match(text)
            if head:
                sem[side] = int(head.group(1))
            elif total and sem[side]:
                totals[sem[side]] = int(total.group(1))
                sem[side] = None
            elif entry and sem[side]:
                k = sem[side]
                for row in entry_rows(int(entry.group(1)), entry.group(2), titles):
                    # Semester k is year ceil(k/2); odd semesters are fall, even ones spring.
                    row.update(sem=k, orig_year=(k + 1) // 2, orig_term="Fall" if k % 2 else "Spring")
                    rows.append(row)
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, totals


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, totals: dict, stated: int, sheets: str) -> list[str]:
    """Return failed-check messages."""
    failures = []
    got = df["credits_min"].sum()
    if got != stated:
        failures.append(f"Credits {got} != the roadmap's {stated}.")
    if SCHOOL.credits != (stated, stated):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the roadmap states {stated}.")
    for k, n in totals.items():
        s = df[df["sem"] == k]["credits_min"].sum()
        if s != n:
            failures.append(f"Semester {k}: {s} credits, roadmap says {n}.")
    if sorted(totals) != list(range(1, 9)):
        failures.append(f"Expected semesters 1-8, found {sorted(totals)}.")
    # Every Computer Science Core course in the sheets must be in the roadmap.
    core = sheets.split("Computer Science Core", 1)[1].split("Computer Science Depth", 1)[0]
    for subj, num in re.findall(r"(?<![/A-Z])([A-Z]{2,4})(?:/[A-Z]{2,4})? (\d{4})", core):
        if f"{subj} {num}" not in set(df["course_code"]):
            failures.append(f"Core course {subj} {num} is not in the roadmap.")
    # Hours by group match the sheets: 12 basic science, 15 depth, 6 technical, 18 liberal arts core
    # (CS 1151 counts as one of its courses, so 15 in the slots).
    for title, hours in [("Basic Science", 12), ("CS Depth", 15), ("Technical Elective", 6), ("Liberal Arts Core", 15)]:
        s = df[df["title"] == title]["credits_min"].sum()
        if s != hours:
            failures.append(f"{title}: {s} hours, expected {hours}.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    program = json.loads(SCHOOL.newest(SCHOOL.college_source).read_text(encoding="utf-8"))
    if program["groupFilter2"]["name"] != SCHOOL.college or program["code"] != "CSENGBS":
        raise SystemExit(f"College '{SCHOOL.college}' / CSENGBS not in the catalog's program record.")
    with pdfplumber.open(SCHOOL.newest("*_cs-prerequisite-sheets-2025-26.pdf")) as pdf:  # "with" closes the file
        sheets = "\n".join(p.extract_text() for p in pdf.pages)
    with pdfplumber.open(path) as pdf:
        page = pdf.pages[0]
        text = page.extract_text()
        stated = int(re.search(r"(\d+) hours", text).group(1))  # "120 hours" under the title
        df, totals = parse_plan(page, record_titles())
    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    failures = check(df, totals, stated, sheets)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (roadmap states {stated})")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All batch 5 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
