"""Collect UConn's CS BS sources into data/raw/uconn/ and log them in sources.csv.

Two kinds of source, saved two ways:

- The College of Engineering's "Computer Science (BS), Catalog Year 2026-2027" common
  map (Storrs) is a static PDF on the advising site, downloaded by script. It is the
  canonical plan: eight semesters and the 120-credit total. (A separate Stamford map
  exists; the Storrs campus is used, as Penn State's University Park plan is.)
- The 2026-2027 Academic Catalog (CourseLeaf) answers scripts with a bot challenge
  (HTTP 202, empty body), so, as for Virginia Tech, its pages are saved through the
  user's Chrome as one JSON bundle and imported here with --import-bundle:
  the Computer Science (BS) program page (college, requirements) and one course page
  per subject named in the map: CSE, MATH, ENGR, ENGL.

Sources were reviewed and approved by the user before downloading (batch 4).

Usage:
    python src/collect_uconn.py                                   # the map PDF
    python src/collect_uconn.py --import-bundle ~/Downloads/uconn_bundle.json
"""

import argparse
from datetime import date
from pathlib import Path

from collect_common import fetch, import_bundle
from common import load_school

SCHOOL = load_school("uconn")
MAP_URL = ("https://advising-engineering.media.uconn.edu/wp-content/uploads/sites/3638/2026/05/"
           "CS-26-27-Common-Map.pdf")
PROGRAM_URL = "https://catalog.uconn.edu/undergraduate/engineering/computer-science-bs/"


# Raw-folder name for a bundle page: the program page, or courses-<subject>.html for a
# subject page (/undergraduate/courses/cse/ -> courses-cse.html).
def name_for(page: dict) -> str:
    """Return the file name (without date) for one bundle page."""
    if page["url"] == PROGRAM_URL:
        return "bs-cs-catalog.html"
    subject = page["url"].rstrip("/").rsplit("/", 1)[1]  # last path segment, e.g. "cse"
    return f"courses-{subject}.html"


# Manifest description for a bundle page.
def describe(page: dict) -> str:
    """Return the sources.csv description for one bundle page."""
    if page["url"] == PROGRAM_URL:
        return "Computer Science (BS), 2026-2027 Academic Catalog (College of Engineering): requirements, 120 credits."
    subject = page["url"].rstrip("/").rsplit("/", 1)[1].upper()
    return f"Course descriptions, subject {subject}, 2026-2027 Academic Catalog."


# Entry point: download the map, or import the Chrome bundle when one is given.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--import-bundle", type=Path, help="path of uconn_bundle.json saved through Chrome")
    args = parser.parse_args()
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-11-13"
    if args.import_bundle:
        import_bundle(SCHOOL.raw, args.import_bundle.expanduser(), name_for, describe, today)
    else:
        fetch(SCHOOL.raw, "cs-common-map-26-27", MAP_URL,
              "Computer Science (BS) common map, Catalog Year 2026-2027, Storrs (College of Engineering "
              "advising): eight semesters, 120 credits (canonical plan)", today, ".pdf")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
