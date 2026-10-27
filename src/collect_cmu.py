"""Download Carnegie Mellon's CS BS catalog pages into data/raw/cmu/ and log them in sources.csv.

CMU publishes its 2026-2027 Undergraduate Catalog as static CourseLeaf pages, so plain
GET requests are enough. The B.S. in Computer Science page (School of Computer Science)
holds the requirements "for students entering Fall 2026", the summary of degree
requirements (360 units), and the eight-semester "Sample Course Sequence".

CMU's catalog lists course descriptions one page per department rather than per
subject code. Each course named in the sample sequence or the core requirements
(07-, 15-, 21-, 76-, and 99- courses) is on one of four department pages, found by
checking each page's course blocks in step 13.

Sources were reviewed and approved by the user before downloading (step 13, batch 3).

Usage:
    python src/collect_cmu.py
"""

from datetime import date

from collect_common import fetch
from common import load_school

SCHOOL = load_school("cmu")
CATALOG = "https://coursecatalog.web.cmu.edu/"

# (slug, url, description, file extension).
SOURCES = [
    ("bs-cs-catalog",
     CATALOG + "schools-colleges/schoolofcomputerscience/undergraduatecomputerscience/computer-science-bs/",
     "B.S. in Computer Science, 2026-2027 catalog: requirements for students entering Fall 2026, 360-unit "
     "summary, Sample Course Sequence (canonical plan)", ".html"),
]
# Department course pages: slug -> (path, which plan courses it holds).
COURSE_PAGES = {
    "courses-scs": ("schools-colleges/schoolofcomputerscience/courses/", "07- and 15- courses"),
    "courses-math": ("schools-colleges/melloncollegeofscience/departmentofmathematicalsciences/courses/",
                     "21- courses"),
    "courses-english": ("schools-colleges/dietrichcollegeofhumanitiesandsocialsciences/departmentofenglish/courses/",
                        "76-101"),
    "courses-intercollege": ("intercollegeprograms/courses/", "99-101 Core@CMU"),
}


# Entry point: fetch the program page, then the four department course pages.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-10-17"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    for slug, (path, holds) in COURSE_PAGES.items():
        fetch(SCHOOL.raw, slug, CATALOG + path,
              f"Course descriptions, department page ({holds}), 2026-2027 catalog", today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
