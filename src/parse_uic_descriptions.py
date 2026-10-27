"""Read UIC's official course descriptions from the saved catalog subject pages.

UIC's school-specific description parser (phase 2, step 10). Reads every subject page
that collect_uic.py saved (data/raw/uic/*_courses-<subject>.html) and writes
data/processed/uic/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Each subject page is a CourseLeaf list of <div class="courseblock"> elements, each with:
- p.courseblocktitle: "CS 251.  Data Structures.  4 hours."
- p.courseblockdesc: the description, then "Course Information:" followed by notes such
  as cross-listings, grading, and "Prerequisite(s): ...", sometimes then "Class
  Schedule Information: ..." about lab/lecture registration.
The text before "Course Information:" becomes `description`; the Prerequisite(s) part
becomes `prerequisites`. Every course on the page is written (describe.py uses only
the ones in the plan).

Usage:
    python src/parse_uic_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("uic")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# The title paragraph: code, title, hours, each ending in a period, e.g.
# "CS 251. Data Structures. 4 hours." The title group is lazy (.+?) so it stops at the
# first ". <digits>" that starts the hours; hours may be a range ("1-4 hours").
TITLE = re.compile(r"^([A-Z]{2,4}) (\d{3})\.\s+(.+?)\.\s+([\d-]+(?: or [\d-]+)?) hours?\.")
# The prerequisite part of "Course Information": everything after "Prerequisite(s):"
# (UIC sometimes writes "Prerequisite (s):") up to the next labeled section or the end.
PREREQ = re.compile(r"Prerequisite\s*\(s\):\s*(.*?)(?:\s*(?:Class|Course) Schedule Information:|\s*Recommended Background:|$)")


# Tidy CourseLeaf text: non-breaking spaces become spaces, runs of whitespace collapse,
# and the space get_text(" ") leaves before punctuation after a link ("BIOS 112 .")
# is removed.
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
        m = TITLE.match(clean(block.select_one("p.courseblocktitle").get_text(" ")))
        if not m:
            continue  # not a course title (none seen, but don't guess)
        desc_p = block.select_one("p.courseblockdesc")
        full = clean(desc_p.get_text(" ")) if desc_p else ""
        # partition splits at the first occurrence: (before, separator, after).
        description, _, info = full.partition("Course Information:")
        pre = PREREQ.search(info)
        rows.append({
            "course_code": f"{m.group(1)} {m.group(2)}",
            "description": description.strip(),
            "prerequisites": pre.group(1).strip() if pre else "",
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
    failures = [f"{r['course_code']}: no description" for r in rows if not r["description"]]
    failures += [f"{r['description_file']}: not in sources.csv" for r in rows if not r["description_url"]]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OFFICIAL_COLUMNS).to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(rows)} official descriptions from {len(newest)} subject pages to {rel(OUT_CSV)}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(sorted(set(failures))))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
