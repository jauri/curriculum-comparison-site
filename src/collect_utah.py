"""Collect Utah's CS BS sources into data/raw/utah/ and log them in sources.csv.

The University of Utah's 2026-2027 General Catalog runs on Coursedog (catalog.utah.edu).
The Computer Science BS (program CPSCBS, effective 2026-08-17) has a "Sample Degree
Plans" tab whose "Computer Science Sample 4 Year Plan" (120 credits, 8 semesters) is the
canonical plan; the four emphasis plans on the same tab are not used. (Earlier in batch
4 the 2024-25 handbook plan was chosen because no 2026-27 plan had been found; the user
switched to this one once it was.)

The page builds the plan in the browser from the catalog app's own API, and both the
page's data file and the API answer scripts with HTTP 403. So, as for Virginia Tech, the
sources were saved through the user's Chrome as one JSON bundle (utah_bundle.json),
fetched in an open catalog page:
- the Sample Degree Plans page itself (catalog.utah.edu/programs/CPSCBS/...);
- the app's "programs" API response for CPSCBS (app.coursedog.com), which holds the
  degree maps, the college, and the program's effective date;
- the app's "courses" API response for the courses the page shows, with each course's
  code, title, credits, and description.
The bundle holds each API response twice (the page requested each twice); the second
copy has the same URL and name and is skipped.

One more source is a static PDF downloaded by script: the Kahlert School of Computing's
"Computer Science B.S. Degree - Requirements 2026-27" sheet (cs.utah.edu), which lists
the required CS core. parse_utah.py uses it to confirm that CS 4150 and CS 4400, which
the plan offers as "CS 4150 or CS 4400" in both Year 3 terms, are both required.

Usage:
    python src/collect_utah.py                                   # the requirements PDF
    python src/collect_utah.py --import-bundle ~/Downloads/utah_bundle.json
"""

import argparse
from datetime import date
from pathlib import Path

from collect_common import fetch, import_bundle
from common import load_school

SCHOOL = load_school("utah")
REQUIREMENTS_URL = "https://www.cs.utah.edu/wp-content/uploads/2026/07/CS-Requirements-26-27.pdf"
NAMES = {"plans-page": "cs-bs-sample-plans.html", "programs-api": "cs-bs-programs-api.json",
         "courses-api": "cs-bs-courses-api.json"}
DESCRIPTIONS = {
    "plans-page": "Computer Science BS (CPSCBS), Sample Degree Plans tab, 2026-2027 General Catalog (page only; the "
                  "plans load from the API)",
    "programs-api": "Coursedog catalog API, program CPSCBS (effective 2026-08-17): degree maps including the 'Computer "
                    "Science Sample 4 Year Plan' (canonical plan), college",
    "courses-api": "Coursedog catalog API, the courses shown on the Sample Degree Plans page: codes, titles, credits, "
                   "descriptions",
}


# Raw-folder name for a bundle page, by the "kind" the browser recorded.
def name_for(page: dict) -> str:
    """Return the file name (without date) for one bundle page."""
    return NAMES[page["kind"]]


# Manifest description for a bundle page.
def describe(page: dict) -> str:
    """Return the sources.csv description for one bundle page."""
    return DESCRIPTIONS[page["kind"]] + "."


# Entry point: import the Chrome-saved bundle.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--import-bundle", type=Path, help="path of utah_bundle.json saved through Chrome")
    args = parser.parse_args()
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-11-14"
    if args.import_bundle:
        import_bundle(SCHOOL.raw, args.import_bundle.expanduser(), name_for, describe, today)
    else:
        fetch(SCHOOL.raw, "cs-requirements-26-27", REQUIREMENTS_URL,
              "Computer Science B.S. Degree - Requirements 2026-27 (Kahlert School of Computing): required CS core",
              today, ".pdf")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
