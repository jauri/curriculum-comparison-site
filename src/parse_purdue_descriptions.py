"""Read Purdue's official course descriptions from the saved catalog course pages.

Purdue's school-specific description parser (step 13, batch 3). Reads every course page
that collect_purdue.py imported (data/raw/purdue/courses/*_<code>.html, saved through
Chrome) and writes data/processed/purdue/official_descriptions.csv (columns in
common.OFFICIAL_COLUMNS).

Each page is an Acalog "preview_course_nopop.php" page. Inside its content block:
    <h1 id="course_preview_title">CS 25100 - Data Structures And Algorithms</h1><hr/>
    Credit Hours: 3.00.  Running time analysis of ... <hr/>
    <strong>Learning Outcomes</strong> ... <hr/> ...
The description is the text between the first and second <hr/> after the title, with
the leading "Credit Hours: N." removed. Purdue's catalog lists no prerequisites on
these pages (it points students to myPurdue), so `prerequisites` is left empty.

Usage:
    python src/parse_purdue_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("purdue")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
TITLE = re.compile(r"^([A-Z]{2,4}) (\d{5}) - ")


# Tidy Acalog text: non-breaking spaces become spaces and runs of whitespace collapse.
def clean(text: str) -> str:
    """Return whitespace-tidied text."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


# Read the description from one saved course page.
def read_page(path: Path, url: str) -> dict | None:
    """Return the official-description row for a course page, or None if it has none."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    h1 = soup.find("h1", id="course_preview_title")
    m = TITLE.match(clean(h1.get_text(" "))) if h1 else None
    if not m:
        return None
    first_hr = h1.find_next("hr")
    parts = []
    # next_siblings walks the nodes after the first <hr/> at the same level, so the loop
    # collects text (and inline tags) until it reaches the second <hr/>.
    for node in first_hr.next_siblings:
        if getattr(node, "name", None) == "hr":
            break
        parts.append(node.get_text(" ") if hasattr(node, "get_text") else str(node))
    desc = re.sub(r"^Credit Hours: [\d.]+(?: (?:to|or) [\d.]+)?\.\s*", "", clean(" ".join(parts)))
    return {"course_code": f"{m.group(1)} {m.group(2)}", "description": desc, "prerequisites": "",
            "description_url": url, "description_file": rel(path)}


# Script entry point: read the newest snapshot of each course page.
def main() -> None:
    manifest = pd.read_csv(SCHOOL.raw / "sources.csv")
    urls = dict(zip(manifest["file"], manifest["url"]))  # zip pairs the two columns row by row
    newest = {}
    for path in sorted((SCHOOL.raw / "courses").glob("*.html")):
        newest[path.name.split("_", 1)[1]] = path  # key without the date: later dates win
    rows, empty = [], []
    for path in newest.values():
        row = read_page(path, urls.get(f"courses/{path.name}", ""))
        if row and row["description"]:
            rows.append(row)
        else:
            empty.append(path.name)
    failures = [f"{r['description_file']}: not in sources.csv" for r in rows if not r["description_url"]]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OFFICIAL_COLUMNS).to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(rows)} official descriptions from {len(newest)} course pages to {rel(OUT_CSV)}")
    if empty:
        print(f"No description text: {', '.join(empty)}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(sorted(set(failures))))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
