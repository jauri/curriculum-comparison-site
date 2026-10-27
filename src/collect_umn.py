"""Download Minnesota's CS BS sources into data/raw/umn/ and log them in sources.csv.

Three kinds of source, all plain GET requests:

1. The plan of study: the College of Science and Engineering's "Computer Science
   Four-Year Plan" page (cse.umn.edu, revised 03/2026), a static Drupal page with one
   <ul> of courses per semester.
2. The catalog program page: the UMN Twin Cities catalog runs on Coursedog, which
   renders /programs/<id> on the server and embeds the program's full data (college,
   degree credit minimum, requirement rules) as JSON in a <script id="__NUXT_DATA__">
   tag. The visible requirement lists are filled in later by JavaScript, so the parser
   reads that JSON.
3. Course descriptions: /courses/<id> pages, also server-rendered with the course's data
   (code, title, credits, description) in the same kind of JSON. The ids come from the
   catalog's course search, which fills in its results with JavaScript; they were looked
   up in Chrome in step 13 and are listed in COURSE_IDS (the same approach as Berkeley).
   Each page is about 2.7 MB because it embeds the whole app state, which is why the
   folder is large.

Sources were reviewed and approved by the user before downloading (step 13, batch 2).

Usage:
    python src/collect_umn.py
"""

import time
from datetime import date

import requests

from collect_common import HEADERS, fetch, save
from common import load_school

SCHOOL = load_school("umn")
CATALOG = "https://umtc.catalog.prod.coursedog.com/"

# (slug, url, description, file extension).
SOURCES = [
    ("cs-four-year-plan", "https://cse.umn.edu/college/four-year-plans/computer-science-four-year-plan",
     "Computer Science Four-Year Plan (B.S.), College of Science and Engineering, revised 03/2026 (canonical plan)",
     ".html"),
    ("cs-bs-program", CATALOG + "programs/019627107",
     "Computer Science B.S. program page, UMN Twin Cities catalog (Coursedog): college, degree credit minimum, "
     "requirement rules in the embedded JSON", ".html"),
]
# Course code -> Coursedog course group id, for every course named in the four-year plan.
COURSE_IDS = {
    "MATH 1371": "0036921", "MATH 1372": "0036931", "PHYS 1301W": "0020701", "CSE 1001": "8071661",
    "WRIT 1301": "8003721", "CSCI 1133": "8096661", "STAT 3021": "0016221", "CSCI 2011": "0036721",
    "CSCI 1933": "8103461", "CSCI 2021": "0036731", "CSCI 2033": "8051471", "CSCI 2041": "8103471",
    "CSCI 3081W": "7930761", "CSCI 4041": "0036751", "CSCI 3923": "8263851", "CSCI 4061": "0021871",
}


# Download one catalog page per course, named by course code (spaces removed).
def fetch_courses(today: str) -> None:
    """Fetch every course page in COURSE_IDS into data/raw/umn/courses/."""
    for code, cid in COURSE_IDS.items():
        name = f"courses/{today}_{code.replace(' ', '')}.html"
        if (SCHOOL.raw / name).exists():
            print(f"skip   {name} (already saved today)")
            continue
        resp = requests.get(CATALOG + "courses/" + cid, headers=HEADERS, timeout=60)
        resp.raise_for_status()  # never save an error page as a source
        save(SCHOOL.raw, name, CATALOG + "courses/" + cid, f"Course page, {code}, UMN Twin Cities catalog",
             "script", resp, today)
        time.sleep(1)  # be gentle: one request a second to a server built for people


# Entry point: the plan and program pages, then the course pages.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-10-17"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    fetch_courses(today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
