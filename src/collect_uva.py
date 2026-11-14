"""Collect UVA's CS BS sources into data/raw/uva/ and log them in sources.csv.

UVA's 2026-2027 Undergraduate Record lists the BS in Computer Science's requirements
(School of Engineering and Applied Science, 126 credits) but has no semester plan. The
only semester-by-semester plan is the CS department advising site's "Example BSCS
Semester Outline - 2024-2025 Academic Year", which is used (decided with the user,
Georgia Tech's precedent for an older-year plan). Two kinds of source, saved two ways:

- By script (static files on uvacsadvising.org): the 2024-25 example outline (canonical
  plan) and the current BSCS requirements checklist, which is used to check that the
  2024-25 outline still names the current required courses.
- Through the user's Chrome (the Record is an Acalog catalog that answers scripts with a
  bot challenge), as one JSON bundle imported with --import-bundle: the Record's
  "Computer Science, B.S." program page (catoid 72, poid 11700; college, 126 credits,
  requirements), the entry of every course it links, and the entry for ECE 2200, a plan
  course the program page names without a link (found with the Record's own search).

Sources were reviewed and approved by the user before downloading (batch 4).

Usage:
    python src/collect_uva.py                                    # the two PDFs
    python src/collect_uva.py --import-bundle ~/Downloads/uva_bundle.json
"""

import argparse
from datetime import date
from pathlib import Path

from collect_common import acalog_namer, fetch, import_bundle
from common import load_school

SCHOOL = load_school("uva")
ADVISING = "https://uvacsadvising.org/materials/"
# (slug, url, description, file extension).
SOURCES = [
    ("bscs-example-schedule-2024-25", ADVISING + "bscs-example-schedule.pdf",
     "Example BSCS Semester Outline - 2024-2025 Academic Year (UVA CS advising): eight semesters, 126 credits "
     "(canonical plan)", ".pdf"),
    ("bscs-checklist", ADVISING + "uva-bscs-checklist.pdf",
     "BSCS requirements checklist, current (UVA CS advising): used to check the 2024-25 outline's required courses",
     ".pdf"),
]


# Manifest description for a bundle page.
def describe(page: dict) -> str:
    """Return the sources.csv description for one bundle page."""
    if "preview_program.php" in page["url"]:
        return ("Computer Science, B.S., Undergraduate Record 2026-2027 (School of Engineering and Applied Science): "
                "requirements, 126 credits (college and credits source).")
    return f"Course entry, {page['code'].replace(chr(160), ' ')}, Undergraduate Record 2026-2027."


# Entry point: download the PDFs, or import the Chrome bundle when one is given.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--import-bundle", type=Path, help="path of uva_bundle.json saved through Chrome")
    args = parser.parse_args()
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-11-14"
    if args.import_bundle:
        import_bundle(SCHOOL.raw, args.import_bundle.expanduser(), acalog_namer("bs-cs-record.html"), describe, today)
    else:
        for slug, url, description, ext in SOURCES:
            fetch(SCHOOL.raw, slug, url, description, today, ext)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
