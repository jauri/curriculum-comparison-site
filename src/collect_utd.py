"""Download UT Dallas's CS BS catalog pages into data/raw/utd/ and log them in sources.csv.

UT Dallas publishes its 2026 Undergraduate Catalog as static pages, so plain GET
requests are enough. Two program pages are saved:
- the "4-Year Plan Example" for the Computer Science BS (canonical plan);
- the Computer Science BS degree-requirements page, which names the Erik Jonsson School
  of Engineering and Computer Science and states the 124 semester credit hours.

UT Dallas has one catalog page per course (/courses/cs1337), not one per subject. The
course list is read from the saved plan page itself: every course code in its grid
("CS 1337", "MATH 2417") gets its page. Reading the codes from the saved file, rather
than typing them here, keeps the list traceable to the source.

Sources were reviewed and approved by the user before downloading (batch 4).

Usage:
    python src/collect_utd.py
"""

import re
from datetime import date

import requests
from bs4 import BeautifulSoup

from collect_common import HEADERS, fetch, save
from common import load_school

SCHOOL = load_school("utd")
CATALOG = "https://catalog.utdallas.edu/2026/undergraduate/"

# (slug, url, description, file extension).
SOURCES = [
    ("bs-cs-four-year", CATALOG + "programs/ecs/computer-science/four-year",
     "Computer Science (BS) 4-Year Plan Example, 2026 Undergraduate Catalog (canonical plan)", ".html"),
    ("bs-cs-program", CATALOG + "programs/ecs/computer-science",
     "Computer Science (BS) degree requirements, 2026 Undergraduate Catalog: Erik Jonsson School of "
     "Engineering and Computer Science, 124 semester credit hours", ".html"),
]
# Plan codes that are typos, and the course the degree requirements name instead. The
# plan's "CS 3337" has an empty catalog page, and the requirements page lists CS 3377
# (Systems Programming in UNIX) in its place; parse_utd.py applies the same correction
# and checks it against the requirements page.
PLAN_TYPOS = {"CS 3337": "CS 3377"}
# A UTD course code: 2-4 capital letters, a space, 4 digits (e.g. "CS 1337", "ECS 1100").
CODE = re.compile(r"\b([A-Z]{2,4}) (\d{4})\b")


# Course codes in the saved plan grid, in order of first appearance. Only the plan's
# tables are read, so codes in the footnotes ("Core 090") are not mistaken for courses.
def plan_codes() -> list[str]:
    """Return the distinct course codes in the newest saved plan page."""
    soup = BeautifulSoup(SCHOOL.newest("*_bs-cs-four-year.html").read_text(encoding="utf-8"), "html.parser")
    text = " ".join(t.get_text(" ") for t in soup.find_all("table"))
    # dict.fromkeys keeps first-seen order while dropping repeats.
    return list(dict.fromkeys(f"{s} {n}" for s, n in CODE.findall(text)))


# Entry point: fetch the two program pages, then one page per plan course.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-11-13"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    # The corrected codes are fetched too (the typo's empty page was saved on 2026-11-13).
    for code in plan_codes() + list(PLAN_TYPOS.values()):
        key = code.replace(" ", "")  # "CS 1337" -> "CS1337"
        if (SCHOOL.raw / f"courses/{today}_{key}.html").exists():
            print(f"skip   courses/{today}_{key}.html (already saved today)")
            continue  # skip before requesting, so reruns don't contact the server
        fetch_course(key, code, today)


# Fetch one course page into courses/<date>_<CODE>.html. fetch() always names a file
# "<date>_<slug>" at the top of the raw folder, so course pages (kept in a subfolder,
# Berkeley's layout) are requested here and stored with save(), which takes a full name.
def fetch_course(key: str, code: str, today: str) -> None:
    """Download one UTD course page into data/raw/utd/courses/."""
    url = f"{CATALOG}courses/{key.lower()}"
    resp = requests.get(url, headers=HEADERS, timeout=30)  # timeout: never hang on a dead server
    resp.raise_for_status()  # an error page is never saved as a source
    save(SCHOOL.raw, f"courses/{today}_{key}.html", url,
         f"Course description, {code}, 2026 Undergraduate Catalog", "script", resp, today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
