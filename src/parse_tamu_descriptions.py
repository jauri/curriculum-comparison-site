"""Read Texas A&M's official course descriptions from the saved catalog subject pages.

Texas A&M's school-specific description parser (step 13). Reads every subject page that
collect_tamu.py saved (data/raw/tamu/*_courses-<subject>.html) and writes
data/processed/tamu/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Each subject page is a CourseLeaf list of <div class="courseblock"> elements. TAMU's
version differs from UIC's in two ways:
- the title is an <h2 class="courseblocktitle"> holding "CSCE 221 Data Structures and
  Algorithms" (no periods, no hours);
- p.courseblockdesc starts with a <span class="hours"> block ("Credits 4. 3 Lecture
  Hours. 2 Lab Hours."), then the description, then "Prerequisites:" and sometimes
  "Cross Listing:".
The hours span is removed; the text before "Prerequisites:" (or "Cross Listing:")
becomes `description`, and the prerequisite text becomes `prerequisites`. Many
descriptions open with the Texas Common Course Numbering equivalent and the title again,
"(MATH 2413) Engineering Mathematics I. Rectangular coordinates, ...", so that prefix is
removed. Every course on the page is written (describe.py uses only the ones in the
plan); a block with no description text is skipped and listed, not treated as an error,
since describe.py fails for any plan course without one.

Usage:
    python src/parse_tamu_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("tamu")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# The title heading: "CSCE 221 Data Structures and Algorithms" -> subject, number.
TITLE = re.compile(r"^([A-Z]{3,4}) (\d{3})\b")
# Labeled sections that may follow the description; the description stops at the first.
SECTIONS = re.compile(r"\s*(?:Prerequisites?|Cross Listings?|Corequisites?):")
PREREQ = re.compile(r"Prerequisites?:\s*(.*?)(?:\s*(?:Cross Listings?|Corequisites?):|$)")
# The Texas Common Course Numbering prefix: "(CHEM 1309, 1409*) " at the very start.
TCCN = re.compile(r"^\([A-Z]{3,4} \d{4}[^)]*\)\s*")


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
        m = TITLE.match(clean(block.select_one(".courseblocktitle").get_text(" ")))
        desc_p = block.select_one("p.courseblockdesc")
        if not m or desc_p is None:
            continue  # not a course block (none seen, but don't guess)
        for span in desc_p.select("span.hours"):
            span.decompose()  # drop "Credits 4. 3 Lecture Hours. ..." before reading the text
        full = clean(desc_p.get_text(" "))
        description = SECTIONS.split(full, maxsplit=1)[0]  # text before the first labeled section
        description = TCCN.sub("", description)
        # The title repeated after the TCCN prefix: "Engineering Mathematics I. " (the
        # heading minus its code) is dropped when the text starts with it.
        title = clean(block.select_one(".courseblocktitle").get_text(" "))[m.end():].strip()
        if title and description.startswith(title + "."):
            description = description[len(title) + 1:].strip()
        pre = PREREQ.search(full)
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
