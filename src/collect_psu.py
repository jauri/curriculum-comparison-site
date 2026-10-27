"""Download Penn State's CS BS bulletin pages into data/raw/psu/ and log them in sources.csv.

Penn State publishes its 2026-2027 Undergraduate Bulletin as static CourseLeaf pages,
so plain GET requests are enough. The Computer Science, B.S. (Engineering) page holds
the program requirements and, in its "Suggested Academic Plan" tab, one plan per
campus; the University Park plan is the canonical one ("127-130" total credits).

Course descriptions come one page per subject. Only the subjects of courses named in
the University Park plan are saved.

Sources were reviewed and approved by the user before downloading (step 13, batch 3).

Usage:
    python src/collect_psu.py
"""

from datetime import date

from collect_common import fetch
from common import load_school

SCHOOL = load_school("psu")
BULLETIN = "https://bulletins.psu.edu/"

# (slug, url, description, file extension).
SOURCES = [
    ("bs-cs-bulletin", BULLETIN + "undergraduate/colleges/engineering/computer-science-bs/",
     "Computer Science, B.S. (Engineering), 2026-2027 Undergraduate Bulletin: requirements and suggested "
     "academic plans by campus; University Park plan is canonical", ".html"),
]
# Subjects of the courses named in the University Park plan: CMPSC, MATH (140, 141,
# 220, 230), PHYS (211, 212), ENGL (15, 202C), CAS (100A/B), CMPEN (270), STAT (318, 319).
SUBJECTS = ["cmpsc", "math", "phys", "engl", "cas", "cmpen", "stat"]


# Entry point: fetch the program page, then one description page per subject.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-10-17"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    for subj in SUBJECTS:
        fetch(SCHOOL.raw, f"courses-{subj}", f"{BULLETIN}university-course-descriptions/undergraduate/{subj}/",
              f"Course descriptions, subject {subj.upper()}, 2026-2027 Undergraduate Bulletin", today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
