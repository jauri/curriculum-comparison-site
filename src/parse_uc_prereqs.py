"""Parse UC's catalog prerequisite text into a table the curriculum editor can check.

Step 23 follow-up (specs/11-editor-view.md, "Checks"). The editor warns when a draft
places a course before (or in the same semester as) a prerequisite, or removes a
prerequisite. It needs each course's prerequisites as course codes, not as the
catalog's sentence, and the web views must not parse data themselves (CLAUDE.md), so
this script does the parsing.

Input: data/processed/uc/required_courses.csv, column `prerequisites`: UC's catalog
text as saved by describe.py, e.g.

    To take this course you must: Have taken the following Courses CS2028C min grade
    C-,CS2071 min grade C-, or EECE2080C min grade C-. Be enrolled in one of these
    Plans CS-BSCS, CMPE-BSCOM, CS-MIN.

Reading rules (written here so every value traces to a rule):

1. Only the sentence "Have taken the following Course(s) ..." names prerequisite
   courses. The other sentences (plans, programs, placement tests) are about who may
   enroll, not about order in the plan, and are ignored, except rules 4 and 5.
2. Within that sentence, ", or " separates alternatives, and a plain "," inside an
   alternative joins courses that are all required. So "A,B, or C" reads as
   (A and B) or C. The catalog gives no parentheses; this is the reading that fits
   UC's own plan (CS 4071 needs CS 2028C, CS 2071, and STAT 2037 together).
3. An alternative counts for the editor only if every course in it is in UC's 8
   academic semesters (`in_plan`). Alternatives with outside courses (EECE 2080C,
   placement courses) can't be checked against a draft. A course with no in-plan
   alternative has nothing to check.
4. A placement test can replace the courses: when the text also says "Taken one of
   these tests ...", a student can meet the requirement by test score (UC's plan puts
   ENED 1021 and MATH 1061 in semester 1 on that basis), so the course has no in-plan
   alternative to check. Its alternatives are still listed in the CSV.
5. Class standing: "Be a First Year Student" -> semesters 1-2 only; "Be at least a
   Sophomore / Junior / Senior" -> from semester 3 / 5 / 7. A 4-year plan has two
   semesters per year, so this is the standing a student on the plan would have.

Writes:
- data/processed/uc/prerequisites.csv: one line per (course, alternative, prerequisite)
  for analysis, with in_plan.
- data/processed/uc/prerequisites.json: one object per course with prerequisite text,
  for the editor: course_code, text, alternatives (all, lists of codes),
  plan_alternatives (rule 3), standing, min_sem, max_sem.

Usage:
    python src/parse_uc_prereqs.py
"""

import json
import re

import pandas as pd

from common import ROOT, rel, require

PROCESSED = ROOT / "data" / "processed" / "uc"
IN_CSV = PROCESSED / "required_courses.csv"
OUT_CSV = PROCESSED / "prerequisites.csv"
OUT_JSON = PROCESSED / "prerequisites.json"

# The sentence naming prerequisite courses (rule 1). "Courses?" takes the singular
# ("the following Course MATH1062") and the plural. The lazy (.*?) stops at the first
# period followed by a space or the end, i.e. the end of the sentence; the codes and
# grades inside ("C-") contain no periods.
TAKEN_RE = re.compile(r"Have taken the following Courses? (.*?)\.(?:\s|$)")
# One catalog code, written without a space ("CS2028C"): letters, then four digits and
# an optional letter suffix (C = combined lecture and lab at UC).
CODE_RE = re.compile(r"^([A-Z]+)(\d{4}[A-Z]?)$")
# A placement test that can replace the prerequisite courses (rule 4).
TEST_PHRASE = "Taken one of these tests"
# Class standing (rule 5): the semesters a student on a 4-year plan has that standing.
STANDING = {
    "Be a First Year Student": ("First year", 1, 2),
    "Be at least a Sophomore": ("Sophomore", 3, 8),
    "Be at least a Junior": ("Junior", 5, 8),
    "Be at least a Senior": ("Senior", 7, 8),
}


# Turn "CS2028C min grade C-" into "CS 2028C", the plan's spelling. Returns None for
# anything that isn't a plain course code, so an unexpected item is reported, not guessed.
def plan_code(item: str) -> str | None:
    """Return the plan-style code for one prerequisite item, or None."""
    code = item.strip().split(" min grade")[0].strip()
    m = CODE_RE.match(code)
    return f"{m.group(1)} {m.group(2)}" if m else None


# Split the "Have taken" sentence into alternatives (rule 2). Returns a list of lists of
# codes, and the items that weren't codes (so main() can stop on them).
def alternatives(text: str) -> tuple[list[list[str]], list[str]]:
    """Return (alternatives, unreadable items) for one prerequisite text."""
    m = TAKEN_RE.search(text)
    if not m:
        return [], []
    alts, bad = [], []
    for alt in m.group(1).split(", or "):
        codes = []
        for item in alt.split(","):
            code = plan_code(item)
            if code:
                codes.append(code)
            else:
                bad.append(item.strip())
        alts.append(codes)
    return alts, bad


# Script entry point: read the plan, parse each row's text, check, and write both files.
def main() -> None:
    require([(IN_CSV, "build_outputs.py --school uc")])
    # keep_default_na=False keeps empty prerequisite cells as "" instead of NaN.
    df = pd.read_csv(IN_CSV, keep_default_na=False)
    academic = df[df["is_coop"].astype(str) != "True"]
    in_plan = set(academic.loc[academic["course_code"] != "", "course_code"])

    lines, courses, problems = [], [], []
    for _, r in academic[academic["prerequisites"] != ""].iterrows():
        text = r["prerequisites"]
        alts, bad = alternatives(text)
        problems += [f"{r['course_code']}: can't read '{b}'" for b in bad]
        # next() with a default: the first standing phrase in the text, or None.
        standing = next((v for k, v in STANDING.items() if k in text), None)
        for i, alt in enumerate(alts, start=1):
            for code in alt:
                lines.append({"course_code": r["course_code"], "alternative": i, "prereq_code": code,
                              "in_plan": code in in_plan})
        courses.append({
            "course_code": r["course_code"], "text": text, "alternatives": alts,
            # Rule 3: keep an alternative only when all its courses are in UC's plan;
            # rule 4: none when a placement test can stand in for the courses.
            "plan_alternatives": [] if TEST_PHRASE in text else [a for a in alts if a and all(c in in_plan for c in a)],
            "standing": standing[0] if standing else None,
            "min_sem": standing[1] if standing else None,
            "max_sem": standing[2] if standing else None,
        })
    if problems:
        raise SystemExit("Unreadable prerequisite items:\n  " + "\n  ".join(problems))

    # UC's own plan must pass its own checks; if not, a rule above is wrong.
    # norm_semester was read as text (co-op rows leave it blank), so make it a number.
    sem = dict(zip(academic["course_code"], academic["norm_semester"].astype(int)))
    for c in courses:
        s = sem[c["course_code"]]
        ok = not c["plan_alternatives"] or any(all(sem[p] < s for p in a) for a in c["plan_alternatives"])
        if not ok or (c["min_sem"] and not c["min_sem"] <= s <= c["max_sem"]):
            raise SystemExit(f"UC's own plan fails the check for {c['course_code']}; check the reading rules.")

    pd.DataFrame(lines).to_csv(OUT_CSV, index=False)
    OUT_JSON.write_text(json.dumps(courses, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    checked = sum(1 for c in courses if c["plan_alternatives"] or c["standing"])
    print(f"Wrote {len(lines)} prerequisite lines to {rel(OUT_CSV)} and {len(courses)} courses to {OUT_JSON.name}")
    print(f"{checked} courses have something the editor can check; UC's own plan passes.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
