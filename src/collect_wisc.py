"""Download Wisconsin's Computer Sciences BS Guide pages into data/raw/wisc/ and log them.

UW-Madison publishes its 2026-2027 Guide as static CourseLeaf pages, so plain GET
requests are enough. The Computer Sciences BS page (College of Letters & Science) holds
the university, college, and major requirements and the Four-Year Plan.

Course descriptions come one page per subject. The plan names courses only by code
(no titles), so the subject pages also supply the titles. Only the subjects of courses
named in the plan or in its "Complete one" option lists (linear algebra, probability or
statistics, theory) are saved. Cross-listed courses (COMP SCI/E C E 354) are described
on every listing subject's page, so the COMP SCI page is enough for them.

Sources were reviewed and approved by the user before downloading (step 13, batch 2).

Usage:
    python src/collect_wisc.py
"""

from datetime import date

from collect_common import fetch
from common import load_school

SCHOOL = load_school("wisc")
GUIDE = "https://guide.wisc.edu/"

# (slug, url, description, file extension).
SOURCES = [
    ("bs-cs-guide", GUIDE + "undergraduate/letters-science/computer-sciences/computer-sciences-bs/",
     "Computer Sciences BS, 2026-2027 Guide: requirements, four-year plan, total credits, college (canonical plan)",
     ".html"),
]
# Subjects of the plan's courses and option lists. Guide subject slugs use underscores
# ("comp_sci", "inter_ls"); the hyphenated form returns 404.
SUBJECTS = ["comp_sci", "math", "stat", "inter_ls"]


# Entry point: fetch the program page, then one description page per subject.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-10-17"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    for subj in SUBJECTS:
        fetch(SCHOOL.raw, f"courses-{subj}", f"{GUIDE}courses/{subj}/",
              f"Course descriptions, subject {subj.upper()}, 2026-2027 Guide", today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
