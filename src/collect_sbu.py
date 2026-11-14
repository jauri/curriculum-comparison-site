"""Import Stony Brook's CS BS catalog pages into data/raw/sbu/ and log them in sources.csv.

Stony Brook University publishes its Fall 2026 Undergraduate Catalog on Acalog
(catalog.stonybrook.edu), which answers scripts with a bot challenge (HTTP 202, empty
body). As for Virginia Tech, the pages are saved through the user's Chrome as one JSON
bundle (sbu_bundle.json), built in an open program page by same-origin fetches:
- the "Computer Science, BS" program page (catoid 11, poid 1411): College of
  Engineering and Applied Sciences, requirements, and the "Sample Course Sequence"
  (Freshman through Senior, Fall and Spring), the canonical plan. The Fall 2026 edition
  is used, not the newer Spring 2027 one, as it is the catalog of students entering in
  Fall 2026 (decided with the user);
- the catalog entry of every course the program page links (preview_course_nopop.php),
  which holds that course's description;
- four entries for plan courses the program page names without a link (WRT 101,
  WRT 102, CSE 101, CSE 103), found with the catalog's own course search ("Best Match"
  for each code) and saved the same way.

This script imports the bundle with collect_common.import_bundle(): the program page
becomes <date>_bs-cs-catalog.html and each course entry courses/<date>_<CODE>.html.

Sources were reviewed and approved by the user before downloading (batch 4).

Usage:
    python src/collect_sbu.py --import-bundle ~/Downloads/sbu_bundle.json
"""

import argparse
from datetime import date
from pathlib import Path

from collect_common import acalog_namer, import_bundle
from common import load_school

SCHOOL = load_school("sbu")


# Manifest description for a bundle page.
def describe(page: dict) -> str:
    """Return the sources.csv description for one bundle page."""
    if "preview_program.php" in page["url"]:
        return ("Computer Science, BS, Fall 2026 Undergraduate Catalog (College of Engineering and Applied Sciences): requirements and Sample Course Sequence (canonical plan).")
    return f"Course entry, {page['code'].replace(chr(160), ' ')}, Fall 2026 Undergraduate Catalog."


# Entry point: import the Chrome-saved bundle.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--import-bundle", type=Path, required=True, help="path of sbu_bundle.json")
    args = parser.parse_args()
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-11-14"
    import_bundle(SCHOOL.raw, args.import_bundle.expanduser(), acalog_namer("bs-cs-catalog.html"), describe, today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
