"""Download official UC course detail pages (with descriptions) into data/raw/uc/courses/.

UC has no static public course catalog. Official descriptions are in the Catalyst
"Browse Course Catalog" (PeopleSoft Community Access, no login needed), which is driven
by form POSTs rather than per-course URLs. This script replays the same clicks a person
would make in the browser:

    letter (e.g. C) -> subject (CS) -> course number (2028C) -> [offering, if several]

and saves the resulting course detail page unchanged as
data/raw/uc/courses/YYYY-MM-DD_catalyst_CS2028C.html, with a row in
data/raw/uc/sources.csv.

The course list is read from the saved Section I major map (see collect_uc.py), so every
course looked up traces back to the plan of study. Run collect_uc.py first.

Usage:
    python src/collect_uc_courses.py
"""

import hashlib
import re
import time
from datetime import date

import requests
from bs4 import BeautifulSoup

# Reuse the paths, headers, and manifest writer from collect_uc.py so both scripts
# save files in the same layout and log to the same sources.csv.
from collect_uc import COURSES_DIR, HEADERS, RAW_DIR, append_manifest

# The one URL the whole catalog lives behind. Every "click" is a POST to this same
# address; the server tracks where you are through hidden form fields, not the URL.
CATALOG_URL = (
    "https://classes.catalyst-services.uc.edu/psc/psclass/EMPLOYEE/SA/c/"
    "COMMUNITY_ACCESS.SSS_BROWSE_CATLG.GBL"
)
# A UC course code: 2-4 capital letters (subject), then 4 digits, then an optional
# letter suffix (e.g. the "C" in CS2028C). The two capture groups split it into
# (subject, number). \b (word boundary) stops matches inside longer tokens.
COURSE_CODE = re.compile(r"\b([A-Z]{2,4})(\d{4}[A-Z]?)\b")

# When a course has several offerings (one per college), prefer CEAS, and never pick a
# regional campus (Blue Ash, Clermont) when a main-campus offering exists.
PREFERRED_GROUP = "College of Eng & Appl Sci"
REGIONAL_GROUPS = ("Blue Ash College", "Clermont College")

DELAY_SECONDS = 1.0  # be polite to UC's server


# Build the list of courses to look up by scanning the saved Section I plan of study
# for anything shaped like a course code. Reading the raw file (instead of hard-coding
# a list) means the lookups always match the plan that was actually downloaded.
# - sorted(...glob(...))[-1] picks the newest snapshot: filenames start with an ISO
#   date, so alphabetical order is also chronological order.
# - get_text(" ") strips the HTML tags, so the regex only sees visible page text; the
#   " " separator keeps text from adjacent tags from running together.
# - set() removes duplicates (a code can appear more than once on the page).
def plan_courses() -> list[tuple[str, str]]:
    """Return sorted unique (subject, number) pairs from the newest Section I major map."""
    maps = sorted(RAW_DIR.glob("*_cs-bs-majormap-class2031-sec1.html"))
    if not maps:
        raise SystemExit("No Section I major map in data/raw/uc/; run collect_uc.py first.")  # exits with a message instead of a traceback
    text = BeautifulSoup(maps[-1].read_text(encoding="utf-8"), "html.parser").get_text(" ")
    return sorted(set(COURSE_CODE.findall(text)))  # findall returns (subject, number) tuples because the regex has two groups


# A small "headless browser" for the PeopleSoft catalog.
# PeopleSoft pages are stateful: every page is one big HTML <form>, and clicking a link
# runs JavaScript that submits that form with a hidden field, ICAction, set to the ID of
# the thing clicked. Other hidden fields (such as ICSID and ICStateNum) tell the server
# which session and which step you're on. To "click" without a browser, we copy every
# input from the current page, set ICAction, and POST it back. The response becomes
# the new current page.
class CatalogSession:
    """Replays PeopleSoft form posts: each post sends the page's hidden fields + ICAction."""

    # Start a fresh session by loading the catalog's first page. requests.Session keeps
    # cookies between requests, which PeopleSoft needs to connect the later POSTs to
    # this same visit.
    def __init__(self) -> None:
        self.http = requests.Session()
        self.http.headers.update(HEADERS)  # send our User-Agent on every request in this session
        self.html = self._send(self.http.get(CATALOG_URL, timeout=30))

    # Shared handling for every response: fail loudly on HTTP errors, pause so we don't
    # flood UC's server, and return the page HTML.
    def _send(self, resp: requests.Response) -> str:
        resp.raise_for_status()
        time.sleep(DELAY_SECONDS)  # rate limiting: at most about one request per second
        return resp.text

    # Parse the current page so it can be searched for links and form fields.
    def soup(self) -> BeautifulSoup:
        return BeautifulSoup(self.html, "html.parser")

    # Simulate clicking the element whose ID is `action`. This is what the page's own
    # JavaScript does: resubmit the form with every current input value and ICAction
    # set to the clicked element. Buttons, submits, and checkboxes are skipped because
    # a browser wouldn't send them unless they were the thing being clicked or checked.
    def click(self, action: str) -> None:
        form = self.soup().find("form")
        # Dict comprehension: {name: value} for every named <input> on the form.
        # inp.get("value", "") falls back to "" for inputs with no value attribute.
        data = {
            inp["name"]: inp.get("value", "")
            for inp in form.find_all("input")
            if inp.get("name") and inp.get("type") not in ("button", "submit", "checkbox")
        }
        data["ICAction"] = action
        self.html = self._send(self.http.post(CATALOG_URL, data=data, timeout=30))  # data= sends the dict form-encoded, as a browser would

    # Find the first link on the current page that matches a condition, and return its
    # ID (which is what click() needs). `predicate` is a function taking (id, visible
    # text) and returning True for a match, so callers can match on either one. Returns
    # None if nothing matches.
    def link_id(self, predicate) -> str | None:
        for a in self.soup().find_all("a"):
            if a.get("id") and predicate(a.get("id"), a.get_text(" ", strip=True)):
                return a["id"]
        return None


# Some courses are offered by several colleges (e.g. ENGL1001 by Arts & Sciences, Blue
# Ash, and Clermont), and PeopleSoft asks which one you want. Each offering row has
# links with IDs like ACAD_GROUP$0, ACAD_GROUP$1, ... where the number is the row index.
# Choice order: the CEAS offering if there is one; otherwise the first main-campus
# offering; regional campuses only if nothing else exists.
def choose_offering(session: CatalogSession) -> str:
    """On a 'Select Course Offering' page, pick an offering and return its academic group."""
    # Map row index -> college name, e.g. {"0": "Blue Ash College", "2": "College of
    # Arts & Sciences"}. split("$")[1] pulls the row number out of "ACAD_GROUP$2".
    groups = {
        a["id"].split("$")[1]: a.get_text(strip=True)
        for a in session.soup().find_all("a", id=re.compile(r"^ACAD_GROUP\$\d+$"))
    }
    # Drop the regional campuses. `or groups` falls back to all rows if that would
    # leave nothing (an empty dict is falsy in Python).
    main = {row: g for row, g in groups.items() if g not in REGIONAL_GROUPS} or groups
    # next(generator, default): the first CEAS row, or failing that, the lowest row
    # number. key=int compares rows numerically, so "10" doesn't sort before "2".
    row = next((r for r, g in main.items() if g == PREFERRED_GROUP), min(main, key=int))
    session.click(f"CAREER${row}")  # the "Undergraduate" link in that row opens the course detail
    return groups[row]


# Look up one course and save its official detail page (which includes the
# description). Replays the same path a person would click through:
#   letter index -> subject -> course number -> (offering, if asked) -> detail page.
# A new CatalogSession is started for every course, so one course's navigation state
# can't leak into the next. The cost is a few extra requests per course.
# If any step fails to find what it expects, a MISS line is printed and the course is
# skipped rather than saving the wrong page. Missing courses can then be given generic
# descriptions in step 5.
def fetch_course(subject: str, number: str, today: str) -> None:
    code = f"{subject}{number}"
    path = COURSES_DIR / f"{today}_catalyst_{code}.html"
    if path.exists():
        print(f"skip   {path.name} (already saved today)")
        return

    session = CatalogSession()
    session.click(f"DERIVED_SSS_BCC_SSR_ALPHANUM_{subject[0]}")  # the A-Z index; e.g. "C" lists subjects starting with C
    # Subject links read like "CS - CS Computer Science". Including " - " in the match
    # keeps "CS" from also matching "CSD" or "CIS".
    subject_link = session.link_id(lambda _id, text: text.startswith(f"{subject} - "))
    if not subject_link:
        print(f"MISS   {code}: subject {subject} not in catalog")
        return
    session.click(subject_link)  # expands the subject's course table
    # Course rows have a number link (ID CRSE_NBR$n) and a title link. Match the number
    # exactly so "2028C" doesn't match "2028".
    course_link = session.link_id(
        lambda _id, text: _id.startswith("CRSE_NBR$") and text == number
    )
    if not course_link:
        print(f"MISS   {code}: course not listed under {subject}")
        return
    session.click(course_link)

    # Courses with only one offering go straight to the detail page; the rest show an
    # offering picker first.
    offering = ""
    if "Select Course Offering" in session.html:
        offering = choose_offering(session)

    # Sanity check before saving, so an unexpected error page never ends up in raw/.
    if "Course Detail" not in session.html:
        print(f"MISS   {code}: no course detail page reached")
        return

    content = session.html.encode("utf-8")  # convert to bytes so the checksum matches the saved file exactly
    path.write_bytes(content)
    description = f"Catalyst course detail {subject} {number}"
    if offering:
        description += f" (offering: {offering})"  # record which college's version was saved, for traceability
    append_manifest({
        "retrieved_date": today,
        "file": f"courses/{path.name}",  # relative to data/raw/uc/, like the other manifest rows
        "url": CATALOG_URL,  # same URL for every course; the description records the click path
        "description": description,
        "method": "script-peoplesoft",
        "http_status": 200,  # _send() already raised on any non-2xx response
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    })
    print(f"saved  {path.name}" + (f" [{offering}]" if offering else ""))


# Entry point: read the course list from the saved plan, then fetch each course's
# detail page one at a time (sequentially, to keep the load on UC's server low).
def main() -> None:
    COURSES_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    courses = plan_courses()
    print(f"{len(courses)} courses in the Section I plan")
    for subject, number in courses:
        fetch_course(subject, number, today)


# Only run when executed directly (python src/collect_uc_courses.py), not on import.
if __name__ == "__main__":
    main()
