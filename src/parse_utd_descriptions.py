"""Read UT Dallas's official course descriptions from the saved per-course catalog pages.

UT Dallas's school-specific description parser (batch 4). Reads every course page that
collect_utd.py saved (data/raw/utd/courses/<date>_<CODE>.html) and writes
data/processed/utd/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Each page holds one course in <div id="bukku-page">: an <h1>, then a <p> that starts
with labeled spans (course_address "CS 1337", course_tccns "(COSC 1337)", course_title,
course_hours "(3 semester credit hours)") followed by plain text:

    Review of control structures ... Prerequisite: CS 1436 with a grade of C or better
    or equivalent. (Same as CE 1337) (3-0) S

So the spans are removed, the trailing "(3-0) S" (lecture-lab hours and the terms
offered) and "(Same as ...)" cross-listing are cut off, and the text is split at the
first "Prerequisite"/"Corequisite" phrase: before it is `description`, from it on is
`prerequisites`. A page without the paragraph (the plan's mistyped "CS 3337", whose page
is an empty shell) is skipped and listed.

Usage:
    python src/parse_utd_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("utd")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# The end of the paragraph: "(3-0) S", "(3-1) Y", "(0-3) R" (lecture-lab hours, terms).
HOURS_TAIL = re.compile(r"\s*\(\d+-\d+\)\s*[A-Z]*\s*$")
# A cross-listing note, "(Same as CE 1337)", anywhere in the text.
SAME_AS = re.compile(r"\s*\(Same as [^)]*\)")
# Where the requisites begin: "Prerequisite:", "Prerequisites:", "Corequisite:",
# "Prerequisite or Corequisite:", "Prerequisites or Corequisites:".
REQS = re.compile(r"\b(?:Prerequisites?|Corequisites?)\b(?: or (?:Prerequisites?|Corequisites?))?:")


# Collapse whitespace and remove the space get_text(" ") leaves before punctuation.
def clean(text: str) -> str:
    """Return whitespace- and punctuation-tidied text."""
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    return re.sub(r"\s+([.,;:)])", r"\1", text)  # \1 puts the punctuation back without the space


# Read one saved course page. Returns None when the page has no course paragraph.
def read_page(path: Path, url: str) -> dict | None:
    """Return the official-description row for one course page, or None."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    para = soup.select_one("#bukku-page p")  # CSS: the first <p> inside the element with id bukku-page
    if para is None or para.select_one(".course_address") is None:
        return None
    code = clean(para.select_one(".course_address").get_text(" "))
    for span in para.select("span"):
        span.decompose()  # drop the code, TCCN, title, and hours spans before reading the text
    full = SAME_AS.sub("", HOURS_TAIL.sub("", clean(para.get_text(" "))))
    m = REQS.search(full)
    return {
        "course_code": code,
        "description": (full[:m.start()] if m else full).strip(),
        "prerequisites": full[m.start():].strip() if m else "",
        "description_url": url,
        "description_file": rel(path),
    }


# Script entry point: read the newest snapshot of each course page.
def main() -> None:
    manifest = pd.read_csv(SCHOOL.raw / "sources.csv")
    urls = dict(zip(manifest["file"], manifest["url"]))  # zip pairs the two columns row by row
    newest = {}
    for path in sorted((SCHOOL.raw / "courses").glob("*_*.html")):
        newest[path.name.split("_", 1)[1]] = path  # key without the date: later dates win
    rows, empty = [], []
    for path in newest.values():
        row = read_page(path, urls.get(f"courses/{path.name}", ""))
        if row is None or not row["description"]:
            empty.append(path.name)
        else:
            rows.append(row)
    failures = [f"{r['description_file']}: not in sources.csv" for r in rows if not r["description_url"]]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OFFICIAL_COLUMNS).to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(rows)} official descriptions from {len(newest)} course pages to {rel(OUT_CSV)}")
    if empty:
        print(f"Skipped (no course paragraph): {', '.join(empty)}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(sorted(set(failures))))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
