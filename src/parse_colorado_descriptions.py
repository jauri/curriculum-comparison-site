"""Read Colorado Boulder's official course descriptions from the saved catalog subject pages.

Colorado's school-specific description parser (batch 4). Reads every subject page that
collect_colorado.py saved (data/raw/colorado/*_courses-<subject>.html) and writes
data/processed/colorado/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Each subject page is a CourseLeaf list of <div class="courseblock" data-coursecode="CSCI
2270"> elements. CU's version keeps the description alone in p.courseblockdesc and puts
everything else in separate p.courseblockextra paragraphs, each led by a bold label:
"Requisites:", "Equivalent - Duplicate Degree Credit Not Granted:", "Repeatable:",
"Recommended:", "Additional Information:". Several labels can share one paragraph,
separated only by <br/>. So `description` is the whole courseblockdesc text, and
`prerequisites` is the text after "Requisites:" up to the next label. The course code comes from
the block's data-coursecode attribute, which is exact (the visible title also holds the
credit hours, "CSCI 1200 (3) Introduction ...").

Usage:
    python src/parse_colorado_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("colorado")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# The "Requisites:" part of a block's extra text, up to the next bold label (or the end).
# (?=...) is a lookahead: it stops the match before the next label without consuming it.
REQUISITES = re.compile(r"Requisites:\s*(.*?)\s*(?=(?:Equivalent - Duplicate Degree Credit Not Granted|"
                        r"Repeatable|Recommended|Additional Information):|$)")


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
        desc_p = block.select_one("p.courseblockdesc")
        # All extra paragraphs as one string; the labeled parts can share a paragraph
        # (separated only by <br/>), so the requisites are cut out by label, not by tag.
        extra = " ".join(clean(p.get_text(" ")) for p in block.select("p.courseblockextra"))
        m = REQUISITES.search(extra)
        prereq = m.group(1).strip() if m else ""
        rows.append({
            "course_code": clean(block["data-coursecode"]),
            "description": clean(desc_p.get_text(" ")) if desc_p else "",
            "prerequisites": prereq,
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
