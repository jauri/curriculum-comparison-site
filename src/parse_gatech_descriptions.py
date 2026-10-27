"""Read Georgia Tech's official course descriptions from the saved catalog subject pages.

Georgia Tech's school-specific description parser (step 13, batch 3). Reads every
subject page that collect_gatech.py saved (data/raw/gatech/*_courses-<subject>.html)
and writes data/processed/gatech/official_descriptions.csv (columns in
common.OFFICIAL_COLUMNS).

Each subject page is a CourseLeaf list of <div class="courseblock"> elements in the
classic layout:
- p.courseblocktitle holds "CS 1332.  Data Structures and Algorithms for Applications.
  3 Credit Hours." (code, title, and hours separated by periods);
- p.courseblockdesc holds the description;
- p.courseblockextra paragraphs, when present, hold labeled extras; the one starting
  "Prerequisite" becomes `prerequisites`.

The pages are the 2026-2027 catalog's, while the plan is the College of Computing's
2025-26 sheet: the catalog archive holds only whole-catalog PDFs (collect_gatech.py).
A course renamed between the two years would show here as a title mismatch, which
build_outputs/validate do not check, so the parser prints each plan course's catalog
title for review instead.

Usage:
    python src/parse_gatech_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("gatech")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# "CS 1332.  Data Structures ...  3 Credit Hours." -> code "CS 1332". Some numbers end
# in a letter ("MATH 1X51" style placeholders are not real courses and don't match).
TITLE = re.compile(r"^([A-Z]{2,4}) (\d{4}[A-Z]?)\.\s+(.*?)\.\s+[\d-]+(?: or [\d-]+)? Credit Hours?\.?$")


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
        m = TITLE.match(clean(title_p.get_text(" "))) if title_p else None
        if not m:
            continue  # not a course block, or a title line in an unexpected form
        desc_p = block.select_one("p.courseblockdesc")
        prereqs = [clean(p.get_text(" ")) for p in block.select("p.courseblockextra")
                   if clean(p.get_text(" ")).startswith("Prerequisite")]
        rows.append({
            "course_code": f"{m.group(1)} {m.group(2)}",
            "title": m.group(3),
            "description": clean(desc_p.get_text(" ")) if desc_p else "",
            "prerequisites": re.sub(r"^Prerequisites?:\s*", "", " ".join(prereqs)),
            "description_url": url,
            "description_file": rel(path),
        })
    return rows


# Script entry point: read the newest snapshot of each subject page, write the CSV, and
# print the catalog title of every course the plan names (for the year-mismatch review).
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
    plan_csv = SCHOOL.processed / "plan_parsed.csv"
    if plan_csv.exists():
        plan = pd.read_csv(plan_csv, dtype=str, keep_default_na=False)
        titles = {r["course_code"]: r["title"] for r in rows}
        codes = set(plan["course_code"]) | {o for opts in plan["options"] if opts for o in opts.split("; ")}
        print("2026-27 catalog titles of the plan's courses (check against the 2025-26 plan):")
        for code in sorted(codes - {""}):
            print(f"  {code}: {titles.get(code, '(not in the catalog pages)')}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(sorted(set(failures))))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
