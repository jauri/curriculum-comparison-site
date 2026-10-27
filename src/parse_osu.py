"""Parse Ohio State's BS CSE sample schedule into one row per course or requirement slot.

Ohio State's school-specific plan parser (phase 2, step 10). Reads the newest saved July
2025 curriculum sheet (data/raw/osu/*_bs-cse-curriculum-sheet-2025-07.docx, effective
Autumn 2024, Individualized specialization) and writes data/processed/osu/plan_parsed.csv
with the columns in common.PARSED_COLUMNS.

A .docx file is a zip archive; the text lives in word/document.xml, in Word's XML
vocabulary: <w:p> paragraphs, <w:tbl> tables, <w:tr> rows, <w:tc> cells, and <w:t>
text runs. The sample schedule is a heading paragraph per term ("Year 1 Autumn: 16
hours") followed by a two-column table (Course | Hours). The requirement tables (major
core, required non-major courses) sit inside text boxes, so they are found by searching
every <w:tr> in the document.

Modeling decisions (made with the user in step 10; see PROGRESS.md):
- The schedule disagrees with the sheet's own requirements list in three places. The
  requirements list wins (it also matches the 2023 sheet, the official credit hours, and
  the 126 total), and each corrected row says what the schedule printed. See CORRECTIONS.
- "X or Y" choices (CSE 32X1, 34X1, 35X1, 390X, 591X) are ONE elective_slot row each,
  with the option codes in `options`, read from the major core table.
- Ethics: the CSE 2501 (1 hr) + GE Theme path is used; the PHILOS 2338 path is in notes.
- CSE 1223 is in the schedule but not in the 126-hour requirements (students take it
  unless they place out), so counts_toward_total = False.
- The schedule lists codes without titles, so titles and credit hours of named courses
  come from Ohio State's official class-search data (parse_osu_descriptions.py).
- Ohio State's fall term is "Autumn"; it is kept as written in orig_term.

Usage:
    python src/parse_osu.py
"""

import re
import warnings
import zipfile

import pandas as pd
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from common import PARSED_COLUMNS, finish_choices, load_school, rel
from parse_osu_descriptions import load_courses

SCHOOL = load_school("osu")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "CSE curriculum sheet with sample schedule, July 2025 (effective AU24), Individualized option"

# The schedule's term headings, e.g. "Year 3 Spring: 17-18 hours".
TERM_HEADING = re.compile(r"^Year (\d) (Autumn|Spring): ([\d-]+) hours$")
# A schedule cell that is one course: subject (any case, e.g. "Physics"), a 4-digit
# number with an optional decimal variant (".xx"), then anything (e.g. "(need C- or better)").
COURSE = re.compile(r"^([A-Za-z]+) (\d{4})(?:\.\w+)?\b(.*)$")
# Shorthand for a choice, e.g. "CSE 32X1" or "CSE 591X": X stands for any digit.
CHOICE = re.compile(r"^(CSE) (\d*X\d*)\b")
# Course codes in a requirement-table cell such as "CSE 3231 or 3241", "CSE 2501 or
# PHILOS 2338", or "Math 1151, 1172": an optional subject (any case) before each
# number. A number without its own subject takes the previous one.
CODE_LIST = re.compile(r"(?:([A-Za-z]+) )?(\d{4})")

# Schedule text that disagrees with the requirements list -> (corrected code, credits,
# note). Keyed by (year, term, the schedule's cell text).
CORRECTIONS = {
    (1, "Spring", "MATH 1152"): ("MATH 1172", 5,
        "Schedule prints 'MATH 1152 | 3'; the requirements list says Math 1151, 1172 (10 hours), "
        "MATH 1172 is 5 credits, and the term total (15) only adds up with 5. Corrected to MATH 1172, 5 cr."),
    (2, "Autumn", "STAT 3470"): ("STAT 3470", 3,
        "Schedule prints 4 hours; the requirements list and the course itself are 3. Corrected to 3 cr."),
    (3, "Autumn", "ECE 2060"): ("ECE 2360", 3,
        "Schedule prints ECE 2060 a second time (it is already in Year 2 Spring); the requirements "
        "list has ECE 2360 (Electronics for CSE Majors), which is otherwise missing. Corrected to ECE 2360."),
}
# Gen-ed slot labels in the schedule -> table title (the GE category's full name).
GE_SLOTS = {
    "GE-Writing": "GE Foundations: Writing and Information Literacy",
    "GE-SBS": "GE Foundations: Social and Behavioral Sciences",
    "GE-Diversity": "GE Foundations: Race, Ethnicity and Gender Diversity",
    "GE-History": "GE Foundations: Historical and Cultural Studies",
    "GE-Lit/VPA": "GE Foundations: Literary, Visual and Performing Arts",
    "GE-Theme": "GE Theme",
}
GE_THEME_NOTE = ("OSU requires two GE Themes of 4 hours each: Citizenship for a Diverse and Just World, and a "
                 "Theme of the student's choice. The schedule doesn't say which goes where. PHILOS 2338 can also "
                 "count as the Citizenship Theme (see CSE 2501).")
ELECTIVE_SLOTS = {
    "Math or Science Elective": ("Math or Science Elective",
        "OSU: 8 hours of science/math electives from an approved list (see Buckeye Degree Planner)."),
    "Technical Elective": ("Technical Elective",
        "OSU: 17 hours; at least 9 in CSE courses at the 3000 level or higher, at most 8 in approved non-CSE "
        "courses at the 2000 level or higher. In the Individualized option, chosen with an advisor."),
}
NOTES = {
    "CSE 1223": ("Not part of the 126-hour requirements: students take it unless they place out of it "
                 "(CSE 2221's prerequisite), so counts_toward_total = false."),
    "CSE 2501": ("Ethics requirement: the sheet allows CSE 2501 (1 hr) plus a separate 4-hour GE Theme, or PHILOS "
                 "2338 (4 hr), which also counts as the Citizenship Theme, plus a 1-hour free elective. The CSE "
                 "2501 path is used here (decided with the user)."),
    "GENED 1201": "GE Launch Seminar.",
}


# Text of one Word element: the concatenation of its <w:t> text runs. (Word splits text
# into runs wherever formatting changes, so a single word can span several runs.)
def wtext(el) -> str:
    """Return the visible text of a Word XML element, whitespace-collapsed."""
    return re.sub(r"\s+", " ", "".join(t.get_text() for t in el.find_all("w:t"))).strip()


# Load word/document.xml from the .docx zip. BeautifulSoup's built-in html.parser can
# read the XML well enough (tag names like "w:tbl" are kept as is); the warning that it
# is XML is silenced because no XML parser (lxml) is installed on purpose.
def load_docx(path) -> BeautifulSoup:
    """Return the parsed body XML of a .docx file."""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        return BeautifulSoup(xml, "html.parser")


# Expand a requirement cell like "CSE 3231 or 3241" into ["CSE 3231", "CSE 3241"].
def expand_codes(cell: str) -> list[str]:
    """Return full course codes from a requirement-table code cell."""
    codes, subject = [], None
    for subj, num in CODE_LIST.findall(cell):
        # A bare number reuses the last subject seen. The words "and"/"or" before a number
        # ("CSE 2221 and 2231") are connectors, not subjects, so they count as bare.
        subject = subj.upper() if subj and subj.lower() not in ("and", "or") else subject
        codes.append(f"{subject} {num}")
    return codes


# Read every requirement-table row in the document (the tables inside text boxes appear
# twice, once per Word rendering fallback, so rows are de-duplicated by text). Returns
# {code-cell text: (codes, title, hours text)} for rows whose first cell names courses
# (subject in any case: the college table writes "Math 1151, 1172", "Physics 1250").
def requirement_rows(doc) -> dict[str, tuple[list[str], str, str]]:
    """Return requirement rows keyed by their code cell."""
    rows = {}
    for tr in doc.find_all("w:tr"):
        cells = [wtext(tc) for tc in tr.find_all("w:tc")]
        if len(cells) >= 3 and re.match(r"^[A-Za-z]{3,7} \d{4}", cells[0]):
            rows.setdefault(cells[0], (expand_codes(cells[0]), cells[1], cells[2]))
    return rows


# The options of a choice shorthand: the major-core row whose codes all fit the pattern.
# "32X1" becomes the regex 32\d1, so it matches CSE 3231 and 3241.
def choice_options(shorthand: str, reqs: dict) -> tuple[list[str], str]:
    """Return (option codes, option titles text) for a shorthand such as 'CSE 32X1'."""
    pattern = re.compile("^CSE " + shorthand.replace("X", r"\d") + "$")
    for codes, title, _ in reqs.values():
        if len(codes) > 1 and all(pattern.match(c) for c in codes):
            return codes, title
    raise SystemExit(f"No major-core choice matches {shorthand}.")


# Turn one schedule row (course text, hours text) into a row dict.
def parse_cell(year: int, term: str, cell: str, hours: str, reqs: dict, official: dict) -> dict:
    """Parse one sample-schedule row into course/slot fields."""
    row = {"course_code": "", "subject": "", "number": "", "title": "", "requirement_type": "required",
           "gened_tag": "", "min_grade": "", "counts_toward_total": True, "notes": "", "options": ""}
    bracketed = cell.startswith("[")  # "[GE-Theme if not PHILOS 2338]" with hours "[4]"
    cell = cell.strip("[]")
    # Credits: "4", "[4]", or "1 or 4" (the ethics choice; the CSE 2501 path's 1 is used).
    credits = int(re.findall(r"\d+", hours)[0])

    if (m := CHOICE.match(cell)):  # := assigns and tests in one step (Python 3.8+)
        codes, titles = choice_options(m.group(2), reqs)
        row.update(subject="CSE", title=f"{m.group(0)} ({' or '.join(codes)})", requirement_type="elective_slot",
                   options="; ".join(codes),
                   notes="Student chooses one: " + " | ".join(
                       f"{c} {official[c]['title']}" if c in official else f"{c} (not offered in 2026-27)"
                       for c in codes) + ".")
        if "bookend" in cell:
            row["notes"] += " Includes the GE Reflection ('bookend')."
    elif cell.split(" or ")[0].split("-")[0] in GE_SLOTS or cell.startswith("GE-"):
        label = cell.split(" if ")[0]  # "GE-Theme if not PHILOS 2338" -> "GE-Theme"
        row.update(title=GE_SLOTS[label], requirement_type="gen_ed", gened_tag=label)
        if label == "GE-Theme":
            row["notes"] = GE_THEME_NOTE + (" This one is not needed if PHILOS 2338 is taken." if bracketed else "")
    elif cell in ELECTIVE_SLOTS:
        title, note = ELECTIVE_SLOTS[cell]
        row.update(title=title, requirement_type="elective_slot", notes=note)
    elif (m := COURSE.match(cell)):
        code = f"{m.group(1).upper()} {m.group(2)}"  # "Physics 1250" -> "PHYSICS 1250"
        if (fix := CORRECTIONS.get((year, term, code))):
            code, credits, note = fix
            row["notes"] = "Corrected from the sample schedule: " + note
        subj, num = code.split()
        if code not in official:
            raise SystemExit(f"No official data for {code}; run collect_osu_courses.py.")
        row.update(course_code=code, subject=subj, number=num, title=official[code]["title"])
        if "C- or better" in m.group(3):
            row["min_grade"] = "C-"
        if code in NOTES:
            row["notes"] = (row["notes"] + " " + NOTES[code]).strip()
        if code == "CSE 1223":
            row["counts_toward_total"] = False
        if official[code]["credits_min"] != credits:
            raise SystemExit(f"{code}: schedule says {credits} cr, the course is {official[code]['credits_min']}.")
    else:
        raise SystemExit(f"Unrecognized schedule entry: {cell!r}")
    row.update(credits_min=credits, credits_max=credits)
    return row


# Walk the document body in order: a term heading paragraph sets the current term, and
# the next table holds that term's courses. Only top-level elements are walked
# (recursive=False), so tables inside text boxes are ignored here.
def parse_schedule(doc, reqs: dict, official: dict) -> tuple[pd.DataFrame, dict]:
    """Return (rows, {(year, term): stated hours text})."""
    rows, stated, current = [], {}, None
    for el in doc.find("w:body").find_all(["w:p", "w:tbl"], recursive=False):
        if el.name == "w:p" and (m := TERM_HEADING.match(wtext(el))):
            current = (int(m.group(1)), m.group(2))
            stated[current] = m.group(3)
        elif el.name == "w:tbl" and current:
            for tr in el.find_all("w:tr")[1:]:  # [1:] skips the "Course | Hours" header row
                cell, hours = (wtext(tc) for tc in tr.find_all("w:tc"))
                r = parse_cell(*current, cell, hours, reqs, official)  # *current unpacks (year, term)
                r.update(orig_year=current[0], orig_term=current[1], orig_calendar_year="",
                         orig_term_type="academic", is_coop=False)
                rows.append(r)
            current = None  # each heading owns exactly one table
    return pd.DataFrame(rows), stated


# Run the step 10 checks; return failure messages. Term totals that differ from the
# headings are only printed: the headings carry the same typos as the rows (e.g. Year 2
# Autumn says 18 because of the 4-hour STAT 3470).
def check(df: pd.DataFrame, stated: dict, reqs: dict, stated_total: int) -> list[str]:
    """Return failed-check messages."""
    failures = []
    counted = df[df["counts_toward_total"]]
    if counted["credits_min"].sum() != stated_total:
        failures.append(f"Counted credits {counted['credits_min'].sum()} != the sheet's minimum {stated_total}.")
    if SCHOOL.credits != (stated_total, stated_total):
        failures.append(f"schools.csv says {SCHOOL.credits} but the sheet states {stated_total}.")
    if len(stated) != 8:
        failures.append(f"Expected 8 terms, found {len(stated)}.")
    # Every course in the requirement tables must be a row or an option of a choice row.
    # An "X or Y" requirement needs one of its codes (so the ethics alternative, PHILOS
    # 2338, needn't appear); "X and Y" or "X, Y" needs all of them.
    in_plan = set(df["course_code"]) | {c for o in df["options"] if o for c in o.split("; ")}
    for cell, (codes, _, _) in reqs.items():
        ok = any(c in in_plan for c in codes) if " or " in cell else all(c in in_plan for c in codes)
        if not ok:
            failures.append(f"Requirement '{cell}' is not in the schedule.")
    for (y, t), text in stated.items():
        got = df[(df["orig_year"] == y) & (df["orig_term"] == t)]["credits_min"].sum()
        print(f"  Year {y} {t:<6}: heading {text:>5} hours, rows {got} (incl. uncounted)")
    return failures


# Script entry point.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    doc = load_docx(path)
    total = re.search(r"minimum of (\d+) credit hours", wtext(doc))
    reqs = requirement_rows(doc)
    official = load_courses()
    df, stated = parse_schedule(doc, reqs, official)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)
    # The catalog year is the project's 2026-27; the sheet itself is older (user's decision).
    df["notes"] = df["notes"].str.strip()

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    failures = check(df, stated, reqs, int(total.group(1)))
    counted = df[df["counts_toward_total"]]
    print(f"Credits counted: {counted['credits_min'].sum()} (sheet: minimum {total.group(1)}); "
          f"not counted: {', '.join(df.loc[~df['counts_toward_total'], 'course_code'])}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 10 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
