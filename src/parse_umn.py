"""Parse Minnesota's CS BS four-year plan into one row per course or requirement slot.

Minnesota's school-specific plan parser (step 13, batch 2). Reads the newest saved
four-year plan page (data/raw/umn/*_cs-four-year-plan.html) and the catalog program
page (data/raw/umn/*_cs-bs-program.html), and writes data/processed/umn/plan_parsed.csv
with the columns in common.PARSED_COLUMNS.

The plan page is plain HTML: a div per year ("plan-year-freshman", h2 "Freshman
Year"), a div per semester ("plan-semester-fall", h3 "Fall Semester"), and one <ul>
whose <li> items read like "◊ Math 1371 Calculus I (placement or prereq) [4cr]": an
optional symbol (◊ = required for admission to the major, + and ± point to legend
notes), a code written in mixed case ("CSci 2011"), a short title, prerequisites in
<em>, and credits in brackets ("[4cr]" or "[3 or 4cr]"). The plan states no semester
or plan totals.

The catalog program page (Coursedog) embeds the program's data as JSON in a
<script id="__NUXT_DATA__"> tag, in Nuxt's "devalue" format: one flat JSON array in
which objects refer to other entries by index. nuxt_value() resolves those references.
From it the parser reads the degree credit minimum (cdProgramCreditsDegreeMin) and the
credits of the "Second Science" rule. Course titles come from the saved course pages
(data/raw/umn/courses/), which embed each course's record the same way.

Modeling decisions (step 13):
- Codes are upper-cased to the catalog's form ("CSci 2011" -> "CSCI 2011").
- Both first-year semesters list "Liberal Education course or Writ 1301": the student
  takes WRIT 1301 (University Writing, a university requirement) in one and a liberal
  education course in the other. The plan doesn't say which, so the two rows are one
  all_in_any_order group (options "WRIT 1301; Liberal Education course"), the rule
  used for Berkeley's ELENG 66/64.
- "Additional Science Requirement± (course specific)" has no credits in the plan; the
  catalog's "Second Science" rule gives 3-4 credits, which the row uses.
- Most slots are "[3 or 4cr]" and the open electives are "If needed to reach 120
  credits", so the rows sum to a range (110-129), which schools.csv records; the parser
  checks that the catalog's 120-credit degree minimum falls inside it.

Usage:
    python src/parse_umn.py
"""

import json
import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("umn")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Computer Science Four-Year Plan (revised 03/2026), College of Science and Engineering"

YEARS = {"Freshman Year": 1, "Sophomore Year": 2, "Junior Year": 3, "Senior Year": 4}
TERMS = {"Fall Semester": "Fall", "Spring Semester": "Spring"}
# A plan code: a subject in any case (Math, CSci, Phys, Stat, Writ, CSE), a space, four
# digits, and an optional suffix letter (W = writing intensive), e.g. "CSci 3081W".
CODE = re.compile(r"\b([A-Z][A-Za-z]{1,4}) (\d{4}[A-Z]?)\b")
# Credits in brackets: "[4cr]" or "[3 or 4cr]".
CREDITS = re.compile(r"\[(\d+)(?: or (\d+))?\s*cr\]")
WRIT_GROUP = "writ-1301-liberal-education"
WRIT_OPTIONS = "WRIT 1301; Liberal Education course"
WRIT_NOTE = ("Both first-year semesters list 'Liberal Education course or Writ 1301': WRIT 1301 (University "
             "Writing, a university requirement) goes in one and a liberal education course in the other, in "
             "either order (all_in_any_order group).")
# Slot labels (symbols and parentheticals removed) -> (title, requirement_type, notes).
SLOTS = {
    "Liberal Education course": ("Liberal Education course", "gen_ed",
        "UMN liberal education: cores (biological sciences, physical sciences, historical perspectives, social "
        "sciences, arts/humanities, literature, mathematical thinking) and four of five themes, including "
        "Race, Power, and Justice in the US."),
    "Additional Science Requirement": ("Additional Science Requirement", "elective_slot",
        "UMN plan legend: may be fulfilled with Chem 1071/65, Phys 1302W, ESci 2201 (fall only, coreq Phys "
        "1301W), Psy 3011 (prereq Psy 1001), or GCD 3022. Credits from the catalog's Second Science rule."),
    "UD Math Oriented Requirement": ("UD Math Oriented Requirement", "elective_slot",
        "UMN plan legend: CSci technical electives plus the upper-division math-oriented requirement must total "
        "at least 23 credits, at least 11 of them CSci courses."),
    "Technical Elective": ("Technical Elective", "elective_slot",
        "UMN plan legend: CSci technical electives plus the upper-division math-oriented requirement must total "
        "at least 23 credits, at least 11 of them CSci courses."),
    "Open Elective": ("Open Elective", "elective_slot",
        "UMN plan: 'If needed to reach 120 credits'."),
}


# Text of an element with whitespace collapsed.
def text(el) -> str:
    """Return an element's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", el.get_text(" ").replace("\xa0", " ")).strip()


# Read a Coursedog page's embedded Nuxt data: the flat JSON array described above.
def nuxt_data(path: Path) -> list:
    """Return the __NUXT_DATA__ array of a saved Coursedog page."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    return json.loads(soup.find("script", id="__NUXT_DATA__").string)


# Resolve one value of a devalue array. Inside objects and lists, integers are indexes
# into the array; this follows them recursively, so the result is plain Python data.
# isinstance(x, bool) is checked first because True/False are also ints in Python.
def nuxt_value(data: list, x):
    """Return x with every index reference into data replaced by the value it points to."""
    if isinstance(x, bool) or not isinstance(x, int):
        return x
    v = data[x]
    if isinstance(v, dict):
        return {k: nuxt_value(data, i) for k, i in v.items()}
    if isinstance(v, list):
        return [nuxt_value(data, i) for i in v]
    return v


# The course record on a saved course page: the one object with both "code" and
# "courseGroupId" keys (e.g. code "CSCI4041", name "Algorithms and Data Structures").
def course_record(path: Path) -> dict:
    """Return the resolved course record of a saved Coursedog course page."""
    data = nuxt_data(path)
    # next() with a default: the first matching object, or None if the page has none.
    raw = next((d for d in data if isinstance(d, dict) and "code" in d and "courseGroupId" in d), None)
    if raw is None:
        raise SystemExit(f"No course record in {rel(path)}.")
    return {k: nuxt_value(data, i) for k, i in raw.items()}


# Program facts from the catalog page: the degree credit minimum and the credit range of
# the "Second Science" rule (the smallest minCredits and largest maxCredits of its
# options). The program record is the object with a cdProgramCreditsDegreeMin key.
def program_facts(path: Path) -> tuple[int, tuple[int, int]]:
    """Return (degree credit minimum, (min, max) credits of the Second Science rule)."""
    data = nuxt_data(path)
    program = next(d for d in data if isinstance(d, dict) and "cdProgramCreditsDegreeMin" in d)
    degree_min = int(nuxt_value(data, program["cdProgramCreditsDegreeMin"]))
    rule = next(d for d in data if isinstance(d, dict) and "subRules" in d
                and nuxt_value(data, d.get("name")) == "Second Science")
    options = nuxt_value(data, rule["subRules"])
    return degree_min, (min(o["minCredits"] for o in options), max(o["maxCredits"] for o in options))


# Titles of the saved course pages, keyed by plan code ("CSCI 4041"). The catalog's code
# has no space ("CSCI4041"), so the space goes back in before the number.
def catalog_titles() -> dict[str, str]:
    """Return {code: catalog title} from data/raw/umn/courses/."""
    titles = {}
    for path in sorted((SCHOOL.raw / "courses").glob("*.html")):
        rec = course_record(path)
        code = re.sub(r"^([A-Z]+)(\d)", r"\1 \2", rec["code"])  # \1 \2: subject, space, first digit
        # longName is the full title; name is a transcript abbreviation ("CSE Calc I").
        titles[code] = rec.get("longName") or rec["name"]
    return titles


# A blank row dict with the defaults every row starts from.
def base_row(lo: int, hi: int) -> dict:
    """Return a required-course row with the given credit range."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": lo, "credits_max": hi,
            "requirement_type": "required", "gened_tag": "", "min_grade": "", "counts_toward_total": True,
            "notes": "", "options": "", "choice_kind": "", "choice_group": ""}


# Turn one <li> into a row. The <em> prerequisite text is removed first; the label is
# what is left before the credits, with the plan's symbols (◊ + ±) stripped.
def parse_item(li, titles: dict, science: tuple[int, int]) -> dict:
    """Return the row for one plan list item."""
    for em in li.find_all("em"):
        em.decompose()  # decompose() deletes the tag and its text from the tree
    full = text(li)
    m = CREDITS.search(full)
    lo, hi = (int(m.group(1)), int(m.group(2) or m.group(1))) if m else science
    label = re.sub(r"[◊+±]", "", CREDITS.split(full)[0]).strip()  # text before the credits, no symbols
    after = CREDITS.split(full)[-1].strip() if m else ""  # e.g. "(required for those admitted ...)"
    row = base_row(lo, hi)
    if label.startswith("Liberal Education course or Writ 1301"):
        row.update(title="Liberal Education course or WRIT 1301", requirement_type="elective_slot",
                   subject="", options=WRIT_OPTIONS, choice_kind="all_in_any_order", choice_group=WRIT_GROUP,
                   notes=WRIT_NOTE)
        return row
    # A slot label, with any parenthetical ("(If needed to reach 23 credits)") set aside.
    base, _, paren = label.partition(" (")
    if base in SLOTS:
        title, rtype, notes = SLOTS[base]
        if paren and base != "Open Elective" and "course specific" not in paren:
            notes = f"UMN plan: '{paren.rstrip(')')}'. " + notes
        row.update(title=title, requirement_type=rtype, notes=notes)
        return row
    cm = CODE.match(label)
    if not cm:
        raise SystemExit(f"Unknown plan item: {full!r}. Add it to SLOTS.")
    code = f"{cm.group(1).upper()} {cm.group(2)}"
    subj, num = code.split()
    row.update(course_code=code, subject=subj, number=num, title=titles.get(code, ""))
    if after:
        row["notes"] = f"UMN plan: '{after.strip('()')}'."
    return row


# Walk the plan: each year div holds two semester divs, each with one list of items.
def parse_plan(soup, titles: dict, science: tuple[int, int]) -> pd.DataFrame:
    """Return the plan rows with original year and term."""
    rows = []
    for year_div in soup.select("div.plan-years-container > div"):
        year = YEARS[text(year_div.find("h2"))]
        for sem_div in year_div.find_all("div", class_=re.compile(r"^plan-semester-(fall|spring)$")):
            term = TERMS[text(sem_div.find("h3"))]
            for li in sem_div.select("div.plan-semester-class-list li"):
                r = parse_item(li, titles, science)
                r.update(orig_year=year, orig_term=term)
                rows.append(r)
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, degree_min: int, admission: list[str]) -> list[str]:
    """Return failed-check messages."""
    failures = []
    low, high = int(df["credits_min"].sum()), int(df["credits_max"].sum())
    if not low <= degree_min <= high:
        failures.append(f"The catalog's {degree_min}-credit minimum is outside the plan's {low}-{high}.")
    if SCHOOL.credits != (low, high):
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the plan rows sum to {low}-{high}.")
    terms = df.groupby(["orig_year", "orig_term"]).ngroups  # number of distinct (year, term) pairs
    if terms != 8:
        failures.append(f"Expected 8 semesters, found {terms}.")
    untitled = df[(df["course_code"] != "") & (df["title"] == "")]["course_code"].tolist()
    failures += [f"No catalog title for {c} (add it to collect_umn.COURSE_IDS)." for c in untitled]
    for code in admission:
        if code not in set(df["course_code"]):
            failures.append(f"Admission course {code} is not in the plan.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    plan_path = SCHOOL.newest(SCHOOL.credits_source)
    program_path = SCHOOL.newest(SCHOOL.college_source)
    soup = BeautifulSoup(plan_path.read_text(encoding="utf-8"), "html.parser")
    if SCHOOL.college not in program_path.read_text(encoding="utf-8"):
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(program_path)}.")
    degree_min, science = program_facts(program_path)
    # "Courses required for admission to this major: Math 1371, Math 1372, ..." in the notes.
    m = re.search(r"Courses required for admission to this major: ([^.<]+)", text(soup))
    admission = [f"{s.upper()} {n}" for s, n in CODE.findall(m.group(1))] if m else []
    if not admission:
        raise SystemExit(f"Admission course list not found on {rel(plan_path)}.")
    df = parse_plan(soup, catalog_titles(), science)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(plan_path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()}-{df['credits_max'].sum()} (catalog degree minimum {degree_min}; "
          f"second science {science[0]}-{science[1]})")
    failures = check(df, degree_min, admission)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 13 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
