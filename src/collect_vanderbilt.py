"""Download Vanderbilt's CS BS sources into data/raw/vanderbilt/ and log them in sources.csv.

Vanderbilt's School of Engineering publishes a "Four-Year Roadmap and Checklist" per
major. The newest Computer Science roadmap is for 2025-26 (no 2026-27 version is posted
on the department site), so it is the canonical plan (Georgia Tech and UVA precedent
for an older-year plan). Saved by script:

- the 2025-26 CS Roadmap PDF: eight semesters, 120 hours (canonical plan);
- the 2025-26 CS Prerequisite Sheets PDF: the curriculum's requirement groups, which
  list the options behind the roadmap's slots (Basic Science, CS Depth, CS Project,
  Technical Elective);
- the 2026-27 Undergraduate Catalog's record for the Computer Science major (CSENGBS),
  from the catalog's public Kuali API, which names the School of Engineering;
- one 2026-27 catalog course record per course the roadmap or the sheets name by code,
  each holding that course's title and description.

Why the Kuali API: the catalog page (vanderbilt.edu/catalogs/kuali/undergraduate-26-27.php)
is an empty shell that a script on the page fills from this API, so the API's JSON is
what the page itself shows. The JSON is saved unchanged.

Sources were reviewed and approved by the user before downloading (batch 5).

Usage:
    python src/collect_vanderbilt.py
"""

import re
from datetime import date

import pdfplumber
import requests

from collect_common import HEADERS, fetch, save
from common import load_school

SCHOOL = load_school("vanderbilt")
CDN = "https://cdn.vanderbilt.edu/vu-sub/wp-content/uploads/sites/282/2025/09/"
# The 2026-27 Undergraduate Catalog's id in Kuali, read from the catalog page's own
# script (catalogId = '69861616dc1d2450f8837f3a'), and the CS major's program id (pid).
KUALI = "https://vanderbilt.kuali.co/api/v1/catalog/"
CATALOG_ID = "69861616dc1d2450f8837f3a"
CS_MAJOR_PID = "HkeZHOkNjd"

# (slug, url, description, file extension).
SOURCES = [
    ("cs-roadmap-2025-26", CDN + "23152312/25-26-Computer-Science-Roadmap.pdf",
     "Four-Year Roadmap and Checklist, Computer Science, 2025-26 (School of Engineering): eight semesters, "
     "120 hours (canonical plan)", ".pdf"),
    ("cs-prerequisite-sheets-2025-26", CDN + "23152745/25-26-Computer-Science-Prerequisite-Sheets.pdf",
     "Computer Science Curriculum and Prerequisites, 2025-2026 Catalog Year: requirement groups and the "
     "options behind the roadmap's slots", ".pdf"),
    ("cs-major-program", f"{KUALI}program/{CATALOG_ID}/{CS_MAJOR_PID}",
     "Computer Science (Major), CSENGBS, 2026-27 Undergraduate Catalog (Kuali API record): School of "
     "Engineering (college source)", ".json"),
]
# One token of a course list in the PDFs, either
# - a full code: subject letters, a space, four digits, an optional letter ("CS 1101",
#   "ES 2100W", "CS/ECE 2281L"). For cross-listed "CS/ECE 2201" the optional
#   (?:/[A-Z]{2,4})? swallows "/ECE", so the CS code (written first) is the one kept, and
#   the lookbehind (?<![/A-Z]) stops a second match starting at "ECE"; or
# - a bare number after a comma: the sheets' shorthand lists repeat only the number
#   ("CHEM 1601, 1601L, 1602"), and such a number inherits the last subject.
TOKEN = re.compile(r"(?<![/A-Z])([A-Z]{2,4})(?:/[A-Z]{2,4})? (\d{4}[A-Z]?)\b|,\s*(\d{4}[A-Z]?)\b")


# Course codes named in the two saved PDFs, in order of first appearance. Codes are read
# from the saved files (not typed here) so the list is traceable to the sources.
# "ES 1401-1403" is a range: ES 1401, 1402 and 1403 are one-credit modules taken together.
def pdf_codes() -> list[str]:
    """Return the distinct course codes in the newest saved roadmap and sheets."""
    codes = []
    for pattern in ("*_cs-roadmap-2025-26.pdf", "*_cs-prerequisite-sheets-2025-26.pdf"):
        with pdfplumber.open(SCHOOL.newest(pattern)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        text = text.replace("ES 1401-1403", "ES 1401, 1402, 1403")
        # Walk the text once, keeping the last subject so shorthand numbers get one.
        subject = None
        for m in TOKEN.finditer(text):
            if m.group(1):
                subject = m.group(1)
                codes.append(f"{subject} {m.group(2)}")
            elif subject:
                codes.append(f"{subject} {m.group(3)}")
    return list(dict.fromkeys(codes))  # dict.fromkeys keeps first-seen order, drops repeats


# Map catalog course ids ("CS2201") to Kuali pids for the whole 2026-27 catalog. The
# list is fetched (not saved): it only locates each course's record, and every saved
# record carries its own URL in sources.csv.
def course_pids() -> dict[str, str]:
    """Return {catalog course id: pid} for the 2026-27 catalog."""
    resp = requests.get(f"{KUALI}courses/{CATALOG_ID}", headers=HEADERS, timeout=60)
    resp.raise_for_status()
    return {c["__catalogCourseId"]: c["pid"] for c in resp.json()}


# Entry point: the three program sources, then one record per course code.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-11-14"
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)
    pids = course_pids()
    missing = []
    for code in pdf_codes():
        key = code.replace(" ", "")  # "CS 2201" -> "CS2201", the catalog's course id
        name = f"courses/{today}_{key}.json"
        if (SCHOOL.raw / name).exists():
            print(f"skip   {name} (already saved today)")
            continue  # skip before requesting, so reruns don't contact the server
        if key not in pids:
            missing.append(code)  # e.g. a course no longer in the 2026-27 catalog
            continue
        url = f"{KUALI}course/{CATALOG_ID}/{pids[key]}"
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()  # an error page is never saved as a source
        save(SCHOOL.raw, name, url, f"Course record, {code}, 2026-27 Undergraduate Catalog (Kuali API)",
             "script", resp, today)
    if missing:
        print(f"Not in the 2026-27 catalog: {', '.join(missing)}")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
