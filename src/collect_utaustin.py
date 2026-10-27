"""Download UT Austin's CS BS catalog pages into data/raw/utaustin/ and log them in sources.csv.

UT Austin publishes its 2026-2028 Undergraduate Catalog as static CourseLeaf pages, so
plain GET requests are enough. The Computer Science degree has several options; the
standard "Computer Science Option" is used (not the Honors or Turing Scholars options).
Its page holds the requirements and the Plan of Study grid.

Course descriptions come one page per subject in the "Courses A-Z" section of the
catalog. Only the subjects that appear in the plan of study are saved.

Sources were reviewed and approved by the user before downloading (step 13).

Usage:
    python src/collect_utaustin.py
"""

from datetime import date

from collect_common import fetch
from common import load_school

SCHOOL = load_school("utaustin")
CATALOG = "https://catalog.utexas.edu/"

# (slug, url, description, file extension).
SOURCES = [
    ("bscompsci-cs-option-catalog",
     CATALOG + "undergraduate/programs/computer-science-computer-science-option-bscompsci/",
     "BS in Computer Science, Computer Science Option, 2026-2028 catalog: requirements, plan of study, college (canonical plan)",
     ".html"),
]
# Subjects of the named courses in the plan, as UT's URL slugs: "c-s" is the subject
# "C S" (UT writes it with a space), "m" is Mathematics.
SUBJECTS = ["c-s", "m", "sds", "rhe", "gov"]


# Entry point: fetch the program page, then one description page per subject.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-10-17"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    for subj in SUBJECTS:
        fetch(SCHOOL.raw, f"courses-{subj}", f"{CATALOG}general-information/coursesatoz/{subj}/",
              f"Course descriptions, subject {subj.upper().replace('-', ' ')}, 2026-2028 catalog", today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
