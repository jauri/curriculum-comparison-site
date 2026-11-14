"""Read UConn's official course descriptions from the saved catalog subject pages.

UConn's school-specific description parser (batch 4). Reads every subject page saved
through Chrome by collect_uconn.py (data/raw/uconn/*_courses-<subject>.html) and writes
data/processed/uconn/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

UConn's 2026-2027 catalog is a newer CourseLeaf layout than Texas A&M's. Each course is a
<div class="courseblock" data-coursecode="CSE 2050">, with:
- the description alone in a div.courseblockextra;
- labeled spans after it, each with a bold label: "Enrollment Requirements:" (the
  prerequisites), "Grading Basis:", and so on (span.detail-reqs holds the first).
So `description` is the courseblockextra text and `prerequisites` is the detail-reqs
text without its label.

Usage:
    python src/parse_uconn_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("uconn")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"


# Tidy CourseLeaf text: non-breaking spaces become spaces, runs of whitespace collapse,
# and the space get_text(" ") leaves before punctuation after a link is removed.
def clean(text: str) -> str:
    """Return whitespace- and punctuation-tidied text."""
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    return re.sub(r"\s+([.,;:)])", r"\1", text)  # \1 puts the punctuation back without the space


# Read all course blocks on one saved subject page.
def read_page(path: Path, url: str) -> list[dict]:
    """Return one official-description row per course block on a subject page."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    rows = []
    for block in soup.select("div.courseblock[data-coursecode]"):  # [attr]: only blocks that carry a code
        desc = block.select_one("div.courseblockextra")
        reqs = block.select_one("span.detail-reqs")
        if reqs is not None and reqs.find("strong"):
            reqs.find("strong").decompose()  # drop the "Enrollment Requirements:" label
        rows.append({
            "course_code": clean(block["data-coursecode"]),
            "description": clean(desc.get_text(" ")) if desc else "",
            "prerequisites": clean(reqs.get_text(" ")) if reqs else "",
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
