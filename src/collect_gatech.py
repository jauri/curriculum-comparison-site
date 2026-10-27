"""Download Georgia Tech's CS BS sources into data/raw/gatech/ and log them in sources.csv.

Georgia Tech's BS in Computer Science is built from two "Threads" chosen by the student,
and the catalog lists requirements per thread pair, with no semester layout. The
College of Computing's "Thread Combination Credit Sheets" page links an eight-semester
plan per academic year: "General 8 Semester Plan, No Threads", an Excel file on Dropbox.
The 2026-27 sheets are restricted ("Request access"), so the 2025-26 general plan is the
canonical plan (decided with the user in step 13, batch 3; catalog year 2025-26, as for
Northeastern). A plain GET of its dl=1 link returns the file.

Also saved:
- the credit-sheets page itself, which links the plan and names its year;
- the 2026-2027 catalog's BS CS page (College of Computing; thread structure, general
  requirements), used to verify the college and cross-check the plan. The catalog's
  archive holds only whole-catalog PDFs, so the current edition is used;
- one 2026-2027 course-description page per subject named in the plan.

Sources were reviewed and approved by the user before downloading (step 13, batch 3).

Usage:
    python src/collect_gatech.py
"""

from datetime import date

from collect_common import fetch
from common import load_school

SCHOOL = load_school("gatech")
CATALOG = "https://catalog.gatech.edu/"

# (slug, url, description, file extension).
SOURCES = [
    ("8-semester-plan-25-26",
     "https://www.dropbox.com/scl/fi/2035d1itol9yldwtewwrq/8-Semester-Plan-25-26.xlsx"
     "?rlkey=woui7t7ytv206q1exzzt2mzk5&st=ocxfxg1p&dl=1",
     "General 8 Semester Plan, No Threads, 2025-26 academic year (College of Computing credit sheet, Excel; "
     "canonical plan)", ".xlsx"),
    ("credit-sheets-page", "https://www.cc.gatech.edu/thread-combination-credit-sheets",
     "College of Computing, Thread Combination Credit Sheets page: links the 8-semester plans by year", ".html"),
    ("bs-cs-catalog", CATALOG + "programs/computer-science-bs/",
     "Bachelor of Science in Computer Science, 2026-2027 catalog: threads, general requirements, college "
     "(cross-check)", ".html"),
]
# Subjects of the courses named in the 2025-26 plan: CS, ENGL (1101, 1102), MATH (1551,
# 1552, 1554, 2550, 3012), APPH (1040/1050/1060 wellness), HIST (2111 or 2112).
SUBJECTS = ["cs", "engl", "math", "apph", "hist"]


# Entry point: fetch the plan and pages, then one description page per subject.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-10-17"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    for subj in SUBJECTS:
        fetch(SCHOOL.raw, f"courses-{subj}", f"{CATALOG}coursesaz/{subj}/",
              f"Course descriptions, subject {subj.upper()}, 2026-2027 catalog", today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
