"""Read Wisconsin's official course descriptions from the saved Guide subject pages.

Wisconsin's school-specific description parser (step 13, batch 2). Reads every subject
page that collect_wisc.py saved (data/raw/wisc/*_courses-<subject>.html) and writes
data/processed/wisc/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Each subject page is a CourseLeaf list of <div class="courseblock"> elements. The
Guide's version:
- span.courseblockcode holds the code, possibly cross-listed: "COMP SCI/E C E 354";
- p.courseblockdesc holds only the description;
- hidden "cb-extras" paragraphs hold labeled facts, one of which is "Requisites:".
A cross-listed course gets one row per listing (COMP SCI 354 and E C E 354), all with
the same text, so the plan's code finds it whichever listing the plan uses. A course
listed on two saved pages (COMP SCI/MATH 240 is on both) keeps the first row read.

Usage:
    python src/parse_wisc_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel
from parse_wisc import CODE, listings, text

SCHOOL = load_school("wisc")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"


# Remove the spaces get_text(" ") leaves around links: before punctuation and after "(".
def tidy(t: str) -> str:
    """Return text without stray spaces before punctuation or after an opening parenthesis."""
    t = re.sub(r"\s+([.,;:)])", r"\1", t)  # \1 puts the punctuation back without the space
    return re.sub(r"\(\s+", "(", t)


# Read all course blocks on one saved subject page.
def read_page(path: Path, url: str) -> list[dict]:
    """Return one official-description row per listing code on a subject page."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    rows = []
    for block in soup.select("div.courseblock"):
        code_span, desc_p = block.select_one(".courseblockcode"), block.select_one("p.courseblockdesc")
        m = CODE.match(text(code_span)) if code_span else None
        if not m or desc_p is None:
            continue  # not a course block (none seen, but don't guess)
        prereq = ""
        for extra in block.select("p.courseblockextra"):
            label = extra.select_one(".cbextra-label")
            if label and text(label).startswith("Requisites"):
                prereq = tidy(text(extra.select_one(".cbextra-data")))
        description = tidy(text(desc_p))
        for code in listings(*m.groups()):
            rows.append({"course_code": code, "description": description, "prerequisites": prereq,
                         "description_url": url, "description_file": rel(path)})
    return rows


# Script entry point: read the newest snapshot of each subject page.
def main() -> None:
    manifest = pd.read_csv(SCHOOL.raw / "sources.csv")
    urls = dict(zip(manifest["file"], manifest["url"]))  # zip pairs the two columns row by row
    newest = {}
    for path in sorted(SCHOOL.raw.glob("*_courses-*.html")):
        newest[path.name.split("_", 1)[1]] = path  # key without the date: later dates win
    rows = [r for path in newest.values() for r in read_page(path, urls.get(path.name, ""))]
    empty = sorted({r["course_code"] for r in rows if not r["description"]})
    df = pd.DataFrame([r for r in rows if r["description"]], columns=OFFICIAL_COLUMNS)
    df = df.drop_duplicates("course_code")  # keep the first page's row for a course on two pages
    failures = [f"{f}: not in sources.csv" for f in df.loc[df["description_url"] == "", "description_file"]]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(df)} official descriptions from {len(newest)} subject pages to {rel(OUT_CSV)}")
    if empty:
        print(f"Skipped (course block without description text): {', '.join(empty)}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(sorted(set(failures))))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
