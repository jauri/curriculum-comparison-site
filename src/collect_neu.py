"""Download Northeastern's CS BSCS catalog pages into data/raw/neu/ and log them in sources.csv.

Northeastern publishes its catalog as static CourseLeaf pages, so plain GET requests are
enough. The 2026-2027 BSCS page has requirements but no plan of study, so the canonical
plan is the "Sample Plan of Study" tab of the archived 2025-2026 page (chosen by the
user in step 13). The current 2026-2027 page is saved too, to cross-check the
requirements (it states 133 hours; the 2025-26 plan totals 135).

Course descriptions come one page per subject. Only the subjects of courses named in
the plan are saved, from two catalog years:
- the archived 2025-2026 pages, which match the plan's year and are the ones used. They
  were added after the first run (same site and kind of page) because Northeastern
  reused a number: DS 3000 is "Foundations of Data Science" in the 2025-26 plan but
  "Mathematical Foundations of Artificial Intelligence" in the 2026-27 catalog.
- the current 2026-2027 pages, kept as a cross-check of what changed.

Sources were reviewed and approved by the user before downloading (step 13).

Usage:
    python src/collect_neu.py
"""

from datetime import date

from collect_common import fetch
from common import load_school

SCHOOL = load_school("neu")
CATALOG = "https://catalog.northeastern.edu/"
PROGRAM = "undergraduate/computer-information-science/computer-science/bscs/"

# (slug, url, description, file extension).
SOURCES = [
    ("bscs-catalog-2025-26", CATALOG + "archive/2025-2026/" + PROGRAM,
     "BSCS (Boston), archived 2025-2026 catalog: requirements and sample plans of study (canonical plan)",
     ".html"),
    ("bscs-catalog-2026-27", CATALOG + PROGRAM,
     "BSCS (Boston), 2026-2027 catalog: requirements only, no plan of study (cross-check)",
     ".html"),
]
# Subjects of the courses named in the plan (ENGW = Writing, EECE = Electrical and
# Computer Engineering, DS = Data Science).
SUBJECTS = ["cs", "math", "engw", "eece", "ds"]


# Entry point: fetch the program pages, then one description page per subject.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-10-17"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    for subj in SUBJECTS:
        fetch(SCHOOL.raw, f"courses-2025-26-{subj}", f"{CATALOG}archive/2025-2026/course-descriptions/{subj}/",
              f"Course descriptions, subject {subj.upper()}, archived 2025-2026 catalog (used)", today)
        fetch(SCHOOL.raw, f"courses-{subj}", f"{CATALOG}course-descriptions/{subj}/",
              f"Course descriptions, subject {subj.upper()}, 2026-2027 catalog (cross-check)", today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
