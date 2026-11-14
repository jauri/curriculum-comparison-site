"""Parse UConn's CS BS common map into one row per course or requirement slot.

UConn's school-specific plan parser (batch 4). Reads the newest saved College of
Engineering map (data/raw/uconn/*_cs-common-map-26-27.pdf, "Computer Science (BS),
Catalog Year 2026-2027", Storrs) and the 2026-2027 catalog program page
(*_bs-cs-catalog.html, saved through Chrome), and writes
data/processed/uconn/plan_parsed.csv with the columns in common.PARSED_COLUMNS.

The map is a one-page PDF with two columns of semesters ("Semester One" on the left,
"Semester Two" on the right, and so on). pdfplumber gives each word with its position,
so words left of the page's middle belong to the odd semester and the rest to the even
one. Words are grouped into lines by their vertical position, then lines into entries:
an entry ends with its credits, "(3 credits)", "(1 credit)", or "(1+ credits)",
optionally followed by "(TOI 6)"; a line without credits continues onto the next line
(long titles wrap). Each semester ends with a total line, "15 credits".

Modeling decisions (batch 4, for the user's review):
- Course rows use the catalog's titles (the map abbreviates, "Funct. Prog. Fund."),
  read from the saved CSE, MATH, ENGR, and ENGL course pages.
- "CSE 3150 ... or CSE 3160 ..." is one elective_slot row with both codes in `options`.
- "Probability & Statistics Course" is an elective_slot with the four options the
  catalog lists (MATH 3160, STAT 3025Q, STAT 3345Q, STAT 3375Q).
- The three "Lab Science (4 credits) (TOI 6)" rows are elective_slot rows: the catalog's
  two-semester chemistry or physics sequence plus one more science course (12 credits).
- "TOI Course" is a gen_ed row (UConn's Common Curriculum "Topics of Inquiry").
- "CSE Elective 3000+ or Concentration Course" and "CSE Elective" are elective_slot rows;
  the catalog's concentration rule is in their notes.
- The last "Free Elective* (1+ credits)" ("as needed to reach total degree credits") is
  counted as 1 credit, which makes the eight semesters sum to the stated 120.

Usage:
    python src/parse_uconn.py
"""

import re

import pandas as pd
import pdfplumber
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("uconn")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Computer Science (BS) common map, Catalog Year 2026-2027 (Storrs), College of Engineering"

SEMESTERS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5, "Six": 6, "Seven": 7, "Eight": 8}
# An entry's credits at its end, with an optional "(TOI 6)" after: "(3 credits)",
# "(1 credit)", "(1+ credits)". Group 1 is the number, group 2 the "+" if any.
CREDITS = re.compile(r"\((\d+)(\+?) credits?\)\s*(?:\(TOI \d+\))?\s*$")
# A UConn course code: 3-4 capital letters, a space, 4 digits, an optional Q or W
# (Q = quantitative, W = writing competency), e.g. "MATH 1131Q", "CSE 4939W".
CODE = re.compile(r"\b([A-Z]{3,4}) (\d{4}[QW]?)\b")
# Slot labels on the map -> (title, requirement_type, notes from the catalog page).
SLOTS = {
    "Lab Science": ("Lab Science", "elective_slot",
                    "UConn: a two-semester chemistry or physics laboratory sequence (8 credits) plus one more "
                    "science course from another department (4 credits). The map tags these rows TOI 6, the "
                    "Common Curriculum topic of inquiry they also satisfy."),
    "TOI Course": ("TOI Course", "gen_ed",
                   "UConn Common Curriculum: a course from the Topics of Inquiry (TOI) areas."),
    "CSE Elective 3000+ or Concentration Course": (
        "CSE Elective 3000+ or Concentration Course", "elective_slot",
        "UConn: a concentration (one required course plus nine elective credits from its list) or, without one, "
        "12 credits of 3000+ level CSE courses beyond the required ones; CSE courses must reach 43 credits."),
    "CSE Elective": ("CSE Elective", "elective_slot",
                     "UConn: additional CSE courses as required to reach 43 credits in CSE courses."),
    "Probability & Statistics Course": ("Probability & Statistics Course", "elective_slot",
                                        "UConn: select one of MATH 3160 Probability, STAT 3025Q Statistical Methods, "
                                        "STAT 3345Q Probability Models for Engineers, STAT 3375Q Introduction to "
                                        "Mathematical Statistics I."),
    "Free Elective": ("Free Elective", "elective_slot", "UConn: elective courses to reach a minimum of 120 credits."),
}
PROB_STAT_OPTIONS = "MATH 3160; STAT 3025Q; STAT 3345Q; STAT 3375Q"


# Group a page's words into text lines per column: {column: [(top, line text), ...]}.
# Words whose tops are within 3 points of each other are one line (pdfplumber reports
# slightly different tops for words on the same baseline).
def column_lines(page) -> dict[int, list[tuple[float, str]]]:
    """Return each column's lines, top to bottom, as (top, text) pairs."""
    mid = page.width / 2
    cols = {0: [], 1: []}
    for w in sorted(page.extract_words(), key=lambda w: (round(w["top"]), w["x0"])):
        col = 0 if w["x0"] < mid else 1
        lines = cols[col]
        if lines and abs(lines[-1][0] - w["top"]) <= 3:
            lines[-1] = (lines[-1][0], lines[-1][1] + " " + w["text"])
        else:
            lines.append((w["top"], w["text"]))
    return cols


# Read every semester's entries and stated total from both columns. A "Semester X"
# heading opens a semester; lines join until one ends with credits; a bare "15 credits"
# (or "13+ credits") line is the semester total.
def read_map(page) -> tuple[dict[int, list[tuple[str, int, bool]]], dict[int, str]]:
    """Return ({semester: [(entry text, credits, is_minimum)]}, {semester: stated total})."""
    entries, totals = {}, {}
    for lines in column_lines(page).values():
        sem, buf = None, ""
        for _, line in lines:
            heads = re.findall(r"Semester (One|Two|Three|Four|Five|Six|Seven|Eight)", line)
            if heads:
                sem, buf = SEMESTERS[heads[0]], ""
                entries.setdefault(sem, [])  # setdefault: create the list the first time only
                continue
            if sem is None:
                continue  # title and note lines above the first semester
            total = re.fullmatch(r"(\d+\+?) credits", line)
            if total:
                totals[sem] = total.group(1)
                sem = None  # anything after the total (footnotes) belongs to no semester
                continue
            buf = f"{buf} {line}".strip()
            m = CREDITS.search(buf)
            if m:
                entries[sem].append((buf[:m.start()].strip(), int(m.group(1)), m.group(2) == "+"))
                buf = ""
    return entries, totals


# Course titles from the saved CourseLeaf subject pages. Each course block carries its
# code in a data-coursecode attribute ("CSE 2050") and its title in a span of class
# "detail-title" ("Data Structures and Object-Oriented Design."), final period dropped.
def catalog_titles() -> dict[str, str]:
    """Return {course code: catalog title} from the saved course pages."""
    titles = {}
    for path in sorted(SCHOOL.raw.glob("*_courses-*.html")):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        for block in soup.select("div.courseblock[data-coursecode]"):  # [attr]: blocks that carry a code
            title = block.select_one(".detail-title")
            if title:
                code = re.sub(r"\s+", " ", block["data-coursecode"].replace("\xa0", " ")).strip()
                titles[code] = re.sub(r"\s+", " ", title.get_text(" ")).strip().rstrip(".")
    return titles


# A blank row dict with the defaults every row starts from.
def base_row(credits: int) -> dict:
    """Return a row with fixed credits."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": credits,
            "credits_max": credits, "requirement_type": "required", "gened_tag": "", "min_grade": "",
            "counts_toward_total": True, "notes": "", "options": ""}


# Build the row for one map entry ("CSE 1010: Intro to Computing for Engineers").
def entry_row(text: str, credits: int, minimum: bool, titles: dict) -> dict:
    """Return the row for one map entry."""
    row = base_row(credits)
    codes = [f"{s} {n}" for s, n in CODE.findall(text)]
    label = text.rstrip("*").strip()  # "Free Elective*" -> "Free Elective"
    if len(codes) == 2 and " or " in text:
        row.update(title=f"{codes[0]} or {codes[1]} ({titles.get(codes[0], '')})", subject=codes[0].split()[0],
                   requirement_type="elective_slot", options="; ".join(codes),
                   notes=f"Student chooses one: {codes[0]} ({titles.get(codes[0], '')}) | "
                         f"{codes[1]} ({titles.get(codes[1], '')}).")
    elif len(codes) == 1 and text.startswith(codes[0]):
        subj, num = codes[0].split()
        row.update(course_code=codes[0], subject=subj, number=num,
                   title=titles.get(codes[0]) or text.split(":", 1)[1].strip())
        if codes[0] not in titles:
            row["notes"] = "Title as abbreviated on the map (course not on a saved catalog page)."
    elif label in SLOTS:
        title, rtype, note = SLOTS[label]
        row.update(title=title, requirement_type=rtype, notes=note)
        if label == "Probability & Statistics Course":
            row["options"] = PROB_STAT_OPTIONS
    else:
        raise SystemExit(f"Unknown map entry: {text!r}. Add it to SLOTS.")
    if minimum:
        row["notes"] = ("Map: '1+ credits, as needed to reach total degree credits'; counted as the "
                        f"{credits} credit that brings the plan to 120. " + row["notes"]).strip()
    return row


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, totals: dict, stated: int) -> list[str]:
    """Return failed-check messages."""
    failures = []
    got = df["credits_min"].sum()
    if got != stated:
        failures.append(f"Credits {got} != the map's Total Credits {stated}.")
    if SCHOOL.credits != (stated, stated):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the map states {stated}.")
    for sem, said in totals.items():
        s = df[df["sem"] == sem]["credits_min"].sum()
        if str(s) != said.rstrip("+"):
            failures.append(f"Semester {sem}: {s} credits, map says {said}.")
    if sorted(totals) != list(range(1, 9)):
        failures.append(f"Expected semesters 1-8, found {sorted(totals)}.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    catalog = SCHOOL.newest(SCHOOL.college_source)
    page_text = re.sub(r"\s+", " ", BeautifulSoup(catalog.read_text(encoding="utf-8"), "html.parser").get_text(" "))
    if "The Computer Science major requires a total of 120 credits" not in page_text:
        raise SystemExit(f"The 120-credit statement was not found on {rel(catalog)}.")
    if SCHOOL.college not in page_text:
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(catalog)}.")
    with pdfplumber.open(path) as pdf:  # "with" closes the file when the block ends
        page = pdf.pages[0]
        text = page.extract_text()
        entries, totals = read_map(page)
    if "Catalog Year 2026-2027" not in text:
        raise SystemExit(f"'Catalog Year 2026-2027' not found on {rel(path)}.")
    stated = int(re.search(r"Total Credits: (\d+)", text).group(1))

    titles = catalog_titles()
    rows = []
    for sem in sorted(entries):
        for entry, credits, minimum in entries[sem]:
            row = entry_row(entry, credits, minimum, titles)
            # Semester k is year ceil(k/2); odd semesters are fall, even ones spring.
            row.update(sem=sem, orig_year=(sem + 1) // 2, orig_term="Fall" if sem % 2 else "Spring")
            rows.append(row)
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    failures = check(df, totals, stated)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()} (map states {stated})")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All batch 4 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
