"""Download Case Western Reserve's Computer Science BS bulletin pages into data/raw/case/.

CWRU publishes its General Bulletin as static CourseLeaf pages, so plain GET requests
are enough. The Computer Science, BS page (Department of Computer and Data Sciences,
Case School of Engineering) holds the program requirements and the "Sample Plan of
Study" grid (canonical plan, eight semesters, 122 credit hours). The plan starts with
CSDS 132 Programming in Java, which has no prerequisite, so it starts from no
programming experience (spec 05's display rule). The BA in Computer Science is a
separate degree; the engineering rule (spec 05) picks the BS.

Course descriptions come one page per subject from the bulletin's course descriptions
(bulletin.case.edu/course-descriptions/<subject>/). Only the subjects of courses named
in the plan are saved.

Sources were reviewed and approved by the user before downloading (batch 5,
2026-11-14).

Usage:
    python src/collect_case.py
"""

from datetime import date

from collect_common import fetch
from common import load_school

SCHOOL = load_school("case")
BULLETIN = "https://bulletin.case.edu/"

# (slug, url, description, file extension).
SOURCES = [
    ("bs-cs-bulletin", BULLETIN + "engineering/computer-data-sciences/computer-science-bs/",
     "Computer Science, BS, Case School of Engineering, CWRU General Bulletin: program requirements, total "
     "credit hours, Sample Plan of Study (canonical plan)", ".html"),
]
# Subjects of the courses named in the plan, plus STAT and OPRE for the options of its
# Statistics Elective slot.
SUBJECTS = ["csds", "math", "phys", "engr", "stat", "opre"]


# Entry point: fetch the program page, then one description page per subject.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-11-14"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    for subj in SUBJECTS:
        fetch(SCHOOL.raw, f"courses-{subj}", f"{BULLETIN}course-descriptions/{subj}/",
              f"Course descriptions, subject {subj.upper()}, CWRU General Bulletin", today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
