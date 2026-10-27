"""Read Virginia Tech's official course descriptions from the saved catalog subject pages.

Virginia Tech's school-specific description parser (step 13, batch 3). Reads every
subject page that collect_vt.py imported (data/raw/vt/*_courses-<subject>.html) and
writes data/processed/vt/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Each subject page is a CourseLeaf list of <div class="courseblock"> elements in VT's
"detail" layout, with one element per field:
- span.detail-code holds the code ("CS 3214"), span.detail-title the title
  ("- Computer Systems");
- div.courseblockextra holds the description;
- span.detail-prereq holds "Prerequisite(s): ...". Other fields (corequisites,
  contact hours, pathways) are not used.
Every course on the page is written (describe.py uses only the ones in the plan); a
block with no description text is skipped and listed.

Usage:
    python src/parse_vt_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("vt")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
CODE = re.compile(r"^([A-Z]{2,4}) (\d{4})$")


# Tidy CourseLeaf text: non-breaking spaces become spaces, runs of whitespace collapse,
# and the space get_text(" ") leaves before punctuation after a link is removed.
def clean(text: str) -> str:
    """Return whitespace- and punctuation-tidied text."""
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    text = re.sub(r"\(\s+", "(", text)  # "( CS 2506" -> "(CS 2506", left by get_text around links
    return re.sub(r"\s+([.,;:)])", r"\1", text)  # \1 puts the punctuation back without the space


# Read all course blocks on one saved subject page.
def read_page(path: Path, url: str) -> list[dict]:
    """Return one official-description row per course block on a subject page."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    rows = []
    for block in soup.select("div.courseblock"):
        code_el = block.select_one("span.detail-code")
        m = CODE.match(clean(code_el.get_text(" "))) if code_el else None
        if not m:
            continue  # not a course block (none seen, but don't guess)
        desc_el = block.select_one("div.courseblockextra")
        pre_el = block.select_one("span.detail-prereq")
        prereq = clean(pre_el.get_text(" ")) if pre_el else ""
        rows.append({
            "course_code": m.group(0),
            "description": clean(desc_el.get_text(" ")) if desc_el else "",
            "prerequisites": re.sub(r"^Prerequisite\(s\):\s*", "", prereq),
            "description_url": url,
            "description_file": rel(path),
        })
    return rows


# Script entry point: read the newest snapshot of each subject page.
def main() -> None:
    manifest = pd.read_csv(SCHOOL.raw / "sources.csv")
    urls = dict(zip(manifest["file"], manifest["url"]))  # zip pairs the two columns row by row
    newest = {}
    for path in sorted(SCHOOL.raw.glob("*_courses-*.html")):
        newest[path.name.split("_", 1)[1]] = path  # key without the date: later dates win
    rows = [r for path in newest.values() for r in read_page(path, urls.get(path.name, ""))]
    empty = sorted(r["course_code"] for r in rows if not r["description"])
    rows = [r for r in rows if r["description"]]
    failures = [f"{r['description_file']}: not in sources.csv" for r in rows if not r["description_url"]]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OFFICIAL_COLUMNS).to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(rows)} official descriptions from {len(newest)} subject pages to {rel(OUT_CSV)}")
    if empty:
        print(f"Skipped (course block without description text): {', '.join(empty)}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(sorted(set(failures))))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
