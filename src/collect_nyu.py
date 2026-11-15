"""Download NYU Tandon's Computer Science BS bulletin pages into data/raw/nyu/ and log them.

NYU publishes its Bulletins as static CourseLeaf pages, so plain GET requests are
enough. The Computer Science (BS) page of the Tandon School of Engineering holds the
curriculum list and the "Sample Plan of Study" grid (canonical plan, eight semesters,
128 credits). The plan's first course, CS-UY 1114, is "for ... majors who have limited
prior experience in programming", so the plan starts from no programming experience
(spec 05's display rule).

Course descriptions come one page per subject from the bulletin's course pages
(bulletins.nyu.edu/courses/<subject>/, subject written lowercase with an underscore,
e.g. cs_uy for CS-UY). Only the subjects of courses named in the plan are saved.

Sources were reviewed and approved by the user before downloading (batch 5,
2026-11-14). The bulletin host refused connections earlier that day and answered again
in the evening.

Usage:
    python src/collect_nyu.py
"""

from datetime import date

from collect_common import fetch
from common import load_school

SCHOOL = load_school("nyu")
BULLETIN = "https://bulletins.nyu.edu/"

# (slug, url, description, file extension).
SOURCES = [
    ("bs-cs-bulletin", BULLETIN + "undergraduate/engineering/programs/computer-science-bs/",
     "Computer Science (BS), Tandon School of Engineering, NYU Bulletins: curriculum, total credits, "
     "Sample Plan of Study (canonical plan)", ".html"),
]
# Subjects of the courses named in the plan, in the bulletin's URL spelling.
SUBJECTS = ["cs_uy", "eg_uy", "expos_ua", "ma_uy"]


# Entry point: fetch the program page, then one description page per subject.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-11-14"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    for subj in SUBJECTS:
        # "cs_uy" -> "CS-UY", the subject as the plan writes it.
        fetch(SCHOOL.raw, f"courses-{subj}", f"{BULLETIN}courses/{subj}/",
              f"Course descriptions, subject {subj.upper().replace('_', '-')}, NYU Bulletins", today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
