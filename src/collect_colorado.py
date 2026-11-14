"""Download Colorado Boulder's CS BS catalog pages into data/raw/colorado/ and log them.

CU Boulder publishes its Undergraduate Catalog as static CourseLeaf pages, so plain GET
requests are enough. The Computer Science Bachelor of Science page of the College of
Engineering and Applied Science holds the requirements and the "Recommended Four-Year
Plan of Study" grid (canonical plan). The BA in Computer Science is a separate degree in
Arts and Sciences; the engineering rule (spec 05) picks the BS.

Course descriptions come one page per subject from "Courses A-Z". Only the subjects of
courses named in the plan are saved.

Sources were reviewed and approved by the user before downloading (batch 4).

Usage:
    python src/collect_colorado.py
"""

from datetime import date

from collect_common import fetch
from common import load_school

SCHOOL = load_school("colorado")
CATALOG = "https://catalog.colorado.edu/"

# (slug, url, description, file extension).
SOURCES = [
    ("bs-cs-catalog", CATALOG + "undergraduate/colleges-schools/engineering-applied-science/programs-study/"
     "computer-science/computer-science-bachelor-science-bs/",
     "Computer Science BS, College of Engineering and Applied Science, Undergraduate Catalog: requirements, "
     "total credits, Recommended Four-Year Plan of Study (canonical plan)", ".html"),
]
# Subjects of the courses named in the plan.
SUBJECTS = ["csci", "appm", "phys", "coen"]


# Entry point: fetch the program page, then one description page per subject.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-11-13"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    for subj in SUBJECTS:
        fetch(SCHOOL.raw, f"courses-{subj}", f"{CATALOG}courses-a-z/{subj}/",
              f"Course descriptions, subject {subj.upper()}, Undergraduate Catalog", today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
