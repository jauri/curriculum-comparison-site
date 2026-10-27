"""Download UIUC's CS BS catalog pages into data/raw/uiuc/ and log them in sources.csv.

The University of Illinois Urbana-Champaign publishes its 2026-2027 Course Catalog as
static CourseLeaf pages, so plain GET requests are enough. The CS BS page (Grainger
College of Engineering) holds the requirements, the eight-semester "Sample Sequence",
and the 128-hour total.

Course descriptions come one page per subject ("courses of instruction"). Only the
subjects of courses named in the sample sequence (including both sides of its "or"
choices) are saved.

Sources were reviewed and approved by the user before downloading (step 13, batch 2).

Usage:
    python src/collect_uiuc.py
"""

from datetime import date

from collect_common import fetch
from common import load_school

SCHOOL = load_school("uiuc")
CATALOG = "https://catalog.illinois.edu/"

# (slug, url, description, file extension).
SOURCES = [
    ("bs-cs-catalog", CATALOG + "undergraduate/engineering/computer-science-bs/",
     "Computer Science BS, 2026-2027 catalog: requirements, sample sequence, total hours, college (canonical plan)",
     ".html"),
]
# Subjects of the courses named in the sample sequence: CS, MATH (221/220, 231, 241,
# 257), PHYS (211, 212), and ENG (ENG 100, the Grainger orientation seminar).
SUBJECTS = ["cs", "math", "phys", "eng"]


# Entry point: fetch the program page, then one description page per subject.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-10-17"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    for subj in SUBJECTS:
        fetch(SCHOOL.raw, f"courses-{subj}", f"{CATALOG}courses-of-instruction/{subj}/",
              f"Course descriptions, subject {subj.upper()}, 2026-2027 catalog", today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
