"""Download UIC's CS BS catalog pages into data/raw/uic/ and log them in sources.csv.

UIC publishes its 2026-2027 Undergraduate Catalog as static CourseLeaf pages, so plain
GET requests are enough. Course descriptions come one page per subject (all CS courses
on one page, all MATH courses on another, ...), so only the subjects in the degree
requirements are saved.

Sources were reviewed and approved by the user before downloading (step 10).

Usage:
    python src/collect_uic.py
"""

from datetime import date

from collect_common import fetch
from common import load_school

SCHOOL = load_school("uic")
CATALOG = "https://catalog.uic.edu/ucat/"

# (slug, url, description, file extension).
SOURCES = [
    ("bs-cs-catalog", CATALOG + "colleges-depts/engineering/cs/bs-cs/",
     "BS in Computer Science, 2026-2027 catalog: requirements, sample schedule, science list, college (canonical plan)",
     ".html"),
    ("bs-cs-catalog", CATALOG + "colleges-depts/engineering/cs/bs-cs/bs-cs.pdf",
     "PDF version of the BS in Computer Science catalog page (backup)", ".pdf"),
    ("general-education", CATALOG + "degree-programs/general-education/",
     "General education requirements and categories", ".html"),
]
# Subjects whose course-description pages are needed: every subject of a required
# course or of the "Required Mathematics" options (IE 342 or STAT 381).
SUBJECTS = ["cs", "math", "engl", "engr", "ie", "stat"]


# Entry point: fetch the program pages, then one description page per subject.
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
