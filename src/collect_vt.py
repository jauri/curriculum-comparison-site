"""Import Virginia Tech's CS BS catalog pages into data/raw/vt/ and log them in sources.csv.

Virginia Tech's 2026-2027 Academic Catalog is a CourseLeaf site, but it sits behind an
AWS bot filter that answers scripts with an empty "challenge" response (HTTP 202,
x-amzn-waf-action: challenge). Rather than disguise the script as a browser, the pages
are saved through the user's Chrome, as Berkeley's and Michigan's were: in an open
catalog page, a same-origin fetch() reads each page and the unchanged bytes go into one
JSON bundle (vt_bundle.json), downloaded once. This script imports the bundle with
collect_common.import_bundle(), giving each page the usual dated name and a manifest
row whose method is "browser".

The bundle holds:
- the Computer Science Major page (College of Engineering): program curriculum,
  123 total credits, and the "Roadmap" plan-of-study grid (canonical plan);
- one course-description page per subject named in the roadmap: CS, ENGE, ENGL, MATH,
  CMDA.

Sources were reviewed and approved by the user before downloading (step 13, batch 3).

Usage:
    python src/collect_vt.py --import-bundle ~/Downloads/vt_bundle.json
"""

import argparse
from datetime import date
from pathlib import Path

from collect_common import import_bundle
from common import load_school

SCHOOL = load_school("vt")
PROGRAM_URL = "https://catalog.vt.edu/undergraduate/college-engineering/computer-science/computer-science-bs/"


# Raw-folder name for a bundle page: the program page, or courses-<subject>.html for a
# course-description page (/course-descriptions/cs/ -> courses-cs.html).
def name_for(page: dict) -> str:
    """Return the file name (without date) for one bundle page."""
    if page["url"] == PROGRAM_URL:
        return "bs-cs-catalog.html"
    subject = page["url"].rstrip("/").rsplit("/", 1)[1]  # last path segment, e.g. "cs"
    return f"courses-{subject}.html"


# Manifest description for a bundle page.
def describe(page: dict) -> str:
    """Return the sources.csv description for one bundle page."""
    if page["url"] == PROGRAM_URL:
        return ("Computer Science Major, 2026-2027 Academic Catalog (College of Engineering): program "
                "curriculum, 123 credits, Roadmap plan of study (canonical plan).")
    subject = page["url"].rstrip("/").rsplit("/", 1)[1].upper()
    return f"Course descriptions, subject {subject}, 2026-2027 Academic Catalog."


# Entry point: import the Chrome-saved bundle.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--import-bundle", type=Path, required=True, help="path of vt_bundle.json")
    args = parser.parse_args()
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-10-17"
    import_bundle(SCHOOL.raw, args.import_bundle.expanduser(), name_for, describe, today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
