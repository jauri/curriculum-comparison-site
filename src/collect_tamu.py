"""Download Texas A&M's CS BS catalog pages into data/raw/tamu/ and log them in sources.csv.

Texas A&M publishes its 2026-2027 Undergraduate Catalog as static CourseLeaf pages, so
plain GET requests are enough. The CS BS page holds the requirements and the plan of
study, which comes as two grids: the common College of Engineering first year, then
the CS-specific second through fourth years.

Course descriptions come one page per subject. Only the subjects of courses named in
the plan (including the options of its "Select one of the following" choices) are saved.

Sources were reviewed and approved by the user before downloading (step 13).

Usage:
    python src/collect_tamu.py
"""

from datetime import date

from collect_common import fetch
from common import load_school

SCHOOL = load_school("tamu")
CATALOG = "https://catalog.tamu.edu/undergraduate/"

# (slug, url, description, file extension).
SOURCES = [
    ("bs-cs-catalog", CATALOG + "engineering/computer-science/bs/",
     "BS in Computer Science, 2026-2027 catalog: requirements, plan of study, total hours, college (canonical plan)",
     ".html"),
]
# Subjects of the courses named in the plan. CSCE 222 is cross-listed as ECEN 222, and
# ENGR 216 as PHYS 216; the CSCE and ENGR pages describe them, so ECEN isn't needed.
SUBJECTS = ["csce", "chem", "engl", "engr", "math", "phys", "comm", "stat"]


# Entry point: fetch the program page, then one description page per subject.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-10-17"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    for subj in SUBJECTS:
        fetch(SCHOOL.raw, f"courses-{subj}", f"{CATALOG}course-descriptions/{subj}/",
              f"Course descriptions, subject {subj.upper()}, 2026-2027 catalog", today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
