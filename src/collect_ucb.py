"""Save UC Berkeley's EECS BS sources into data/raw/ucb/ and log them in sources.csv.

Two kinds of source, collected two ways:

1. The plan of study: the Berkeley Engineering Undergraduate Guide page for EECS, with
   the "2026-2027 Freshman Undergraduate Program" table. engineering.berkeley.edu
   answers scripts with HTTP 403, so the page is saved through the user's Chrome
   instead: a same-origin fetch() in the open page reads the server's response, and the
   unchanged bytes are downloaded as a file. This script then imports that file
   (`--import-plan <path>`), copying it into data/raw/ucb/ with the usual dated name and
   a manifest row whose method is "browser".
2. Course descriptions: Berkeley's catalog (undergraduate.catalog.berkeley.edu, run on
   Coursedog) renders each course page on the server, so a plain GET of
   /courses/<id> returns the description. The ids come from the catalog's search page,
   which fills in its results with JavaScript; they were looked up in Chrome in step 13
   and are listed in COURSE_IDS. Each page is about 1.4 MB because it embeds the whole
   app state, which is why the folder is larger than other schools'.

Sources were reviewed and approved by the user before downloading (step 13).

Usage:
    python src/collect_ucb.py --import-plan ~/Downloads/ucb_eecs-major-program.html
    python src/collect_ucb.py            # course pages only
"""

import argparse
import time
from datetime import date
from pathlib import Path

import requests

from collect_common import HEADERS, save, save_bytes
from common import load_school

SCHOOL = load_school("ucb")
# The guide's old address (/students/undergraduate-guide/...) redirects here.
PLAN_URL = ("https://engineering.berkeley.edu/academics/undergraduate-programs/"
            "electrical-engineering-computer-sciences/")
CATALOG = "https://undergraduate.catalog.berkeley.edu/courses/"

# Course code -> Coursedog course id, for every course named in the freshman program
# (including both sides of each "or"). COMPSCI 61CL is named in the program but isn't
# in the 2026-27 catalog (a search for it finds nothing), so it has no id here.
COURSE_IDS = {
    "COMPSCI 61A": "1044241", "COMPSCI 61B": "1044261", "COMPSCI 61BL": "1044271",
    "COMPSCI 61C": "1044281", "COMPSCI 70": "1044331",
    "MATH 51": "1144962", "MATH 52": "1145002", "MATH 53": "1147021", "MATH 54": "1147051",
    "ELENG 64": "1063282", "ELENG 66": "1063272",
    "PHYSICS 7A": "1184911", "PHYSICS 7B": "1184921",
    "PHYSICS 5A": "1254291", "PHYSICS 5B": "1254301", "PHYSICS 5BL": "1254311",
}


# Copy the browser-downloaded plan page into the raw folder and log it. The file is
# read as bytes and written unchanged, so its SHA-256 matches what the browser saved.
def import_plan(src: Path, today: str) -> None:
    """Save the Chrome-downloaded EECS program page as <today>_eecs-major-program.html."""
    save_bytes(SCHOOL.raw, f"{today}_eecs-major-program.html", PLAN_URL,
               "EECS major program page, Berkeley Engineering Undergraduate Guide: 2026-2027 freshman "
               "program table, notes, 120-unit minimum (canonical plan). Saved through Chrome "
               "(same-origin fetch, unchanged bytes) because the site returns 403 to scripts.",
               "browser", src.read_bytes(), 200, today)


# Download one catalog page per course, named by course code (spaces removed).
def fetch_courses(today: str) -> None:
    """Fetch every course page in COURSE_IDS into data/raw/ucb/courses/."""
    for code, cid in COURSE_IDS.items():
        name = f"courses/{today}_{code.replace(' ', '')}.html"
        if (SCHOOL.raw / name).exists():
            print(f"skip   {name} (already saved today)")
            continue
        resp = requests.get(CATALOG + cid, headers=HEADERS, timeout=60)
        resp.raise_for_status()  # never save an error page as a source
        save(SCHOOL.raw, name, CATALOG + cid, f"Course page, {code}, UC Berkeley catalog 2026-27",
             "script", resp, today)
        time.sleep(1)  # be gentle: one request a second to a server built for people


# Entry point: optional plan import, then the course pages.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--import-plan", type=Path, help="path of the program page downloaded through Chrome")
    args = parser.parse_args()
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-10-17"
    if args.import_plan:
        import_plan(args.import_plan.expanduser(), today)
    fetch_courses(today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
