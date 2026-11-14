"""Parse UVA's example BSCS semester outline into one row per course or requirement slot.

UVA's school-specific plan parser (batch 4). Reads the newest saved "Example BSCS
Semester Outline - 2024-2025 Academic Year" (data/raw/uva/*_bscs-example-schedule-
2024-25.pdf, from the CS department's advising site) and the 2026-27 Undergraduate
Record program page (*_bs-cs-record.html, saved through Chrome; college and the 126-
credit total), and writes data/processed/uva/plan_parsed.csv with the columns in
common.PARSED_COLUMNS. The 2026-27 Record has no semester plan, so the 2024-25 outline
is used (decided with the user).

The outline is a one-page PDF with two columns of semesters ("First Semester ... Cr."
on the left, "Second Semester ... Cr." on the right). As in parse_uconn.py, pdfplumber's
word positions split each line into its left and right halves at the page's middle.
Each line is "CODE  Abbreviated title  credits" or "Slot  credits"; each semester ends
with "Total Credits N".

Modeling decisions (batch 4, for the user's review):
- Course rows use the Record's titles (the outline abbreviates, "Discr. Math & Theory 1").
- "CS 111X" (any of CS 1110, 1111, 1112, 1113, the Record's "Introduction to
  Programming" choices) is one choice row.
- "PHYS 1425 & 1429 Intro. Physics I & Lab" (4 credits) is split into PHYS 1425 (3) and
  PHYS 1429 (1), the Record's credits, so the lecture and lab match like other schools'.
- "HSS/UE" (humanities and social sciences, or unrestricted elective) is a gen_ed slot.
- Checked against the current BSCS checklist (bscs-checklist.pdf): the checklist also
  requires APMA 1090 (Calculus I, 3 credits), which the outline omits (it starts with
  APMA 1110 and has one more HSS/UE slot than the checklist's 27 HSS and unrestricted
  credits), and lists PHYS 2415/2419 where the outline uses ECE 2200 (Applied Physics
  II). Both are recorded in notes, not changed.

Usage:
    python src/parse_uva.py
"""

import re

import pandas as pd
import pdfplumber
from bs4 import BeautifulSoup

from acalog import clean, read_entry
from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("uva")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Example BSCS Semester Outline, 2024-2025 Academic Year (UVA CS advising)"

ORDINALS = {"First": 1, "Second": 2, "Third": 3, "Fourth": 4, "Fifth": 5, "Sixth": 6, "Seventh": 7, "Eighth": 8}
# A course line: "CS 2100 Data Structures & Alg. 1 4" or "CS 111X Intro. to Programming 3".
COURSE = re.compile(r"^([A-Z]{2,4}) (\d{3}[\dX])(?: & (\d{4}))? (.+?) (\d)$")
# A slot line: "HSS/UE 3", "CS Elective 3".
SLOT = re.compile(r"^(HSS/UE|Math/Sci Elective|APMA Elective|CS Elective|CS Capstone) (\d)$")
SLOTS = {
    "HSS/UE": ("HSS/UE", "gen_ed", "UVA: a humanities and social sciences elective (15 credits) or an unrestricted "
                                   "elective (12 credits)."),
    "Math/Sci Elective": ("Math/Sci Elective", "elective_slot", "UVA: a mathematics or science elective (3 credits)."),
    "APMA Elective": ("APMA Elective", "elective_slot",
                      "UVA: applied mathematics electives beyond the SEAS requirements (9 credits, including APMA 3100)."),
    "CS Elective": ("CS Elective", "elective_slot", "UVA: 15 credits of CS electives."),
    "CS Capstone": ("CS Capstone", "elective_slot",
                    "UVA: a three-credit CS capstone (CS 4971, CS 4980, or CS 4991 plus an extra CS 4000-level course), "
                    "taken with the SEAS senior thesis courses STS 4500 and 4600."),
}
INTRO_OPTIONS = ["CS 1110", "CS 1111", "CS 1112", "CS 1113"]
CAPSTONE_OPTIONS = ["CS 4971", "CS 4980", "CS 4991"]


# Group the page's words into lines for each half of the page.
def half_lines(page) -> list[tuple[str, str]]:
    """Return (left text, right text) for each line, top to bottom."""
    mid = page.width / 2
    lines = []  # [top, left words, right words]
    # x_tolerance=1: this PDF sets words close together, and pdfplumber's default (3 points)
    # merges them ("CS2100", "DataStructures"); 1 point keeps them apart.
    for w in sorted(page.extract_words(x_tolerance=1), key=lambda w: (round(w["top"]), w["x0"])):
        if not lines or abs(lines[-1][0] - w["top"]) > 3:
            lines.append([w["top"], [], []])
        lines[-1][1 if w["x0"] < mid else 2].append(w["text"])
    return [(" ".join(l), " ".join(r)) for _, l, r in lines]


# A blank row dict with the defaults every row starts from.
def base_row(credits: int) -> dict:
    """Return a row with fixed credits."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": credits,
            "credits_max": credits, "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": ""}


# Turn one half-line into rows (a combined lecture & lab line gives two).
def line_rows(text: str, titles: dict, record_credits: dict) -> list[dict]:
    """Return the rows for one outline line."""
    m = COURSE.match(text)
    if m:
        subj, num, lab, short, cr = m.group(1), m.group(2), m.group(3), m.group(4), int(m.group(5))
        if num == "111X":
            row = base_row(cr)
            row.update(title=f"CS 111X ({titles.get('CS 1110', 'Introduction to Programming')})", subject="CS",
                       requirement_type="elective_slot", options="; ".join(INTRO_OPTIONS),
                       notes="UVA: any one of " + " | ".join(f"{c} ({titles.get(c, '')})" for c in INTRO_OPTIONS) + ".")
            return [row]
        codes = [f"{subj} {num}"] + ([f"{subj} {lab}"] if lab else [])
        rows = []
        for code in codes:
            row = base_row(record_credits.get(code, cr) if lab else cr)
            row.update(course_code=code, subject=subj, number=code.split()[1], title=titles.get(code, short))
            if lab:
                row["notes"] = (f"The outline lists '{text}' as one {cr}-credit line; split by the Record's credits.")
            rows.append(row)
        return rows
    m = SLOT.match(text)
    if not m:
        raise SystemExit(f"Unknown outline line: {text!r}")
    title, rtype, note = SLOTS[m.group(1)]
    row = base_row(int(m.group(2)))
    row.update(title=title, requirement_type=rtype, notes=note)
    if title == "CS Capstone":
        row["options"] = "; ".join(CAPSTONE_OPTIONS)
    return [row]


# Titles and credits from the saved Record course entries ("CS 2100 - Data Structures
# and Algorithms 1", body starting "Credits: 4").
def record_courses() -> tuple[dict, dict]:
    """Return ({code: title}, {code: credits}) from the saved entries."""
    titles, credits = {}, {}
    for path in sorted((SCHOOL.raw / "courses").glob("*_*.html")):
        entry = read_entry(path)
        if entry:
            code = f"{entry[0]} {entry[1]}"
            titles[code] = entry[2]
            m = re.search(r"Credits: (\d+)", entry[3])
            if m:
                credits[code] = int(m.group(1))
    return titles, credits


# Walk the outline: semester headings open semesters on each side; total lines close them.
def parse_plan(page, titles: dict, record_credits: dict) -> tuple[pd.DataFrame, dict]:
    """Return (rows, {semester: stated total})."""
    rows, totals = [], {}
    sem = {0: None, 1: None}  # the open semester on the left (0) and right (1) side
    for halves in half_lines(page):
        for side, text in enumerate(halves):  # side 0 = left, 1 = right
            text = text.strip()
            head = re.match(r"(\w+) Semester Cr\.", text)
            total = re.fullmatch(r"Total Credits (\d+)", text)
            if head and head.group(1) in ORDINALS:
                sem[side] = ORDINALS[head.group(1)]
            elif total and sem[side]:
                totals[sem[side]] = int(total.group(1))
                sem[side] = None
            elif text and sem[side]:
                k = sem[side]
                for row in line_rows(text, titles, record_credits):
                    # Semester k is year ceil(k/2); odd semesters are fall, even ones spring.
                    row.update(sem=k, orig_year=(k + 1) // 2, orig_term="Fall" if k % 2 else "Spring")
                    rows.append(row)
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, totals


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, totals: dict, stated: int, checklist: str) -> list[str]:
    """Return failed-check messages."""
    failures = []
    got = df["credits_min"].sum()
    if got != stated:
        failures.append(f"Credits {got} != the Record's {stated}.")
    if SCHOOL.credits != (stated, stated):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the Record states {stated}.")
    for k, n in totals.items():
        s = df[df["sem"] == k]["credits_min"].sum()
        if s != n:
            failures.append(f"Semester {k}: {s} credits, outline says {n}.")
    if sorted(totals) != list(range(1, 9)):
        failures.append(f"Expected semesters 1-8, found {sorted(totals)}.")
    # Every required CS course on the current checklist should be in the 2024-25 outline.
    for code in re.findall(r"\b(CS [23]\d{3})\b", checklist):
        if code not in set(df["course_code"]):
            failures.append(f"{code} is on the current checklist but not in the 2024-25 outline.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest("*_bscs-example-schedule-2024-25.pdf")
    record = SCHOOL.newest(SCHOOL.credits_source)
    page_text = clean(BeautifulSoup(record.read_text(encoding="utf-8"), "html.parser").get_text(" "))
    if SCHOOL.college not in page_text:
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(record)}.")
    stated = int(re.search(r"Total Required Credits: (\d+)", page_text).group(1))
    with pdfplumber.open(SCHOOL.newest("*_bscs-checklist.pdf")) as pdf:  # "with" closes the file afterwards
        checklist = "\n".join(p.extract_text() for p in pdf.pages)
    titles, record_credits = record_courses()
    with pdfplumber.open(path) as pdf:
        if "2024-2025 Academic Year" not in pdf.pages[0].extract_text():
            raise SystemExit(f"'2024-2025 Academic Year' not found on {rel(path)}.")
        df, totals = parse_plan(pdf.pages[0], titles, record_credits)
    # The two differences from the current checklist (see the docstring), on the rows they concern.
    df.loc[df["course_code"] == "APMA 1110", "notes"] = (
        "The current checklist also requires APMA 1090 (Calculus I, 3 credits), which this 2024-25 outline omits; "
        "the outline starts with APMA 1110 and has one more HSS/UE slot.")
    df.loc[df["course_code"] == "ECE 2200", "notes"] = (
        "The outline's 'Applied Physics (PHYS 2)'; the current checklist lists PHYS 2415/2419 (Physics II).")

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    failures = check(df, totals, stated, checklist)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (Record states {stated})")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All batch 4 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
