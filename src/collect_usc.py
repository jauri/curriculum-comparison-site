"""Collect USC's CS BS sources into data/raw/usc/ and log them in sources.csv.

USC's 2026-2027 Catalogue lists the Computer Science (BS) requirements (Viterbi School of
Engineering, 128 units) but no semester plan. The plan comes from the Viterbi admission
office's 2026 guide, whose Computer Science pages show two four-year grids, "Begin with
CSCI 102" and "Begin with CSCI 103". The CSCI 102 grid, for students without AP credit,
is the canonical plan (decided with the user). Two kinds of source, saved two ways:

- By script: the 2026 guide's Computer Science curriculum PDF (viterbiadmission.usc.edu).
  Its grids are images, not text, so parse_usc.py reads a transcription of the grid
  (data/reference/usc/plan_transcription.csv) that names this PDF as its source.
- Through the user's Chrome (the Catalogue is Acalog and answers scripts with a bot
  challenge), as one JSON bundle imported with --import-bundle: the Catalogue's
  "Computer Science (BS)" program page (catoid 22, poid 32086; college, 128 units,
  requirements), the entry of every course it links, and entries for plan courses the
  page names without a link, found with the Catalogue's own search.

Sources were reviewed and approved by the user before downloading (batch 5).

Usage:
    python src/collect_usc.py                                    # the guide PDF
    python src/collect_usc.py --import-bundle ~/Downloads/usc_bundle.json
"""

import argparse
from datetime import date
from pathlib import Path

from collect_common import acalog_namer, fetch, import_bundle
from common import load_school

SCHOOL = load_school("usc")
# (slug, url, description, file extension).
SOURCES = [
    ("cs-curriculum-2026", "https://viterbiadmission.usc.edu/wp-content/uploads/2026/06/CS_Curriculum_2026.pdf",
     "Viterbi 2026 guide, Computer Science curriculum pages: course tracks and four-year grids 'Begin with "
     "CSCI 102' (canonical plan, no AP credit) and 'Begin with CSCI 103'", ".pdf"),
]


# Manifest description for a bundle page.
def describe(page: dict) -> str:
    """Return the sources.csv description for one bundle page."""
    if "preview_program.php" in page["url"]:
        return ("Computer Science (BS), USC Catalogue 2026-2027 (Viterbi School of Engineering): requirements, "
                "128 units (college and credits source).")
    return f"Course entry, {page['code'].replace(chr(160), ' ')}, USC Catalogue 2026-2027."


# Entry point: download the guide PDF, or import the Chrome bundle when one is given.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--import-bundle", type=Path, help="path of usc_bundle.json saved through Chrome")
    args = parser.parse_args()
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-11-14"
    if args.import_bundle:
        import_bundle(SCHOOL.raw, args.import_bundle.expanduser(), acalog_namer("bs-cs-catalogue.html"), describe, today)
    else:
        for slug, url, description, ext in SOURCES:
            fetch(SCHOOL.raw, slug, url, description, today, ext)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
