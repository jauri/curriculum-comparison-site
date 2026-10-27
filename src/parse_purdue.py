"""Parse Purdue's CS BS plan of study into one row per course or requirement slot.

Purdue's school-specific plan parser (step 13, batch 3). Reads the newest saved
2026-2027 catalog pages (data/raw/purdue/*_program-<track>.html, saved through Chrome)
and writes data/processed/purdue/plan_parsed.csv with the columns in
common.PARSED_COLUMNS.

Purdue's CS BS is one degree with nine tracks ("concentrations"), and the catalog gives
each track its own program page with its own eight-semester plan. The nine plans share
one template: the same named courses in the same semesters, with six "<Track>
Concentration course" slots (seven for the two 21-credit tracks, Computational Science
and Engineering and Database and Information Systems, which add one in Fall of year
4), and they differ otherwise only in typos ("Langauge") and a few credit ranges. So one plan is used and the others are checked against it
(specs/05-comparison-set.md: common core required, track courses as slots):
- The canonical plan is Software Engineering's, which agrees with the other eight
  most (tied with Security; counted by comparing normalized rows in step 13).
- The check: all nine name the same course codes in the same semesters, and each has
  as many track slots as its "Concentration (N credits)" heading says (N / 3).
- The Software Engineering plan's Fall year 2 "Elective - Credit Hours: 1.00-3.00 (CS
  29100 recommended)" makes that semester 15-19 credits, but the plan states 15-17, and
  six of the nine plans write the elective as 1.00. It is read as 1 credit (CS 29100
  is a 1-credit course), and the correction is in the row's notes (step 10's rule: the
  plan's own statement wins over a typo, recorded in notes).

The plan is Acalog HTML. Each semester is a div.acalog-core whose <h3> names it
("Fall 1st Year"), followed by a list:
- li.acalog-course: "CS 18000 - Problem Solving ... Credit Hours: 4.00 ♦ ***"; a
  course ending in "or" is joined with the next one as a choice;
- other <li> items: slots, "Science Core Selection: Written Communication (UCC: WC) -
  Credit Hours: 3.00-4.00", "Elective - Credit Hours: 1.00 (CS 19300 suggested.)";
- the next div's <h4> states the semester's credits ("15-17 Credits").
"♦" marks a "critical course" (the page's legend). "***" is not explained on the page;
the page's Concentration Notes require a C or better in all major required courses and
track courses, so those rows get min_grade = C from that sentence.

Modeling decisions (step 13, batch 3):
- "MA 16100 ... or MA 16500", "MA 16200 or MA 16600", "MA 26100 or MA 27101",
  "MA 26500 or MA 35100", and "STAT 35000 or STAT 51100" are choices: one elective_slot
  row with the option codes in `options`, credits spanning both options.
- An elective with a suggested course ("CS 19300 suggested", "CS 29100 recommended")
  stays an elective slot; the suggestion is in notes.
- Most slots have credit ranges ("3.00 - 4.00"), so the plan sums to a range; the
  catalog's 120-credit degree requirement is checked to lie inside it (Minnesota's
  precedent, step 13 batch 2).

Usage:
    python src/parse_purdue.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import PARSED_COLUMNS, finish_choices, load_school, rel

SCHOOL = load_school("purdue")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"
CANONICAL_TRACK = "software-engineering"
PLAN = ("Plan of study, Computer Science: Software Engineering, BS, 2026-2027 University Catalog "
        "(the nine track plans share one template; track courses are slots)")

TERMS = {f"{t} {y} Year": (n, t) for n, y in enumerate(["1st", "2nd", "3rd", "4th"], start=1)
         for t in ["Fall", "Spring"]}  # "Fall 1st Year" -> (1, "Fall"), ...
TRACKS = ["Algorithmic Foundations", "Computational Science and Engineering", "Database and Information Systems",
          "Machine Intelligence", "Programming Language", "Security", "Software Engineering", "Systems Software",
          "Visual Computing"]
# "CS 18000 - Problem Solving ... (UCC: QR) Credit Hours: 4.00 ♦ *** or"
COURSE = re.compile(r"^([A-Z]{2,4}) (\d{5}) - (.*?)(?: \(UCC: [A-Z]+\))? Credit Hours: ([\d.]+)(.*)$")
# "<label> - Credit Hours: 3.00 - 4.00 (extra)": label, low, optional high, trailing text.
SLOT = re.compile(r"^(.*?)\s*-\s*Credit Hours:\s*([\d.]+)(?:\s*-\s*([\d.]+))?\s*(.*)$")
TOTAL = re.compile(r"^(\d+)(?:-(\d+))? Credits$")

# Typo corrections in the canonical plan: (year, term, plan text) -> (lo, hi, note).
CORRECTIONS = {
    (2, "Fall", "Elective - Credit Hours: 1.00-3.00( CS 29100 recommended)"): (1, 1,
        "Corrected from the plan's '1.00-3.00': the semester is stated as 15-17 credits, which needs 1 credit "
        "here, and six of the nine track plans write this elective as 1.00."),
}
CORE_GRADE_NOTE = "Purdue (Concentration Notes): all major required and track courses need a C or better."
# Slot labels (normalized: track name -> "TRACK", typos fixed) -> (title, type, notes).
SLOTS = {
    "Science Core Selection: Written Communication (UCC: WC)": ("Written Communication", "gen_ed",
        "Purdue College of Science core: Written Communication (also a University Core Curriculum outcome)."),
    "Elective": ("Free Elective", "elective_slot", "Purdue: any Purdue course may be used in the elective area."),
    "AI Working Competency (UCC: AI)": ("AI Working Competency", "gen_ed",
        "Purdue University Core Curriculum: an approved course meeting the AI working competency (1-3 credits)."),
    "Science Core Selection: Language or Culture I": ("Language and Culture I", "gen_ed",
        "Purdue College of Science core: Language and Culture, three courses (world language or approved "
        "culture courses)."),
    "Science Core Selection: Language or Culture II": ("Language and Culture II", "gen_ed",
        "Purdue College of Science core: Language and Culture, second of three courses."),
    "Science Core Selection: Language & Culture III": ("Language and Culture III", "gen_ed",
        "Purdue College of Science core: Language and Culture, third of three courses."),
    "Science Core Selection: Technical Writing & Presentation": ("Technical Writing and Presentation", "gen_ed",
        "Purdue College of Science core: Technical Writing and Technical Presentation."),
    "Science Core Selection: Science, Technology & Society (UCC: STS)": ("Science, Technology and Society",
        "gen_ed", "Purdue College of Science core / University Core Curriculum: Science, Technology & Society."),
    "Science Core Selection: General Education I": ("General Education I", "gen_ed",
        "Purdue College of Science core: General Education (humanities and social science), first of three."),
    "Science Core Selection: General Education II": ("General Education II", "gen_ed",
        "Purdue College of Science core: General Education, second of three."),
    "Science Core Selection: General Education III": ("General Education III", "gen_ed",
        "Purdue College of Science core: General Education, third of three."),
    "Science Core Selection: Great Issues In Science": ("Great Issues in Science", "gen_ed",
        "Purdue College of Science core: Great Issues in Science and Society."),
    "Science Core Selection: Lab Science I": ("Lab Science I", "elective_slot",
        "Purdue College of Science core: Laboratory Science, two courses outside CS."),
    "Science Core Selection: Lab Science II": ("Lab Science II", "elective_slot",
        "Purdue College of Science core: Laboratory Science, second course."),
    "Science Core Selection": ("Science Core Selection", "gen_ed",
        "Purdue College of Science core: a course from any remaining core area (only the Database and "
        "Information Systems plan writes it this way)."),
    "TRACK Concentration course": ("CS Track Course", "elective_slot",
        "Purdue: six courses (18 credits; seven, 21 credits, in two tracks) in the student's track, 2-4 required and the rest chosen from the "
        "track's list; nine tracks (Algorithmic Foundations, Computational Science and Engineering, Database and "
        "Information Systems, Machine Intelligence, Programming Languages, Security, Software Engineering, "
        "Systems Software, Visual Computing). " + CORE_GRADE_NOTE),
}


# Text of an element with non-breaking spaces made normal and whitespace collapsed.
def text(el) -> str:
    """Return an element's visible text, whitespace-collapsed."""
    return re.sub(r"\s+", " ", el.get_text(" ").replace("\xa0", " ")).strip()


# Normalize a slot label so the nine plans' variants compare equal: track names become
# "TRACK", the "Langauge" typo is fixed, "(CC: AI)" becomes "(UCC: AI)", a missing space
# after a colon is added, and the
# Database plan's "Great Issues In Science Selection" loses "Selection".
def norm_label(label: str) -> str:
    """Return the canonical form of a plan slot label."""
    for track in TRACKS:
        label = re.sub(rf"^{track} Concentration course\b", "TRACK Concentration course", label)
    label = label.replace("Langauge", "Language").replace("(CC: AI)", "(UCC: AI)")
    label = re.sub(r":\s*", ": ", label)  # "Selection:Great Issues" -> "Selection: Great Issues"
    return re.sub(r"Great Issues In Science Selection", "Great Issues In Science", label).strip()


# A row dict for given credits.
def base_row(lo: float, hi: float) -> dict:
    """Return a required-course row with the given credit range."""
    return {"course_code": "", "subject": "", "number": "", "title": "", "credits_min": lo, "credits_max": hi,
            "requirement_type": "required", "gened_tag": "", "min_grade": "", "counts_toward_total": True,
            "notes": "", "options": ""}


# Parse one semester's <li> items into rows. Courses ending in "or" collect into a
# pending choice that the next course closes. `fixes` holds the typo corrections for
# this plan (CORRECTIONS for the canonical plan, {} for the others).
def parse_items(items: list[str], term: tuple, fixes: dict) -> list[dict]:
    """Return the rows of one semester, applying any (year, term, text) corrections."""
    rows, pending = [], []
    for item in items:
        m = COURSE.match(item)
        if m:
            subj, num, title, hours, tail = m.groups()
            pending.append((f"{subj} {num}", subj, title, float(hours), "♦" in tail))
            if tail.strip().endswith("or"):
                continue  # the choice continues with the next course
            if len(pending) == 1:
                code, subj, title, hours, critical = pending[0]
                r = base_row(hours, hours)
                notes = ["Critical course (Purdue: one a student must pass to persist in the major)."] if critical else []
                if subj == "CS":
                    r["min_grade"] = "C"
                    notes.append(CORE_GRADE_NOTE)
                r.update(course_code=code, subject=subj, number=num, title=title, notes=" ".join(notes))
            else:
                codes = [p[0] for p in pending]
                subjects = {p[1] for p in pending}
                r = base_row(min(p[3] for p in pending), max(p[3] for p in pending))
                r.update(subject=subjects.pop() if len(subjects) == 1 else "",
                         title=f"{' or '.join(codes)} ({pending[0][2]})", requirement_type="elective_slot",
                         options="; ".join(codes),
                         notes="Student chooses one: " + " | ".join(f"{p[2]} ({p[3]:g} cr)" for p in pending) + ".")
            rows.append(r)
            pending = []
            continue
        s = SLOT.match(item)
        if not s:
            raise SystemExit(f"Unrecognized plan item: {item!r}")
        label, lo, hi, extra = s.groups()
        key = norm_label(label)
        if key not in SLOTS:
            raise SystemExit(f"Unknown slot label in the plan: {label!r}. Add it to SLOTS.")
        title, rtype, notes = SLOTS[key]
        r = base_row(float(lo), float(hi or lo))
        extra = extra.replace("***", "").strip().strip("()").strip()
        if extra:
            notes = f"The plan adds: '{extra}'. {notes}"
        if key.startswith("TRACK"):
            r["min_grade"] = "C"
        fix = fixes.get((*term, item))  # (*term, item) unpacks to the (year, term, text) key
        if fix:
            r.update(credits_min=fix[0], credits_max=fix[1])
            notes = f"{notes} {fix[2]}"
        r.update(title=title, requirement_type=rtype, notes=notes)
        rows.append(r)
    if pending:
        raise SystemExit("A choice ('... or') has no closing course.")
    return rows


# Read one track's plan: {(year, term): rows} and {(year, term): stated (lo, hi)}.
def read_plan(path: Path) -> tuple[dict, dict]:
    """Return the plan's rows and stated credit ranges by semester."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    start = next(h for h in soup.find_all("h3") if text(h) == "Fall 1st Year").find_parent("div", class_="acalog-core")
    sems, stated, term = {}, {}, None
    for div in [start] + start.find_all_next("div", class_="acalog-core"):
        head = div.find(["h3", "h4"])
        head_text = text(head) if head else ""
        if head_text in TERMS:
            term = TERMS[head_text]
            items = [text(li) for li in div.find_all("li") if text(li)]
            # Corrections apply to the canonical plan only; the others are just compared.
            fixes = CORRECTIONS if path.name.endswith(f"_program-{CANONICAL_TRACK}.html") else {}
            sems[term] = parse_items(items, term, fixes)
        elif TOTAL.match(head_text):
            t = TOTAL.match(head_text)
            stated[term] = (int(t.group(1)), int(t.group(2) or t.group(1)))
            if term == (4, "Spring"):
                break  # the World Language list and the legend follow
    return sems, stated


# The comparable shape of a plan: per semester, the sorted course codes (and option
# sets) the plan names.
def shape(sems: dict) -> dict:
    """Return {(year, term): sorted codes}."""
    return {term: sorted(r["course_code"] or r["options"] for r in rows if r["course_code"] or r["options"])
            for term, rows in sems.items()}


# Track slots in a plan, and the number its "Concentration (N credits)" heading implies.
def track_slots(path: Path, sems: dict) -> tuple[int, int]:
    """Return (track slots in the plan, concentration credits / 3)."""
    m = re.search(r"Concentration \((\d+) credits\)", text(BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")))
    return sum(r["title"] == "CS Track Course" for rows in sems.values() for r in rows), int(m.group(1)) // 3


# Run the parse checks and return a list of failure messages (empty = all passed).
def check(df: pd.DataFrame, stated: dict, others: dict, canon: dict, page: str) -> list[str]:
    """Return failed-check messages."""
    failures = []
    lo, hi = df["credits_min"].sum(), df["credits_max"].sum()
    if SCHOOL.credits != (lo, hi):
        failures.append(f"schools.csv says {SCHOOL.credits} credits; the plan sums to {lo:g}-{hi:g}.")
    m = re.search(r"Degree Requirements (\d+) Credits Required", page)
    if not m or not lo <= int(m.group(1)) <= hi:
        failures.append(f"The catalog's degree minimum ({m.group(1) if m else 'not found'}) is not within {lo:g}-{hi:g}.")
    if len(stated) != 8:
        failures.append(f"Expected 8 semesters, found {len(stated)}.")
    for (y, t), (s_lo, s_hi) in stated.items():
        g = df[(df["orig_year"] == y) & (df["orig_term"] == t)]
        got = (g["credits_min"].sum(), g["credits_max"].sum())
        if got != (s_lo, s_hi):
            print(f"  note: Year {y} {t} rows sum to {got[0]:g}-{got[1]:g}; the plan states {s_lo}-{s_hi}.")
            if abs(got[0] - s_lo) > 1 or abs(got[1] - s_hi) > 2:
                failures.append(f"Year {y} {t}: rows {got[0]:g}-{got[1]:g} far from the stated {s_lo}-{s_hi}.")
    for track, (other, (slots, wanted)) in others.items():
        if other != canon:
            failures.append(f"Track plan '{track}' names different courses than the canonical plan.")
        if slots != wanted:
            failures.append(f"Track plan '{track}' has {slots} track slots; its concentration needs {wanted}.")
    return failures


# Script entry point: read all nine plans, keep the canonical one, check, and write.
def main() -> None:
    paths = {p.name.split("program-", 1)[1].removesuffix(".html"): p
             for p in sorted(SCHOOL.raw.glob("*_program-*.html"))}  # later dates overwrite earlier ones
    if len(paths) != 9:
        raise SystemExit(f"Expected 9 track plans in {rel(SCHOOL.raw)}, found {len(paths)}.")
    plans = {track: read_plan(p) for track, p in paths.items()}
    sems, stated = plans[CANONICAL_TRACK]
    path = paths[CANONICAL_TRACK]
    dept = SCHOOL.newest(SCHOOL.college_source)
    if SCHOOL.college not in text(BeautifulSoup(dept.read_text(encoding="utf-8"), "html.parser")):
        raise SystemExit(f"College '{SCHOOL.college}' not found on {rel(dept)}.")

    rows = []
    for (year, term), sem_rows in sorted(sems.items(), key=lambda kv: (kv[0][0], kv[0][1] != "Fall")):
        for r in sem_rows:
            r.update(orig_year=year, orig_term=term)
            rows.append(r)
    df = pd.DataFrame(rows)
    for col in ["credits_min", "credits_max"]:
        # A plain list in an object Series keeps whole numbers as ints in the CSV.
        df[col] = pd.Series([int(x) if x == int(x) else x for x in df[col]], index=df.index, dtype=object)
    df["orig_calendar_year"] = ""
    df["orig_term_type"] = "academic"
    df["is_coop"] = False
    df["institution"] = SCHOOL.institution
    df["program"] = SCHOOL.program
    df["catalog_year"] = SCHOOL.catalog_year
    df["plan"] = PLAN
    df["source_file"] = rel(path)

    canon = shape(sems)
    # The canonical plan's own slot count is checked here too, keyed by its track name.
    others = {t: (shape(s), track_slots(paths[t], s)) for t, (s, _) in plans.items()}
    page = text(BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser"))
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum():g}-{df['credits_max'].sum():g} (degree requires 120)")
    failures = check(df, stated, others, canon, page)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 13 parse checks passed (all nine track plans name the same courses).")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
