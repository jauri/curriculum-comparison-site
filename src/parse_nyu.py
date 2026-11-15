"""Parse NYU Tandon's Computer Science BS sample plan into one row per course or requirement slot.

NYU's school-specific plan parser (batch 5). Reads the newest saved bulletin page
(data/raw/nyu/*_bs-cs-bulletin.html, 2026-2027 NYU Bulletins) and writes
data/processed/nyu/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

The page is a CourseLeaf bulletin page with two tables that matter:
- the "Sample Plan of Study" (one "sc_plangrid" table). Unlike Colorado's grid it has
  no year rows: each "plangridyear" row is one semester ("1st Semester/Term" ...
  "8th Semester/Term"), followed by its course rows and a "plangridsum" row with the
  semester's credits; a "plangridtotal" row gives "Total Credits 128";
- the curriculum list ("sc_courselist"), whose "Science Requirement" block lists the
  six science courses the three Science Elective slots choose from.

Footnote markers are <sup> numbers; the footnotes are the numbered paragraphs after
the grid (1: C- grade rule, 2: precalculus placement, 3: science electives, 4: HUSS
electives, 5: CS elective substitutions). They are condensed into row notes below.

Modeling decisions (batch 5, for the user's review):
- Semester n of the grid becomes orig_year (n + 1) // 2, Fall for odd n and Spring
  for even n: the bulletin's plan is for students entering in the fall.
- CS-UY 1114, CS-UY 1134, and CS-UY 2124 get min_grade "C-" (footnote 1).
- The four "Humanities and Social Sciences Elective" slots are gen_ed. The curriculum
  list says one of the four HUSS courses is an ethics course; the plan does not say
  which, so all four carry that note.
- The three "Science Elective" slots are elective_slot rows. Their six options
  (chemistry, biology, physics) are a mixed list chosen three at a time, so they go in
  notes, not `options` (spec 03, "a slot with a short list of one kind of option"; the
  same option set on three "choose" rows would also read as "take them all").
- "CS Elective" and "Free Elective" slots are elective_slot rows.
- EX-UY 1, the 0-credit corequisite of CS-UY 1114, is not in the grid and gets no row
  (like USC's ENGR 495).

Usage:
    python src/parse_nyu.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("nyu")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Sample Plan of Study, Computer Science (BS), 2026-2027 NYU Bulletins (Tandon School of Engineering)"

# "3rd Semester/Term" -> 3. \d+ takes the number; (?:st|nd|rd|th) is the ordinal suffix,
# grouped without capturing.
SEMESTER = re.compile(r"(\d+)(?:st|nd|rd|th) Semester/Term")
# One NYU course code: a subject with a school suffix ("CS-UY", "EXPOS-UA"), a space,
# and a number of one to four digits ("EXPOS-UA 1", "CS-UY 1114").
CODE = re.compile(r"([A-Z]+-U[A-Z]) (\d{1,4})")
# Courses with a minimum grade of C- (grid footnote 1).
C_MINUS = {"CS-UY 1114", "CS-UY 1134", "CS-UY 2124"}
# Grid footnotes, condensed into the notes of the rows they mark.
CS_1114_NOTE = ("NYU: students who take CS-UY 1113 and CS-UY 1121 may count four credits toward the major "
                "in place of CS-UY 1114.")
CALC_NOTE = "NYU: students placed into MA-UY 914 Precalculus for Engineers take it first and defer this course."
HUSS_NOTE = ("NYU: one of the four humanities and social sciences (HUSS) courses must be an ethics course; "
             "see the Tandon General Education Requirements.")
CS_ELECTIVE_NOTE = ("NYU: 18 credits of computer science electives; with the CSE department's approval, some "
                    "closely related EE, math, or other courses may substitute.")
FREE_NOTE = "NYU: 26 credits of free electives in all."


# Text of a tag with non-breaking spaces made normal and whitespace collapsed.
def text(tag) -> str:
    """Return a tag's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", tag.get_text(" ").replace("\xa0", " ")).strip()


# The science courses of the curriculum list's "Science Requirement" block: the rows
# between that area header and the next header, as (code, title) pairs.
def science_options(soup) -> list[tuple[str, str]]:
    """Return the Science Requirement block's (code, title) rows."""
    options, inside = [], False
    for tr in soup.find("table", class_="sc_courselist").find_all("tr"):
        classes = tr.get("class") or []  # rows without a class attribute give None
        if "areaheader" in classes or "areasubheader" in classes:
            inside = text(tr) == "Science Requirement"
            continue
        code_cell = tr.find("td", class_="codecol")
        if inside and code_cell and CODE.fullmatch(text(code_cell)):
            options.append((text(code_cell), text(code_cell.find_next_sibling("td"))))
    return options


# A blank row dict with the defaults every row starts from.
def base_row(hours: str) -> dict:
    """Return a row with credits from an hours string like "4"."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": int(hours),
            "credits_max": int(hours), "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": ""}


# Build the row for a labeled slot from its grid label ("Science Elective").
def slot_row(label: str, hours: str, science: list[tuple[str, str]]) -> dict:
    """Return the row for one slot label of the plan grid."""
    row = base_row(hours)
    if label == "Science Elective":
        row.update(title="Science elective", requirement_type="elective_slot",
                   notes="NYU: three of these natural science courses (9-12 credits): " +
                         ", ".join(f"{c} ({t})" for c, t in science) + ".")
    elif label == "Humanities and Social Sciences Elective":
        row.update(title="Humanities and social sciences elective", requirement_type="gen_ed", notes=HUSS_NOTE)
    elif label == "CS Elective":
        row.update(title="Computer science elective", requirement_type="elective_slot", notes=CS_ELECTIVE_NOTE)
    elif label == "Free Elective":
        row.update(title="Free elective", requirement_type="elective_slot", notes=FREE_NOTE)
    else:
        raise SystemExit(f"Unknown slot label in the plan grid: {label!r}. Add it to slot_row().")
    return row


# Walk the plan grid: semester headings set the placement, sum rows give each
# semester's stated credits, and every other row is a course or a slot.
def parse_plan(soup, science: list[tuple[str, str]]) -> tuple[pd.DataFrame, dict, str]:
    """Return (rows, {semester number: stated credits}, stated total)."""
    rows, term_credits, total = [], {}, ""
    semester = None
    for tr in soup.find("table", class_="sc_plangrid").find_all("tr"):
        classes = tr.get("class") or []
        if "plangridyear" in classes:
            semester = int(SEMESTER.search(text(tr.find("th"))).group(1))
        elif "plangridsum" in classes:
            term_credits[semester] = text(tr.find("td", class_="hourscol"))
        elif "plangridtotal" in classes:
            total = text(tr.find("td", class_="hourscol"))
        else:
            for sup in tr.find_all("sup"):
                sup.decompose()  # drop footnote markers ("Science Elective 3") before reading labels
            hours = text(tr.find("td", class_="hourscol"))
            code_cell = tr.find("td", class_="codecol")
            label = text(code_cell) if code_cell else text(tr.find("td"))
            m = CODE.fullmatch(label)
            if m:
                row = base_row(hours)
                row.update(course_code=label, subject=m.group(1), number=m.group(2),
                           title=text(code_cell.find_next_sibling("td")))
                if label in C_MINUS:
                    row["min_grade"] = "C-"
                if label == "CS-UY 1114":
                    row["notes"] = CS_1114_NOTE
                elif label == "MA-UY 1024":
                    row["notes"] = CALC_NOTE
            else:
                row = slot_row(label, hours, science)
            # (n + 1) // 2: semesters 1-2 are year 1, 3-4 year 2, ...; odd semesters are fall.
            row.update(orig_year=(semester + 1) // 2, orig_term="Fall" if semester % 2 else "Spring")
            row["semester"] = semester  # kept only for the checks below
            rows.append(row)
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, term_credits, total


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, term_credits: dict, total: str, science: list) -> list[str]:
    """Return failed-check messages."""
    failures = []
    got = df["credits_min"].sum()
    if str(got) != total:
        failures.append(f"Credits {got} != the plan's Total Credits {total}.")
    if SCHOOL.credits != (got, got):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the plan sums to {got}.")
    for sem, credits in term_credits.items():
        s = df[df["semester"] == sem]["credits_min"].sum()
        if str(s) != credits:
            failures.append(f"Semester {sem}: {s} credits, page says {credits}.")
    if sorted(term_credits) != list(range(1, 9)):
        failures.append(f"Expected semesters 1-8, found {sorted(term_credits)}.")
    # Slot counts against the curriculum list: 3 science, 4 HUSS (1 ethics + 3), 18 CS
    # elective credits, 26 free elective credits.
    counts = df.groupby("title")["credits_min"].agg(["count", "sum"])  # agg: both per title
    expected = {"Science elective": ("count", 3), "Humanities and social sciences elective": ("count", 4),
                "Computer science elective": ("sum", 18), "Free elective": ("sum", 26)}
    for title, (stat, want) in expected.items():
        if counts.loc[title, stat] != want:
            failures.append(f"'{title}': {stat} {counts.loc[title, stat]}, the curriculum list implies {want}.")
    if len(science) != 6:
        failures.append(f"Found {len(science)} Science Requirement courses, expected 6.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page = text(soup)
    if SCHOOL.college not in page:
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(path)}.")
    if "2026-2027 Bulletins" not in page:
        raise SystemExit(f"'2026-2027 Bulletins' not found on {rel(path)}; check the bulletin year.")
    science = science_options(soup)
    df, term_credits, total = parse_plan(soup, science)
    failures = check(df, term_credits, total, science)

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
