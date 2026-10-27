"""Save Michigan's CS-Eng (BSE) sources into data/raw/umich/ and log them in sources.csv.

Two kinds of source, collected two ways:

1. The plan of study: the College of Engineering Bulletin's "FA26 CS-Eng Sample
   Schedule" PDF (for students entering Fall 2026; dated 5.7.26). Files under the
   bulletin's /wp-content/uploads/ answer scripts normally, so it is a plain GET.
2. Bulletin HTML pages: the EECS program page (names the B.S.E. (C.S.) degree and links
   the sample schedule) and the course guides for EECS, ENGR, and TCHNCLCM. The bulletin
   answers scripts with HTTP 403, so these pages are saved through the user's Chrome,
   the way Berkeley's plan page was: a same-origin fetch() in the open page reads the
   server's response and the unchanged bytes are downloaded as umich_<slug>.html. This
   script then imports them (`--import-dir ~/Downloads`), copying each into
   data/raw/umich/ with the usual dated name and a manifest row whose method is
   "browser". Pages not in the folder are skipped, so a later import can add them.

In step 13 Chrome saved umich_eecs.html and umich_courses-eecs.html, then blocked
further automatic downloads from the site, so the ENGR and TCHNCLCM guides were not
saved; those courses use generic descriptions until they are imported.

MATH, PHYS, CHEM, and STATS descriptions are in LSA's course guide, which requires a
U-M login, so they are not collected (generic descriptions, decided with the user).

Sources were reviewed and approved by the user before downloading (step 13, batch 2).

Usage:
    python src/collect_umich.py --import-dir ~/Downloads
    python src/collect_umich.py            # the sample schedule PDF only
"""

import argparse
from datetime import date
from pathlib import Path

from collect_common import fetch, save_bytes
from common import load_school

SCHOOL = load_school("umich")
BULLETIN = "https://bulletin.engin.umich.edu/"
PLAN_URL = BULLETIN + "wp-content/uploads/sites/306/2026/05/FA26-CS-Eng-Sample-Schedule_5.7.26.pdf"

# Browser-saved pages: slug -> (url, description). The downloaded file is umich_<slug>.html.
BROWSER_PAGES = {
    "eecs": (BULLETIN + "eecs/",
             "EECS department page, College of Engineering Bulletin: degree programs incl. B.S.E. (C.S.) and "
             "links to the FA26 sample schedules"),
    "courses-eecs": (BULLETIN + "courses/eecs/", "Course guide, Electrical Engineering and Computer Science (EECS)"),
    "courses-engr": (BULLETIN + "courses/engr/", "Course guide, Engineering Division (ENGR)"),
    "courses-techcomm": (BULLETIN + "courses/techcomm/", "Course guide, Technical Communication (TCHNCLCM)"),
}
BROWSER_NOTE = " Saved through Chrome (same-origin fetch, unchanged bytes) because the site returns 403 to scripts."


# Copy each browser-downloaded page found in `folder` into the raw folder and log it.
# The file is read as bytes and written unchanged, so its SHA-256 matches the download.
def import_pages(folder: Path, today: str) -> None:
    """Import every umich_<slug>.html in folder that matches BROWSER_PAGES."""
    for slug, (url, description) in BROWSER_PAGES.items():
        src = folder / f"umich_{slug}.html"
        if not src.exists():
            print(f"missing {src.name} (not imported)")
            continue
        save_bytes(SCHOOL.raw, f"{today}_{slug}.html", url, description + BROWSER_NOTE, "browser",
                   src.read_bytes(), 200, today)


# Entry point: the sample schedule PDF, then any browser-saved pages.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--import-dir", type=Path, help="folder holding the pages downloaded through Chrome")
    args = parser.parse_args()
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-10-17"
    fetch(SCHOOL.raw, "cs-eng-sample-schedule-fa26", PLAN_URL,
          "FA26 CS-Eng Sample Schedule (B.S.E. in Computer Science), College of Engineering Bulletin: eight-term "
          "plan, 128 credits, notes (canonical plan)", today, ".pdf")
    if args.import_dir:
        import_pages(args.import_dir.expanduser(), today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
