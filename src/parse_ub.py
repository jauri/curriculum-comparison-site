"""Parse Buffalo's CS BS Curricular Plan into one row per course or requirement slot.

Buffalo's school-specific plan parser (batch 4). Reads the newest saved program page
(data/raw/ub/*_bs-cs-catalog.html, "Computer Science BS", 2026-2027 Undergraduate
Catalog, saved through Chrome) and writes data/processed/ub/plan_parsed.csv with the
columns in common.PARSED_COLUMNS.

The "Curricular Plan" is one Acalog core block. Inside it, <p> lines name the year
("YEAR 1") and the term ("Fall Semester"), and each <li> is one plan line:
    CSE 115LLR - Introduction to Computer Science I Credits: 4
    Topic Area 1 Credits: 3
    Pathway Credits: 3 Total Credits: 14
The last line of a term also carries the term's "Total Credits" ("14 or 15" when a line
has a choice). Buffalo writes course codes with a component suffix ("LLR" = lecture,
lab, recitation); acalog.course_key() drops it ("CSE 115"), and the course entries are
keyed the same way.

Slot options come from the requirements list on the same page: "Capstone Requirement
(select one)", the probability/statistics list, and the Topic Area course lists. The
page says the three required Topic Areas are "(1) Theory, (2) Security, and (3)
Artificial Intelligence", so Topic Area 1, 2, and 3 in the plan take those lists.

Modeling decisions (batch 4, for the user's review):
- Both first-year terms read "ENG 105LEC - Writing and Rhetoric Credits: 4 OR Pathway
  Credits: 3": students take ENG 105 in one term and a Pathway course in the other. As
  for UIUC's "Composition I or General Education" (step 13 batch 2), ENG 105 is placed
  in the fall and the Pathway course in the spring, which fits both terms' stated
  totals ("14 or 15", "15 or 16").
- "Capstone Requirement" (3-4 credits) is an elective_slot with the four capstone
  options; Topic Areas 1-3 list their area's courses; Specialization 1-2 and "CSE 300 or
  400 Technical Elective" are elective_slot rows without options (any area).
- "Probability/Statistics Course" is 3-4 credits: the plan line says 4, but its listed
  options are 3-4 credits and the term and program totals count 3.
- UBC 399 (UB Curriculum Capstone, 1 credit) is a gen_ed slot row titled "UB Curriculum
  Capstone", with the code in notes: it is the general education program's own
  capstone, not a CS course, and slot rows carry no course code (validate.py).

Usage:
    python src/parse_ub.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from acalog import clean, course_key
from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("ub")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Curricular Plan, 2026-2027 Undergraduate Catalog"

# A course line: "CSE 115LLR - Introduction to Computer Science I Credits: 4".
COURSE = re.compile(r"^([A-Z]{2,4}) (\d{3}[A-Z]*) - (.+?) Credits: (\d+)$")
# A slot line: "Topic Area 1 Credits: 3", "Capstone Requirement Credits: 3-4".
SLOT = re.compile(r"^(.+?) Credits: (\d+)(?:-(\d+))?$")
# A course code inside the requirements text, with its component suffix.
CODE = re.compile(r"\b([A-Z]{2,4}) (\d{3}[A-Z]*) - ")
# Plan slot labels -> (title, requirement_type, requirements-list header or None, notes).
SLOTS = {
    "Pathway": ("Pathway", "gen_ed", None, "UB Curriculum: a Pathway course (general education)."),
    "Pathway Course": ("Pathway", "gen_ed", None, "UB Curriculum: a Pathway course (general education)."),
    "Scientific Literacy Inquiry 1": ("Scientific Literacy and Inquiry 1", "elective_slot", None,
                                      "UB: Science Sequence, at least 7 credits with one credit of lab, from the "
                                      "page's list (biology, chemistry, physics, and others)."),
    "Scientific Literacy and Inquiry 2": ("Scientific Literacy and Inquiry 2", "elective_slot", None,
                                          "UB: second course of the Science Sequence."),
    "Scientific Literacy and Inquiry Lab": ("Scientific Literacy and Inquiry Lab", "elective_slot", None,
                                            "UB: the Science Sequence's laboratory credit, in the same subject as a lecture."),
    "Probability/Statistics Course": ("Probability/Statistics Course", "elective_slot",
                                      "One calculus-based probability or statistics course",
                                      "UB: one calculus-based probability or statistics course."),
    "Topic Area 1": ("Topic Area 1 (Theory)", "elective_slot", "Theory Area Courses",
                     "UB: one course from the Theory area list (required Topic Area 1)."),
    "Topic Area 2": ("Topic Area 2 (Security)", "elective_slot", "Security Area Courses",
                     "UB: one course from the Security area list (required Topic Area 2)."),
    "Topic Area 3": ("Topic Area 3 (Artificial Intelligence)", "elective_slot", "Artificial Intelligence Area Courses",
                     "UB: one course from the Artificial Intelligence area list (required Topic Area 3)."),
    "CSE 300 or 400 Technical Elective": ("CSE 300 or 400 Technical Elective", "elective_slot", None,
                                          "UB: a 3- or 4-credit 300- or 400-level CSE course not otherwise applied "
                                          "(the general upper-level CSE course of the six CSE electives)."),
    "Specialization 1": ("Specialization 1", "elective_slot", None,
                         "UB: two courses from one Topic Area (Theory, Hardware Systems and Networking, AI, Software "
                         "Systems, Security, or Experiential Learning and Research)."),
    "Specialization 2": ("Specialization 2", "elective_slot", None, "UB: the second Specialization Area course."),
    "Math or Science Elective": ("Math or Science Elective", "elective_slot", None,
                                 "UB: one additional math or science course (3 credits minimum) from the page's list."),
    "Capstone Requirement": ("Capstone Requirement", "elective_slot", "Capstone Requirement (select one)",
                             "UB: select one capstone course."),
    "Elective": ("Elective", "elective_slot", None, "UB: elective courses to reach 120 credits."),
}
# The requirements-list headers, in page order, so a list's text runs up to the next one.
HEADERS = ["Capstone Requirement (select one)", "One calculus-based probability or statistics course",
           "Six CSE Electives", "Theory Area Courses", "Hardware Systems and Networking Area Courses",
           "Artificial Intelligence Area Courses", "Software Systems Area Courses", "Security Area Courses",
           "Experiential Learning and Research Area Courses", "Science Sequence"]
ENG_OR_PATHWAY = "ENG 105LEC - Writing and Rhetoric Credits: 4 OR Pathway Credits: 3"


# The course codes listed under one requirements header (up to the next header).
def listed_codes(page: str, header: str) -> list[str]:
    """Return the suffix-free codes in one requirements list."""
    start = page.index(header)
    ends = [page.find(h, start + len(header)) for h in HEADERS if page.find(h, start + len(header)) > 0]
    chunk = page[start:min(ends)] if ends else page[start:]
    return list(dict.fromkeys(course_key(s, n, True) for s, n in CODE.findall(chunk)))  # drop repeats, keep order


# A blank row dict with the defaults every row starts from.
def base_row(lo: int, hi: int | None = None) -> dict:
    """Return a row with credits lo-hi (hi defaults to lo)."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": lo,
            "credits_max": hi if hi is not None else lo, "requirement_type": "required", "gened_tag": "",
            "min_grade": "", "counts_toward_total": True, "notes": "", "options": ""}


# Turn one plan line into a row.
def line_row(line: str, page: str) -> dict:
    """Return the row for one plan line (course or slot)."""
    m = COURSE.match(line)
    if m:
        code = course_key(m.group(1), m.group(2), True)
        row = base_row(int(m.group(4)))
        row.update(course_code=code, subject=m.group(1), number=code.split()[1], title=m.group(3))
        if code == "UBC 399":
            # A general education requirement, not a CS course: kept as a gen_ed slot (slots
            # carry no course code), with the code in notes.
            row.update(course_code="", subject="", number="", title="UB Curriculum Capstone", requirement_type="gen_ed",
                       notes="UB: UBC 399 UB Curriculum Capstone, the general education program's own 1-credit capstone.")
        return row
    m = SLOT.match(line)
    label = m.group(1).replace("​", "").strip() if m else ""  # zero-width spaces appear before some labels
    if label not in SLOTS:
        raise SystemExit(f"Unknown plan line: {line!r}. Add it to SLOTS.")
    title, rtype, header, note = SLOTS[label]
    row = base_row(int(m.group(2)), int(m.group(3)) if m.group(3) else None)
    row.update(title=title, requirement_type=rtype, notes=note)
    if label == "Probability/Statistics Course":
        # The plan line says 4 credits, but its options are 3-4 (CE 305 and CIE 308 are 3), and
        # the term's stated total (17) and the 120-credit program total both need 3.
        row.update(credits_min=3, credits_max=4,
                   notes=note + " The plan line says 4 credits; the options are 3-4, and Year 3 Fall's stated "
                                "total of 17 counts 3.")
    if header:
        codes = listed_codes(page, header)
        row["options"] = "; ".join(codes)
        subjects = {c.split()[0] for c in codes}
        row["subject"] = subjects.pop() if len(subjects) == 1 else ""
    return row


# Walk the Curricular Plan block: <p> lines set the year and term; <li> lines are rows.
def parse_plan(core, page: str) -> tuple[pd.DataFrame, dict, int]:
    """Return (rows, {(year, term): stated total text}, stated program total)."""
    rows, totals, year, term, program_total = [], {}, None, None, None
    for el in core.find_all(["p", "li"]):
        text = clean(el.get_text(" ")).replace("​", "").strip()
        if el.name == "p":
            ym = re.fullmatch(r"YEAR (\d)", text)
            tm = re.fullmatch(r"(Fall|Spring) Semester", text)
            pm = re.fullmatch(r"TOTAL CREDITS REQUIRED: (\d+)", text)
            if ym:
                year = int(ym.group(1))
            elif tm:
                term = tm.group(1)
            elif pm:
                program_total = int(pm.group(1))
            continue
        line, _, total = text.partition(" Total Credits: ")
        if total:
            totals[(year, term)] = total
        if line == ENG_OR_PATHWAY:
            # ENG 105 in the fall, a Pathway course in the spring (see the docstring).
            line = ("ENG 105LEC - Writing and Rhetoric Credits: 4" if term == "Fall" else "Pathway Credits: 3")
            row = line_row(line, page)
            row["notes"] = ("UB: both first-year terms read 'ENG 105 (4) OR Pathway (3)'; students take one of each, "
                            "so ENG 105 is placed in the fall and the Pathway course in the spring. " + row["notes"])
        else:
            row = line_row(line, page)
        row.update(orig_year=year, orig_term=term)
        rows.append(row)
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, totals, program_total


# Does a term's credit range overlap a stated total like "14 or 15" (or "17")? Overlap,
# not containment, because a row's range can be wider than the plan's own count (the
# probability/statistics slot is 3-4 where the term total counts 3).
def fits(lo: int, hi: int, stated: str) -> bool:
    """Return True if the row sums can agree with a stated total."""
    nums = [int(n) for n in re.findall(r"\d+", stated)]
    return lo <= max(nums) and hi >= min(nums)


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, totals: dict, stated: int) -> list[str]:
    """Return failed-check messages."""
    failures = []
    lo, hi = df["credits_min"].sum(), df["credits_max"].sum()
    if not lo <= stated <= hi:
        failures.append(f"Credits {lo}-{hi} do not include the plan's 120 required ({stated}).")
    if SCHOOL.credits != (lo, hi):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the rows sum to {lo}-{hi}.")
    for (y, t), said in totals.items():
        g = df[(df["orig_year"] == y) & (df["orig_term"] == t)]
        if not fits(g["credits_min"].sum(), g["credits_max"].sum(), said):
            failures.append(f"Year {y} {t}: {g['credits_min'].sum()}-{g['credits_max'].sum()} credits, plan says {said}.")
    if len(totals) != 8:
        failures.append(f"Expected 8 term totals, found {len(totals)}.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page = clean(soup.get_text(" "))
    for needed in [SCHOOL.college, "2026-2027 Undergraduate Catalog"]:
        if needed not in page:
            raise SystemExit(f"'{needed}' not found on {rel(path)}.")
    heading = soup.find(lambda t: t.name in ("h2", "h3") and clean(t.get_text()) == "Curricular Plan")
    df, totals, stated = parse_plan(heading.find_parent("div", class_="acalog-core"), page)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()}-{df['credits_max'].sum()} (plan requires {stated})")
    failures = check(df, totals, stated)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All batch 4 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
