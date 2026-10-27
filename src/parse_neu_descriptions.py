"""Read Northeastern's official course descriptions from the saved catalog subject pages.

Northeastern's school-specific description parser (step 13). Reads the archived
2025-2026 subject pages that collect_neu.py saved
(data/raw/neu/*_courses-2025-26-<subject>.html), the same catalog year as the plan, and
writes data/processed/neu/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).
The 2026-2027 pages (*_courses-<subject>.html) are only compared: courses whose title
changed between the years are listed, since a reused number (DS 3000) would otherwise
pair the plan with the wrong course.

Each subject page is a CourseLeaf list of <div class="courseblock"> elements, each with:
- p.courseblocktitle: "CS 2100.  Program Design and Implementation 1.  (4 Hours)"
- p.cb_desc: the description
- p.courseblockextra paragraphs: "Prerequisite(s): ...", "Corequisite(s): ...",
  "Attribute(s): ..." (NUpath categories)

Northeastern's plan grid names courses by code only ("CS 2100 and CS 2101"), so
parse_neu.py also needs each course's catalog title and hours. catalog_courses() gives
them, read from the same pages, so both scripts agree on one reading of the catalog.

Usage:
    python src/parse_neu_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("neu")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# The title paragraph: "CS 2100. Program Design and Implementation 1. (4 Hours)". The
# title group is lazy (.+?) so it stops at the ". (" that starts the hours; hours may be
# a range ("1-4 Hours").
TITLE = re.compile(r"^([A-Z]{2,4}) (\d{4})\.\s+(.+?)\.\s+\(([\d-]+) Hours?\)")


# Tidy CourseLeaf text: non-breaking spaces become spaces, runs of whitespace collapse,
# and the space get_text(" ") leaves before punctuation after a link is removed.
def clean(text: str) -> str:
    """Return whitespace- and punctuation-tidied text."""
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    return re.sub(r"\s+([.,;:)])", r"\1", text)  # \1 puts the punctuation back without the space


# Read all course blocks on one saved subject page, with title and hours as well as
# the description fields (read_page keeps only the description fields).
def read_blocks(path: Path) -> list[dict]:
    """Return code, title, hours, description, and prerequisites for each course block."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    rows = []
    for block in soup.select("div.courseblock"):
        m = TITLE.match(clean(block.select_one("p.courseblocktitle").get_text(" ")))
        if not m:
            continue  # not a course title (none seen, but don't guess)
        desc_p = block.select_one("p.cb_desc")
        prereq = ""
        for extra in block.select("p.courseblockextra"):
            text = clean(extra.get_text(" "))
            if text.startswith("Prerequisite(s):"):
                prereq = text.removeprefix("Prerequisite(s):").strip()
        rows.append({
            "course_code": f"{m.group(1)} {m.group(2)}",
            "title": m.group(3),
            "hours": m.group(4),
            "description": clean(desc_p.get_text(" ")) if desc_p else "",
            "prerequisites": prereq,
        })
    return rows


# The newest snapshot of each subject page of one catalog year, keyed by the filename
# without its date. year="2025-26" gives the pages used; year="" gives the 2026-27 pages
# (their names have no year, and the [a-z]* pattern keeps the 2025-26 ones out).
def newest_pages(year: str = "2025-26") -> dict[str, Path]:
    """Return {"courses-2025-26-cs.html": newest path, ...} for one catalog year."""
    pattern = f"*_courses-{year}-*.html" if year else "*_courses-[a-z]*.html"
    newest = {}
    for path in sorted(SCHOOL.raw.glob(pattern)):
        newest[path.name.split("_", 1)[1]] = path  # later dates sort last and win
    return newest


# Catalog title and hours of every course, for parse_neu.py.
def catalog_courses(year: str = "2025-26") -> dict[str, tuple[str, str]]:
    """Return {course code: (title, hours text)} from the newest subject pages of a year."""
    return {r["course_code"]: (r["title"], r["hours"])
            for path in newest_pages(year).values() for r in read_blocks(path)}


# Script entry point: write the description fields of every course block.
def main() -> None:
    manifest = pd.read_csv(SCHOOL.raw / "sources.csv")
    urls = dict(zip(manifest["file"], manifest["url"]))  # zip pairs the two columns row by row
    newest = newest_pages()
    rows = []
    for path in newest.values():
        for r in read_blocks(path):
            rows.append({"course_code": r["course_code"], "description": r["description"],
                         "prerequisites": r["prerequisites"], "description_url": urls.get(path.name, ""),
                         "description_file": rel(path)})
    empty = sorted(r["course_code"] for r in rows if not r["description"])
    rows = [r for r in rows if r["description"]]
    failures = [f"{r['description_file']}: not in sources.csv" for r in rows if not r["description_url"]]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OFFICIAL_COLUMNS).to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(rows)} official descriptions from {len(newest)} subject pages to {rel(OUT_CSV)}")
    if empty:
        print(f"Skipped (course block without description text): {', '.join(empty)}")
    # Cross-check against 2026-27: titles that changed for the plan's subjects. Only
    # courses in both years are compared; this is a report, not a failure.
    old, new = catalog_courses("2025-26"), catalog_courses("")
    changed = sorted(c for c in old.keys() & new.keys() if old[c][0] != new[c][0])  # & is set intersection
    print(f"Titles changed in 2026-27 ({len(changed)}): " +
          "; ".join(f"{c}: {old[c][0]} -> {new[c][0]}" for c in changed[:12]) + (" ..." if len(changed) > 12 else ""))
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(sorted(set(failures))))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
