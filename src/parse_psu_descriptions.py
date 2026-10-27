"""Read Penn State's official course descriptions from the saved bulletin subject pages.

Penn State's school-specific description parser (step 13, batch 3). Reads every subject
page that collect_psu.py saved (data/raw/psu/*_courses-<subject>.html) and writes
data/processed/psu/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Each subject page is a CourseLeaf list of <div class="courseblock"> elements, in Penn
State's own layout:
- div.courseblocktitle .course_codetitle holds "CMPSC 102: Introduction to Visual
  Programming" (code and title joined by ": ");
- div.courseblockdesc holds the description, in one or more <p> paragraphs;
- div.courseblockextra paragraphs hold labeled extras ("Prerequisite: ...",
  "Enforced Prerequisite at Enrollment: ...", "Cross-listed with: ...",
  "General Education: ..."). The ones whose label mentions a prerequisite become
  `prerequisites`.
Every course on the page is written (describe.py uses only the ones in the plan). A
block with no description text is skipped and listed.

Usage:
    python src/parse_psu_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("psu")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# "CMPSC 483W: Software Design Methods" -> code "CMPSC 483W". Numbers may carry a
# letter suffix (W = writing, N = inter-domain, A/B/C = variants such as CAS 100A).
TITLE = re.compile(r"^([A-Z]{2,5}) (\d{1,3}[A-Z]?):")


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
        # The first .course_codetitle is in the title bar; the bubble repeats the title alone.
        head = block.select_one("div.courseblocktitle .course_codetitle")
        m = TITLE.match(clean(head.get_text(" "))) if head else None
        if not m:
            continue  # not a course block (none seen, but don't guess)
        desc = " ".join(clean(p.get_text(" ")) for p in block.select("div.courseblockdesc p"))
        prereqs = [clean(p.get_text(" ")) for p in block.select("div.courseblockextra p")
                   if "prerequisite" in clean(p.get_text(" ")).split(":", 1)[0].lower()]
        rows.append({
            "course_code": f"{m.group(1)} {m.group(2)}",
            "description": desc,
            "prerequisites": " ".join(prereqs),
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
