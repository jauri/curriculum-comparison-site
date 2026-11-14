"""Import Tennessee's CS BS catalog pages into data/raw/utk/ and log them in sources.csv.

The University of Tennessee, Knoxville publishes its 2026-2027 Undergraduate Catalog on
Acalog (catalog.utk.edu), which answers scripts with a bot challenge (HTTP 202, empty
body). As for Virginia Tech, the pages are saved through the user's Chrome as one JSON
bundle (utk_bundle.json), built in an open program page by same-origin fetches:
- the "Computer Science Major, BS in Computer Science" program page (catoid 56,
  poid 35734): Tickle College of Engineering, requirements, and the Academic Map
  (Terms 1-8), the canonical plan;
- the catalog entry of every course the program page links (preview_course_nopop.php),
  which holds that course's description.

This script imports the bundle with collect_common.import_bundle(): the program page
becomes <date>_bs-cs-catalog.html and each course entry courses/<date>_<CODE>.html.

Sources were reviewed and approved by the user before downloading (batch 4).

Usage:
    python src/collect_utk.py --import-bundle ~/Downloads/utk_bundle.json
"""

import argparse
from datetime import date
from pathlib import Path

from collect_common import acalog_namer, import_bundle
from common import load_school

SCHOOL = load_school("utk")


# Manifest description for a bundle page.
def describe(page: dict) -> str:
    """Return the sources.csv description for one bundle page."""
    if "preview_program.php" in page["url"]:
        return ("Computer Science Major, BS in Computer Science, 2026-2027 Undergraduate Catalog (Tickle College "
                "of Engineering): requirements and Academic Map (canonical plan).")
    return f"Course entry, {page['code'].replace(chr(160), ' ')}, 2026-2027 Undergraduate Catalog."


# Entry point: import the Chrome-saved bundle.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--import-bundle", type=Path, required=True, help="path of utk_bundle.json")
    args = parser.parse_args()
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-11-14"
    import_bundle(SCHOOL.raw, args.import_bundle.expanduser(), acalog_namer("bs-cs-catalog.html"), describe, today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
