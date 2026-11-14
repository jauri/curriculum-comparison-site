"""Import Kentucky's CS BS catalog pages into data/raw/uky/ and log them in sources.csv.

The University of Kentucky publishes its 2026-2027 Undergraduate Catalog on
Acalog (catalogs.uky.edu), which answers scripts with a bot challenge (HTTP 202, empty
body). As for Virginia Tech, the pages are saved through the user's Chrome as one JSON
bundle (uky_bundle.json), built in an open program page by same-origin fetches:
- the "Computer Science, B.S." program page (catoid 22, poid 11580): Stanley and
  Karen Pigman College of Engineering, 128 total hours, and the "Curriculum" (Freshman
  through Senior Year, First and Second Semester), the canonical plan;
- the catalog entry of every course the program page links (preview_course_nopop.php),
  which holds that course's description;
- in a second bundle (uky_college_bundle.json), the Pigman College of Engineering's
  catalog page, which lists the program; the program page itself does not name the
  college.

This script imports the bundle with collect_common.import_bundle(): the program page
becomes <date>_bs-cs-catalog.html and each course entry courses/<date>_<CODE>.html.

Sources were reviewed and approved by the user before downloading (batch 4).

Usage:
    python src/collect_uky.py --import-bundle ~/Downloads/uky_bundle.json
    python src/collect_uky.py --import-bundle ~/Downloads/uky_college_bundle.json
"""

import argparse
from datetime import date
from pathlib import Path

from collect_common import acalog_namer, import_bundle
from common import load_school

SCHOOL = load_school("uky")


# The program page does not name its college, so the college's own catalog page (which
# lists "Computer Science, B.S." among its programs) is saved too, in a second bundle
# (uky_college_bundle.json; Chrome allows one download per tab).
COLLEGE_URL = "https://catalogs.uky.edu/content.php?catoid=22&navoid=1310"
program_namer = acalog_namer("bs-cs-catalog.html")


# Raw-folder name for a bundle page: the college page, or the shared Acalog names.
def name_for(page: dict) -> str:
    """Return the file name (without date) for one bundle page."""
    return "college-programs.html" if page["url"] == COLLEGE_URL else program_namer(page)


# Manifest description for a bundle page.
def describe(page: dict) -> str:
    """Return the sources.csv description for one bundle page."""
    if page["url"] == COLLEGE_URL:
        return ("Stanley and Karen Pigman College of Engineering page, 2026-2027 Undergraduate Catalog: lists the "
                "college's programs, including Computer Science, B.S. (college source).")
    if "preview_program.php" in page["url"]:
        return ("Computer Science, B.S., 2026-2027 Undergraduate Catalog (Pigman College of Engineering): requirements, 128 hours, eight-semester Curriculum (canonical plan).")
    return f"Course entry, {page['code'].replace(chr(160), ' ')}, 2026-2027 Undergraduate Catalog."


# Entry point: import the Chrome-saved bundle.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--import-bundle", type=Path, required=True,
                        help="path of uky_bundle.json or uky_college_bundle.json")
    args = parser.parse_args()
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-11-14"
    import_bundle(SCHOOL.raw, args.import_bundle.expanduser(), name_for, describe, today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
