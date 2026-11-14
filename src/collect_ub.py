"""Import Buffalo's CS BS catalog pages into data/raw/ub/ and log them in sources.csv.

The University at Buffalo publishes its 2026-2027 Undergraduate Catalog on Acalog
(catalogs.buffalo.edu), which answers scripts with a bot challenge (HTTP 202, empty
body). As for Virginia Tech, the pages are saved through the user's Chrome as one JSON
bundle (ub_bundle.json), built in an open program page by same-origin fetches:
- the "Computer Science BS" program page (catoid 21, poid 7950): requirements,
  120 credits, and the "Curricular Plan" (Year 1-4, Fall and Spring), the canonical plan;
- the catalog entry of every course the program page links (preview_course_nopop.php),
  which holds that course's description;
- in a second bundle (ub_extra_bundle.json), the entries of two plan courses the program
  page names without a link, ENG 105 and UBC 399, found with the catalog's own course
  search and saved the same way.

This script imports the bundle with collect_common.import_bundle(): the program page
becomes <date>_bs-cs-catalog.html and each course entry courses/<date>_<CODE>.html.

Sources were reviewed and approved by the user before downloading (batch 4).

Usage:
    python src/collect_ub.py --import-bundle ~/Downloads/ub_bundle.json
    python src/collect_ub.py --import-bundle ~/Downloads/ub_extra_bundle.json
"""

import argparse
from datetime import date
from pathlib import Path

from collect_common import acalog_namer, import_bundle
from common import load_school

SCHOOL = load_school("ub")


# Manifest description for a bundle page.
def describe(page: dict) -> str:
    """Return the sources.csv description for one bundle page."""
    if "preview_program.php" in page["url"]:
        return ("Computer Science BS, 2026-2027 Undergraduate Catalog: requirements, 120 credits, Curricular Plan (canonical plan).")
    return f"Course entry, {page['code'].replace(chr(160), ' ')}, 2026-2027 Undergraduate Catalog."


# Entry point: import the Chrome-saved bundle.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--import-bundle", type=Path, required=True, help="path of ub_bundle.json")
    args = parser.parse_args()
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-11-14"
    import_bundle(SCHOOL.raw, args.import_bundle.expanduser(), acalog_namer("bs-cs-catalog.html"), describe, today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
