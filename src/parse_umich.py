"""Parse Michigan's FA26 CS-Eng sample schedule PDF into one row per course or slot.

Michigan's school-specific plan parser (step 13, batch 2). Reads the newest saved
sample schedule (data/raw/umich/*_cs-eng-sample-schedule-fa26.pdf) and writes
data/processed/umich/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

The PDF is a grid, not a list of courses per term: each row is a requirement
("Mathematics 115, 116, and 214"), then its total credits, then eight term columns
holding the credits taken in each term (e.g. 4 | 4 | . | 4). Section rows ("Program
Subjects (26 hours)") have no credits, and the last row ("Total 128 17 17 16 ...")
gives each term's total. pdfplumber's table extraction reads the grid from both pages.

Footnote markers are small superscript digits glued to the text ("Computers6",
"2141"). They are 6-point characters (the body text is 10-point), so they are dropped
before the table is read: page.filter() keeps only characters of at least MIN_SIZE.

Because one grid row can stand for several courses taken in different terms, each row
label is looked up in ROWS, which lists the plan rows the label produces, one for each
filled term cell in term order. The checks make sure every grid row is in ROWS, that
each yields as many plan rows as it has filled cells, that the cells sum to the row's
total, and that the term sums match the Total row.

Modeling decisions (step 13):
- "Physics 140 and Lab 141" (5 credits in one cell) is one row, PHYS 140, with the lab
  in its title and notes; the PDF doesn't split the credits between them.
- "Chemistry [125/126 and 130] or Chemistry [210 and 211]" is a choice between two
  course bundles, so it is one slot row without `options` (an option list of single
  codes would misstate it); the bundles are in notes.
- "Mathematics 215 or 216", the statistics list, and the EECS 496 / EECS 295 list are
  choice rows with `options`. "EECS 203 (or MATH 465/565)" stays the EECS 203 course
  row with the alternatives in notes, as does MATH 214 with footnote 1's alternatives.
- Titles: the bulletin's EECS course guide gives the EECS titles; other courses keep
  the schedule's own wording ("Mathematics 115"), because their official titles are in
  a login-only course guide.

Usage:
    python src/parse_umich.py
"""

import re

import pandas as pd
import pdfplumber
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("umich")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "FA26 CS-Eng Sample Schedule, College of Engineering Bulletin (dated 5.7.26)"
MIN_SIZE = 8  # points; footnote superscripts are 6 pt, body text 10 pt
TERMS = 8

# Per-row items, in term order: (course_code, title, requirement_type, options, notes).
# A code of "" makes a slot row. Titles here are the schedule's wording; EECS titles
# are replaced by the course guide's (see catalog_titles).
ROWS = {
    "Mathematics 115, 116, and 214": [
        ("MATH 115", "Mathematics 115", "required", "", ""),
        ("MATH 116", "Mathematics 116", "required", "", ""),
        ("MATH 214", "Mathematics 214", "required", "",
         "Michigan footnote 1: MATH 214 can alternatively be satisfied by MATH 217, 417, 419, or ROB 101."),
    ],
    "Mathematics 215 or 216": [
        ("", "MATH 215 or MATH 216 (Mathematics 215 or 216)", "elective_slot", "MATH 215; MATH 216",
         "Student chooses one. Michigan footnote 2: if both are taken, MATH 216 can count as a Flexible "
         "Technical Elective."),
    ],
    "Engineering 100, Introduction to Engineering": [
        ("ENGR 100", "Introduction to Engineering", "required", "", ""),
    ],
    "Engineering 101, Introduction to Computers": [
        ("ENGR 101", "Introduction to Computers", "required", "",
         "Michigan footnote 6: can also be satisfied by ENGR 151, EECS 180 (AP credit), EECS 183, or ROB 102."),
    ],
    "Chemistry [125/126 and 130] or Chemistry [210 and 211]": [
        ("", "Chemistry", "elective_slot", "",
         "Michigan: Chemistry 125/126 and 130 (general chemistry lab and lecture), or Chemistry 210 and 211."),
    ],
    "Physics 140 and Lab 141": [
        ("PHYS 140", "Physics 140 and Lab 141", "required", "", "Lecture PHYS 140 with lab PHYS 141; 5 credits together."),
    ],
    "Physics 240 and Lab 241": [
        ("PHYS 240", "Physics 240 and Lab 241", "required", "", "Lecture PHYS 240 with lab PHYS 241; 5 credits together."),
    ],
    "Intellectual Breadth": [("", "Intellectual Breadth", "gen_ed", "",
                              "Michigan: 16 credits of intellectual breadth (humanities and social sciences).")] * 4,
    "EECS 203, Discrete Mathematics (or MATH 465/565)": [
        ("EECS 203", "Discrete Mathematics", "required", "", "Michigan also accepts MATH 465 or MATH 565."),
    ],
    "EECS 280, Programming and Elementary Data Structures": [
        ("EECS 280", "Programming and Elementary Data Structures", "required", "", ""),
    ],
    "EECS 281, Data Structures and Algorithms": [("EECS 281", "Data Structures and Algorithms", "required", "", "")],
    "EECS 370, Introduction to Computer Organization": [
        ("EECS 370", "Introduction to Computer Organization", "required", "", ""),
    ],
    "STATS 250 or DATASCI 101 or STATS 280 or STATS 412 or STATS 426 or EECS 301 or ECON 451 or TO 301 or IOE 265": [
        ("", "Statistics course", "elective_slot",
         "STATS 250; DATASCI 101; STATS 280; STATS 412; STATS 426; EECS 301; ECON 451; TO 301; IOE 265",
         "Student chooses one statistics or probability course from the listed options."),
    ],
    "EECS 376, Foundations of Computer Science": [("EECS 376", "Foundations of Computer Science", "required", "", "")],
    "TCHNCLCM 300": [("TCHNCLCM 300", "TCHNCLCM 300", "required", "", "")],
    "EECS 496, EECS 295, (or ENGR 499-002, or COMPFOR 111, or CSE 543, or COMM 349, or approved Special Topics sections)": [
        ("", "EECS 496 or EECS 295 (or approved alternatives)", "elective_slot",
         "EECS 496; EECS 295; ENGR 499; COMPFOR 111; CSE 543; COMM 349",
         "Student chooses one: EECS 496, EECS 295, ENGR 499-002, COMPFOR 111, CSE 543, COMM 349, or approved "
         "Special Topics sections (2 credits)."),
    ],
    # The capstone is required, but the course is chosen from a list that is not in the
    # saved PDF, so it is a slot; check_canonical lets it match capstone-design.
    "Approved CS Capstone course": [
        ("", "Approved CS Capstone course", "elective_slot", "",
         "Michigan footnote 3: from the current list of approved capstone courses. TCHNCLCM 497 is taken in the "
         "same or a later semester."),
    ],
    "TCHNCLCM 497": [("TCHNCLCM 497", "TCHNCLCM 497", "required", "",
                      "Michigan footnote 3: taken in the same or a later semester as the capstone.")],
    "Upper Level CS Technical Electives": [
        ("", "Upper Level CS Technical Electives", "elective_slot", "",
         "Michigan footnote 4: 15 credits, including 12 of ULCS and 3 of Expanded ULCS.")] * 3,
    "Flexible Technical Electives": [
        ("", "Flexible Technical Electives", "elective_slot", "",
         "Michigan footnote 5: 10 credits; at most 4 credits of directed or independent study count.")] * 3,
    "General Electives (16 hours)": [("", "General Electives", "elective_slot", "",
                                      "Michigan: 16 credits of general electives.")] * 4,
}
# Section rows: label -> stated hours, checked against the rows under each.
SECTION = re.compile(r"^(.*) \((\d+) hours\)$")


# Text of a cell: newlines from wrapped lines become spaces.
def clean(cell) -> str:
    """Return a table cell's text on one line (or "" for an empty cell)."""
    return re.sub(r"\s+", " ", cell or "").strip()


# Read the grid from every page: [label, total, t1, ..., t8] per row, with footnote
# superscripts removed. The two header rows ("Total Credits / Terms", "1 ... 8") have
# no label and are skipped.
def read_grid(path) -> list[list[str]]:
    """Return the schedule grid rows as cleaned text cells."""
    rows = []
    with pdfplumber.open(path) as pdf:  # "with" closes the file when the block ends
        for page in pdf.pages:
            # filter() returns a view of the page with only the objects the test keeps;
            # objects without a size (lines, rectangles) are kept so the grid lines remain.
            body = page.filter(lambda o: o.get("size", MIN_SIZE) >= MIN_SIZE)
            for table in body.extract_tables():
                rows += [[clean(c) for c in r] for r in table if clean(r[0])]
    return rows


# Titles from the bulletin's EECS course guide: "EECS 280. Programming and Elementary
# Data Structures" in a <strong> at the start of each course paragraph.
def catalog_titles() -> dict[str, str]:
    """Return {code: title} from data/raw/umich/*_courses-*.html."""
    titles = {}
    for path in sorted(SCHOOL.raw.glob("*_courses-*.html")):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        for strong in soup.select("p > strong"):
            m = re.match(r"([A-Z]+) (\d{3})\. (.+)", clean(strong.get_text(" ")))
            if m:
                titles[f"{m.group(1)} {m.group(2)}"] = m.group(3).strip()
    return titles


# Build the plan rows and collect check failures along the way.
def parse_plan(grid: list[list[str]], titles: dict) -> tuple[pd.DataFrame, list[int], int, list[str]]:
    """Return (rows, stated term totals, stated total, failures)."""
    rows, failures, sections = [], [], []
    term_totals, total = [], None
    for label, credits, *cells in grid:  # *cells collects the eight term cells
        if label == "Total":
            total, term_totals = int(credits), [int(c) for c in cells]
            continue
        sec = SECTION.match(label)
        if sec and label not in ROWS:
            sections.append((sec.group(1), int(sec.group(2)), len(rows)))  # rows before it start at len(rows)
            continue
        if label not in ROWS:
            failures.append(f"Grid row {label!r} is not in ROWS.")
            continue
        filled = [(t + 1, int(c)) for t, c in enumerate(cells) if c]  # (term number, credits)
        items = ROWS[label]
        if len(items) != len(filled):
            failures.append(f"{label!r}: {len(filled)} filled term cells but {len(items)} items in ROWS.")
            continue
        if sum(c for _, c in filled) != int(credits):
            failures.append(f"{label!r}: term cells sum to {sum(c for _, c in filled)}, row says {credits}.")
        if sec:  # "General Electives (16 hours)" is a section and a row at once
            sections.append((sec.group(1), int(sec.group(2)), len(rows)))
        for (term, cr), (code, title, rtype, options, notes) in zip(filled, items):
            subj, _, num = code.partition(" ")
            subjects = {o.split()[0] for o in options.split("; ")} if options else set()
            rows.append({"course_code": code, "subject": subj or (subjects.pop() if len(subjects) == 1 else ""),
                         "number": num, "title": titles.get(code, title), "credits_min": cr, "credits_max": cr,
                         "requirement_type": rtype, "gened_tag": "", "min_grade": "", "counts_toward_total": True,
                         "notes": notes, "options": options, "plan_term": term})
    # Each section's stated hours = the credits of the rows from it to the next section.
    bounds = [s[2] for s in sections[1:]] + [len(rows)]
    for (name, hours, start), end in zip(sections, bounds):
        got = sum(r["credits_min"] for r in rows[start:end])
        if got != hours:
            failures.append(f"Section {name!r}: rows sum to {got}, the schedule says {hours} hours.")
    df = pd.DataFrame(rows)
    # Term k of the eight-term plan: year = ceil(k / 2), odd terms Fall, even Spring.
    df["orig_year"] = (df["plan_term"] + 1) // 2  # // is integer division, so (k + 1) // 2 = ceil(k / 2)
    df["orig_term"] = df["plan_term"].map(lambda k: "Fall" if k % 2 else "Spring")
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df.sort_values("plan_term", kind="stable").drop(columns="plan_term"), term_totals, total, failures


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, term_totals: list[int], total: int) -> list[str]:
    """Return failed-check messages."""
    failures = []
    if df["credits_min"].sum() != total:
        failures.append(f"Credits {df['credits_min'].sum()} != the schedule's Total {total}.")
    if SCHOOL.credits != (total, total):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the schedule states {total}.")
    if len(term_totals) != TERMS:
        failures.append(f"Expected {TERMS} term totals, found {len(term_totals)}.")
    for k, stated in enumerate(term_totals, start=1):
        got = df[(df["orig_year"] == (k + 1) // 2) & (df["orig_term"] == ("Fall" if k % 2 else "Spring"))]["credits_min"].sum()
        if got != stated:
            failures.append(f"Term {k}: {got} credits, the schedule says {stated}.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    program = SCHOOL.newest(SCHOOL.college_source)
    page = clean(BeautifulSoup(program.read_text(encoding="utf-8"), "html.parser").get_text(" "))
    # The EECS page must name the degree; the schedule PDF itself names neither degree nor college.
    if "Bachelor of Science in Engineering (Computer Science)" not in page or SCHOOL.college not in page:
        raise SystemExit(f"Degree or college '{SCHOOL.college}' not found on {rel(program)}.")
    df, term_totals, total, failures = parse_plan(read_grid(path), catalog_titles())

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (schedule states {total}; terms {term_totals})")
    failures += check(df, term_totals, total)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 13 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
