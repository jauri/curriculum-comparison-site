"""Read UIUC's official course descriptions from the saved catalog subject pages.

UIUC's school-specific description parser (step 13, batch 2). Reads every subject page
that collect_uiuc.py saved (data/raw/uiuc/*_courses-<subject>.html) and writes
data/processed/uiuc/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Each subject page is a CourseLeaf list of <div class="courseblock"> elements. UIUC's
version:
- p.courseblocktitle holds "CS 225   Data Structures   credit: 4 Hours." (code, title,
  and hours separated by runs of spaces);
- p.courseblockdesc holds the description, then usually "Prerequisite: ...", then
  after a <br/> "This course satisfies the General Education Criteria for: ...".
The text before "Prerequisite:" (or before the gen-ed sentence when there is no
prerequisite) becomes `description`; the prerequisite sentence(s) become
`prerequisites`. Every course on the page is written (describe.py uses only the ones in
the plan); a block with no description text is skipped and listed. Some descriptions
open with the Illinois Articulation Initiative code, "[IAI Code: M1900-1 and MTH901] ",
which is a transfer-equivalence label, not description text, so it is removed.

Usage:
    python src/parse_uiuc_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("uiuc")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# The title line starts with the code: "CS 225 Data Structures ..." -> subject, number.
TITLE = re.compile(r"^([A-Z]{2,4}) (\d{3})\b")
# Where the description ends: the prerequisite sentence or the gen-ed note.
END = re.compile(r"\s*(?:Prerequisites?:|This course satisfies the General Education)")
# The prerequisite text runs to the gen-ed note or the end of the block. (?s) lets "."
# cross line breaks; the lazy .*? stops at the first gen-ed note.
PREREQ = re.compile(r"(?s)Prerequisites?:\s*(.*?)(?:\s*This course satisfies the General Education|$)")
# The Illinois Articulation Initiative prefix, "[IAI Code: ...] ", at the very start.
IAI = re.compile(r"^\[IAI Code:[^\]]*\]\s*")


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
        desc_p = block.select_one("p.courseblockdesc")
        m = TITLE.match(clean(title_p.get_text(" "))) if title_p else None
        if not m or desc_p is None:
            continue  # not a course block (none seen, but don't guess)
        full = clean(desc_p.get_text(" "))
        pre = PREREQ.search(full)
        rows.append({
            "course_code": f"{m.group(1)} {m.group(2)}",
            # Text before the first end marker, without the IAI prefix.
            "description": IAI.sub("", END.split(full, maxsplit=1)[0]).strip(),
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
