"""Read Case Western Reserve's official course descriptions from the saved bulletin subject pages.

Case Western's school-specific description parser (batch 5). Reads every subject page
that collect_case.py saved (data/raw/case/*_courses-<subject>.html) and writes
data/processed/case/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Each subject page is a CourseLeaf list of <div class="courseblock"> elements with no
data-coursecode attribute. The title paragraph reads "CSDS 233.  Introduction to Data
Structures.  4 Units.", so the course code is the text before the first period. The
description paragraph (p.courseblockdesc) holds the description followed by labeled
parts: "Offered as CSDS 233 and ECSE 233.", "Counts as a ... course.", "Prereq: ...",
"Coreq: ...", "Prereq or Coreq: ...", "Recommended preparation: ...". So
`description` is the text before the first label (the cross-listing and the
general-education counts are not course content), and `prerequisites` is the text
after "Prereq:" (or "Prereq or Coreq:") up to the next label.

Usage:
    python src/parse_case_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("case")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# The labels that start the non-description parts of a block, in any order. Both
# capitalizations of "Recommended preparation" occur on the saved pages.
LABEL = r"(?:Offered as |Counts as |Prereq or Coreq:|Prereq:|Coreq:|Recommended [Pp]reparation:)"
FIRST_LABEL = re.compile(r"\s*" + LABEL)
# "Prereq:" (or "Prereq or Coreq:") and its text up to the next label or the end.
# (?=...) is a lookahead: it stops before the next label without consuming it.
PREREQ = re.compile(r"Prereq(?: or Coreq)?:\s*(.*?)\s*(?=" + LABEL + r"|$)")
# The title paragraph's leading course code: "CSDS 233." -> "CSDS 233".
TITLE_CODE = re.compile(r"^([A-Z]{3,4} \d{3}[A-Z]?)\.")


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
    for block in soup.select("div.courseblock"):
        title_p = block.select_one("p.courseblocktitle")
        m = TITLE_CODE.match(clean(title_p.get_text(" "))) if title_p else None
        if m is None:
            continue  # not a course entry
        desc_p = block.select_one("p.courseblockdesc")
        body = clean(desc_p.get_text(" ")) if desc_p else ""
        cut = FIRST_LABEL.search(body)
        prereq = PREREQ.search(body)
        rows.append({
            "course_code": m.group(1),
            "description": body[:cut.start()] if cut else body,  # slice up to the first label
            "prerequisites": prereq.group(1).rstrip(".") if prereq else "",
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
