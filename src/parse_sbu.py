"""Parse Stony Brook's CS BS Sample Course Sequence into one row per course or slot.

Stony Brook's school-specific plan parser (batch 4). Reads the newest saved program page
(data/raw/sbu/*_bs-cs-catalog.html, "Computer Science, BS", Fall 2026 Undergraduate
Catalog, saved through Chrome) and writes data/processed/sbu/plan_parsed.csv with the
columns in common.PARSED_COLUMNS.

The "Sample Course Sequence" is four HTML tables after an <h2> of that name, one per
year (Freshman, Sophomore, Junior, Senior, in that order). Each table shows the fall
semester in its first two columns and the spring in its last two:
    Fall Semester | Credits |  | Spring Semester | Credits
    WRT 101       | 3 credits | | WRT 102 (WRT) | 3 credits
and ends with a "Total" row per semester. Course cells name a code, sometimes with a
choice ("CSE 101 or CSE 103") and Stony Brook Curriculum (SBC) designations in
parentheses ("(TECH)", "(SPK & WRTD)"), which go in `gened_tag`. Other cells are slots
("SBC", "UD Technical Elective 3", "Natural Science Course + Lab").

Modeling decisions (batch 4, for the user's review):
- "First Year Seminar 101" and "102" (1 credit each) are slots titled as written; the
  page names no course code for them.
- "CSE 101 or CSE 103", "AMS 210 or MAT 211", and "CSE 416 or CSE 356" are choice rows.
- The six numbered "UD Technical Elective" slots are the page's six upper-division CSE
  electives; their numbers are dropped from the title, so they share one title and one
  match, like other schools' repeated elective slots.
- "Elective or SBC (SBS+ or HFA+)*" is a free elective slot whose note gives the
  footnote: SBS+ or HFA+ is required for students who take CSE 356 instead of CSE 416.

Usage:
    python src/parse_sbu.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from acalog import clean
from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("sbu")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Sample Course Sequence, Fall 2026 Undergraduate Catalog"
YEAR_WORDS = ["Freshman", "Sophomore", "Junior", "Senior"]
# A course code, "CSE 214" or "AMS 151".
CODE = re.compile(r"\b([A-Z]{3}) (\d{3})\b")
# SBC designations in parentheses after a code: "(TECH)", "(SPK & WRTD)".
SBC_TAG = re.compile(r"\(([A-Z+& ,]+)\)\s*$")
# Slot cells -> (title, requirement_type, notes from the page).
SLOTS = {
    "First Year Seminar 101": ("First Year Seminar 101", "elective_slot",
                               "SBU: first-year seminar (the sequence names no course code)."),
    "First Year Seminar 102": ("First Year Seminar 102", "elective_slot",
                               "SBU: first-year seminar (the sequence names no course code)."),
    "SBC": ("SBC", "gen_ed", "SBU: a Stony Brook Curriculum course (DIV, HUM, SBS, ARTS, USA, or GLO)."),
    "Natural Science Course + Lab": ("Natural Science Course + Lab", "elective_slot",
                                     "SBU: natural science requirement, a lecture with laboratory."),
    "Natural Science": ("Natural Science", "elective_slot", "SBU: natural science requirement."),
    "UD Technical Elective": ("UD Technical Elective", "elective_slot",
                              "SBU: six upper-division technical CSE courses of at least three credits each."),
    "UD Elective": ("UD Elective", "elective_slot", "SBU: an upper-division elective."),
    "Elective": ("Elective", "elective_slot", "SBU: free elective."),
    "Elective or SBC (SBS+ or HFA+)*": ("Elective or SBC (SBS+ or HFA+)", "elective_slot",
                                       "SBU footnote: an SBS+ or HFA+ SBC course is required for students who "
                                       "complete CSE 356 in lieu of CSE 416; otherwise a free elective."),
}


# A blank row dict with the defaults every row starts from.
def base_row(credits: int) -> dict:
    """Return a row with fixed credits."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": credits,
            "credits_max": credits, "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": ""}


# Turn one plan cell ("CSE 214", "CSE 101 or CSE 103 (TECH)", "SBC") into a row.
def cell_row(text: str, credits: int, titles: dict) -> dict:
    """Return the row for one sequence cell."""
    row = base_row(credits)
    tag = SBC_TAG.search(text)
    label = SBC_TAG.sub("", text).strip()
    codes = [f"{s} {n}" for s, n in CODE.findall(label)]
    if codes and label == " or ".join(codes):
        if len(codes) == 1:
            subj, num = codes[0].split()
            row.update(course_code=codes[0], subject=subj, number=num, title=titles.get(codes[0], ""))
        else:
            subjects = {c.split()[0] for c in codes}
            row.update(title=f"{label} ({titles.get(codes[0], '')})", subject=subjects.pop() if len(subjects) == 1 else "",
                       requirement_type="elective_slot", options="; ".join(codes),
                       notes="SBU: choose one: " + " | ".join(f"{c} ({titles.get(c, '')})" for c in codes) + ".")
    else:
        key = re.sub(r" \d$", "", label) if label.startswith("UD Technical Elective") else text
        if key not in SLOTS:
            raise SystemExit(f"Unknown sequence cell: {text!r}. Add it to SLOTS.")
        title, rtype, note = SLOTS[key]
        row.update(title=title, requirement_type=rtype, notes=note)
    if tag:
        row["gened_tag"] = tag.group(1)  # SBC designations the course satisfies
    return row


# Course titles from the saved course entries ("CSE 214 - Data Structures").
def entry_titles() -> dict[str, str]:
    """Return {course code: catalog title} from the saved course entries."""
    from acalog import read_entry
    titles = {}
    for path in sorted((SCHOOL.raw / "courses").glob("*_*.html")):
        entry = read_entry(path)
        if entry:
            titles[f"{entry[0]} {entry[1]}"] = entry[2]
    return titles


# Read the four year tables. Returns the rows and each semester's stated total.
def parse_plan(soup, titles: dict) -> tuple[pd.DataFrame, dict]:
    """Return (rows, {(year, term): stated credits})."""
    h2 = soup.find(lambda t: t.name == "h2" and clean(t.get_text()) == "Sample Course Sequence")
    rows, totals = [], {}
    for year, table in enumerate(h2.find_all_next("table")[:4], start=1):  # enumerate from 1: year number
        for tr in table.find_all("tr")[1:]:  # [1:] skips the header row
            cells = [clean(td.get_text(" ")) for td in tr.find_all(["td", "th"])]
            for term, (label, cr) in (("Fall", cells[0:2]), ("Spring", cells[3:5])):
                if not label:
                    continue
                n = int(re.match(r"\d+", cr).group(0))
                if label.startswith("Total"):
                    totals[(year, term)] = n
                    continue
                row = cell_row(label, n, titles)
                row.update(orig_year=year, orig_term=term)
                rows.append(row)
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, totals


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, totals: dict, sequence_text: str) -> list[str]:
    """Return failed-check messages."""
    failures = []
    got = df["credits_min"].sum()
    if SCHOOL.credits != (got, got):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the sequence sums to {got}.")
    for (y, t), n in totals.items():
        s = df[(df["orig_year"] == y) & (df["orig_term"] == t)]["credits_min"].sum()
        if s != n:
            failures.append(f"Year {y} {t}: {s} credits, sequence says {n}.")
    if len(totals) != 8:
        failures.append(f"Expected 8 semester totals, found {len(totals)}.")
    # The tables are taken in order as Freshman..Senior; the year words must appear in that order.
    positions = [sequence_text.find(w) for w in YEAR_WORDS]
    if -1 in positions or positions != sorted(positions):
        failures.append("The sequence's year labels are not Freshman, Sophomore, Junior, Senior in order.")
    untitled = df[(df["course_code"] != "") & (df["title"] == "")]["course_code"].tolist()
    if untitled:
        failures.append(f"No saved course entry for: {', '.join(untitled)}.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page = clean(soup.get_text(" "))
    for needed in [SCHOOL.college, "Fall 2026 Undergraduate Catalog"]:
        if needed not in page:
            raise SystemExit(f"'{needed}' not found on {rel(path)}.")
    df, totals = parse_plan(soup, entry_titles())
    sequence_text = page[page.find("Sample Course Sequence"):]

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()}")
    failures = check(df, totals, sequence_text)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All batch 4 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
