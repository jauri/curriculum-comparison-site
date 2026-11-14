"""Parse Tennessee's CS BS Academic Map into one row per course or requirement slot.

Tennessee's school-specific plan parser (batch 4). Reads the newest saved program page
(data/raw/utk/*_bs-cs-catalog.html, 2026-2027 Undergraduate Catalog, saved through
Chrome) and writes data/processed/utk/plan_parsed.csv with the columns in
common.PARSED_COLUMNS.

The Academic Map is eight Acalog "core" blocks, <div class="acalog-core"> with an <h2>
"Term 1" ... "Term 8", each a list of <li> items:
- li.acalog-course: a course, "COSC 203 - Data Structures 3 Credit Hours" ("*" after a
  code marks a Volunteer Core course);
- li.acalog-adhoc: a text line, either a choice header ("Select one course:", "Select
  one lecture with lab:", "or Select one pair of courses:"), a connector ("or"), or a
  blank line that ends a group;
- li without a class: an elective line, "3 Computer Science Upper-Division Electives
  6 Credit Hours", where the leading number is a footnote (<sup>).
After each term a separate <div class="custom_leftpad_20"> gives the term's credit
hours ("Credit Hours 14-15") and its uTrack "Milestone Notes". The milestone notes list
courses a student must have finished to stay on track; they are not part of the term's
courses, so they are skipped (the term's stated hours confirm this).

Modeling decisions (batch 4, for the user's review):
- A "Select one course:" group is one elective_slot row with every option's code in
  `options` (most groups are a course and its Honors version). Its credits span the
  options' credits, e.g. MATH 132 (3) or MATH 141 (4) -> 3-4.
- The Term 3 science group adds "or Select one pair of courses" (CHEM 102 + CHEM 103,
  or CHEM 122 + CHEM 123): each pair counts as one option, listed by its lecture code,
  with 4 credits (3 + 1); the pairs are named in notes.
- "Select one lecture with lab: COSC 303 or COSC 308 and COSC 304" is a choice row for
  the lecture (COSC 303 or its Honors version) plus a required row for the lab COSC 304.
- An elective line with N credit hours becomes N/3 rows of 3 credits, so each elective
  course is one row as at other schools ("6 Credit Hours" -> two rows).
- Arts and humanities, social sciences, global citizenship, expanded perspectives, and
  engaged inquiries electives are gen_ed; computer science electives are elective_slot.

Usage:
    python src/parse_utk.py
"""

import re

import pandas as pd
from bs4 import BeautifulSoup

from acalog import clean
from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("utk")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
PLAN = "Academic Map, 2026-2027 Undergraduate Catalog"

# A course item: "COSC 203* - Data Structures 3 Credit Hours". Groups: subject, number,
# title, credits. The "*" (Volunteer Core) is optional; the title is non-greedy so it
# stops before the credits.
COURSE = re.compile(r"^([A-Z]{2,4}) (\d{3})\*? - (.+?) (\d+) Credit Hours")
# An elective line: "Computer Science Upper-Division Electives 6 Credit Hours".
ELECTIVE = re.compile(r"^(.+?) (\d+) [Cc]redit [Hh]ours")
# Elective labels -> (row title, requirement_type, notes from the page's footnotes).
VOL_CORE = "UTK footnote: chosen from the Volunteer Core list."
ELECTIVES = {
    "Computer Science Upper-Division Electives": (
        "Computer Science Upper-Division Elective", "elective_slot",
        "UTK footnote: any 3XX or 4XX COSC or ECE course not already required, as listed on the page."),
    "Arts and Humanities (AH) Electives": ("Arts and Humanities (AH) Elective", "gen_ed", VOL_CORE),
    "Global Citizenship - United States (GCUS) Elective": ("Global Citizenship - United States (GCUS) Elective",
                                                           "gen_ed", VOL_CORE),
    "Global Citizenship - International (GCI) Elective": ("Global Citizenship - International (GCI) Elective",
                                                          "gen_ed", VOL_CORE),
    "Social Sciences Elective": ("Social Sciences Elective", "gen_ed", VOL_CORE),
    "Expanded Perspectives Elective": ("Expanded Perspectives Elective", "gen_ed",
                                       VOL_CORE + " Students are encouraged to choose courses that also meet EI."),
    "Engaged Inquiries (EI) Elective": ("Engaged Inquiries (EI) Elective", "gen_ed",
                                        VOL_CORE + " At least 9 Engaged Inquiries hours in two or more subject areas."),
}


# A blank row dict with the defaults every row starts from.
def base_row(lo: int, hi: int | None = None) -> dict:
    """Return a row with credits lo-hi (hi defaults to lo)."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": lo,
            "credits_max": hi if hi is not None else lo, "requirement_type": "required", "gened_tag": "",
            "min_grade": "", "counts_toward_total": True, "notes": "", "options": ""}


# Read one course <li> into (code, title, credits).
def read_course(li) -> tuple[str, str, int]:
    """Return a course item's code, title, and credit hours."""
    m = COURSE.match(clean(li.get_text(" ")))
    if not m:
        raise SystemExit(f"Unreadable course item: {clean(li.get_text(' '))!r}")
    return f"{m.group(1)} {m.group(2)}", m.group(3), int(m.group(4))


# Split a term's <li> items into groups at the blank adhoc lines. Each group is a list
# of (kind, li) with kind "course", "adhoc" (text line), or "elective".
def groups(core) -> list[list[tuple[str, object]]]:
    """Return the term's items grouped between blank lines."""
    out, cur = [], []
    for li in core.find_all("li"):
        classes = li.get("class") or []
        for sup in li.find_all("sup"):
            sup.decompose()  # footnote numbers ("3 Computer Science ...") are not part of the text
        text = clean(li.get_text(" "))
        if "acalog-adhoc" in classes and not text:
            if cur:
                out.append(cur)
            cur = []
        elif "acalog-course" in classes:
            cur.append(("course", li))
        elif "acalog-adhoc" in classes:
            cur.append(("adhoc", li))
        else:
            # An elective line stands alone: close the current group around it.
            if cur:
                out.append(cur)
            out.append([("elective", li)])
            cur = []
    if cur:
        out.append(cur)
    return out


# Turn one group into rows. A group without a "Select" header is a list of required
# courses; "Select one course" is one choice row; "Select one lecture with lab" is a
# choice row plus a required lab row; an elective line is N/3 slot rows.
def group_rows(group: list) -> list[dict]:
    """Return the plan rows for one group of items."""
    kind, first = group[0]
    if kind == "elective":
        m = ELECTIVE.match(clean(first.get_text(" ")).rstrip(" *").strip())
        label, hours = m.group(1), int(m.group(2))
        title, rtype, note = ELECTIVES[label]
        return [dict(base_row(3), title=title, requirement_type=rtype, notes=note) for _ in range(hours // 3)]
    header = clean(first.get_text(" ")) if kind == "adhoc" else ""
    courses = [read_course(li) for k, li in group if k == "course"]
    if not header.startswith("Select"):
        return [dict(base_row(c), course_code=code, subject=code.split()[0], number=code.split()[1], title=t)
                for code, t, c in courses]
    if header == "Select one lecture with lab:":
        # The last course is the lab (after "and"); the others are the lecture options.
        *lectures, (lab_code, lab_title, lab_cr) = courses
        codes = [c for c, _, _ in lectures]
        choice = dict(base_row(lectures[0][2]), title=f"{' or '.join(codes)} ({lectures[0][1]})",
                      subject=codes[0].split()[0], requirement_type="elective_slot", options="; ".join(codes),
                      notes="UTK: 'Select one lecture with lab': " + " | ".join(f"{c} ({t})" for c, t, _ in lectures)
                            + f", taken with {lab_code}.")
        lab = dict(base_row(lab_cr), course_code=lab_code, subject=lab_code.split()[0],
                   number=lab_code.split()[1], title=lab_title)
        return [choice, lab]
    if header != "Select one course:":
        raise SystemExit(f"Unknown choice header: {header!r}")
    # Options: single courses, then any "Select one pair" pairs (a course item whose
    # text ends in "and" starts a pair with the next course item).
    options, credits, pairs = [], [], []
    items = [(k, li) for k, li in group[1:]]
    i = 0
    while i < len(items):
        k, li = items[i]
        if k == "course":
            code, t, c = read_course(li)
            if clean(li.get_text(" ")).endswith(" and"):
                code2, t2, c2 = read_course(items[i + 1][1])
                options.append(code)
                credits.append(c + c2)
                pairs.append(f"{code} + {code2} ({t} and {t2})")
                i += 2
                continue
            options.append(code)
            credits.append(c)
        i += 1
    titles = [read_course(li)[1] for k, li in items if k == "course"]
    subjects = {o.split()[0] for o in options}
    row = dict(base_row(min(credits), max(credits)), title=f"{' or '.join(options)} ({titles[0]})",
               subject=subjects.pop() if len(subjects) == 1 else "", requirement_type="elective_slot",
               options="; ".join(options))
    row["notes"] = "UTK: select one course." + (f" Pairs count as one option: {' | '.join(pairs)}." if pairs else "")
    if len(options) > 3:
        row["title"] = f"Select one: {', '.join(options)}"
    return [row]


# Walk the eight terms and read each term's stated credit hours.
def parse_plan(soup) -> tuple[pd.DataFrame, dict]:
    """Return (rows, {term: (lo, hi) stated hours})."""
    rows, stated = [], {}
    for k in range(1, 9):
        h2 = soup.find(lambda t: t.name == "h2" and clean(t.get_text()) == f"Term {k}")
        core = h2.find_parent("div", class_="acalog-core")
        for group in groups(core):
            for row in group_rows(group):
                # Term k is year ceil(k/2); odd terms are fall, even ones spring.
                row.update(orig_year=(k + 1) // 2, orig_term="Fall" if k % 2 else "Spring")
                rows.append(row)
        hours = clean(core.find_next_sibling("div").find("h3").get_text(" "))
        lo, _, hi = re.search(r"Credit Hours (\d+(?:-\d+)?)", hours).group(1).partition("-")
        stated[k] = (int(lo), int(hi or lo))
    df = pd.DataFrame(rows)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    return df, stated


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, stated: dict, total: tuple[int, int]) -> list[str]:
    """Return failed-check messages."""
    failures = []
    got = (df["credits_min"].sum(), df["credits_max"].sum())
    if got != total:
        failures.append(f"Credits {got[0]}-{got[1]} != the map's Total Credit Hours {total[0]}-{total[1]}.")
    if SCHOOL.credits != total:
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the map states {total}.")
    for k, (lo, hi) in stated.items():
        t = df[(df["orig_year"] == (k + 1) // 2) & (df["orig_term"] == ("Fall" if k % 2 else "Spring"))]
        if (t["credits_min"].sum(), t["credits_max"].sum()) != (lo, hi):
            failures.append(f"Term {k}: {t['credits_min'].sum()}-{t['credits_max'].sum()} hours, map says {lo}-{hi}.")
    return failures


# Script entry point: parse, add the program columns, check, and write the CSV.
def main() -> None:
    path = SCHOOL.newest(SCHOOL.credits_source)
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    page = clean(soup.get_text(" "))
    for needed in [SCHOOL.college, "2026-2027 Undergraduate Catalog"]:
        if needed not in page:
            raise SystemExit(f"'{needed}' not found on {rel(path)}.")
    m = re.search(r"Total Credit Hours (\d+)-(\d+)", page)
    total = (int(m.group(1)), int(m.group(2)))
    df, stated = parse_plan(soup)

    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()}-{df['credits_max'].sum()} (map states {total[0]}-{total[1]})")
    failures = check(df, stated, total)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All batch 4 parse checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
