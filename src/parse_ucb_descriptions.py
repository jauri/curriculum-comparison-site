"""Read UC Berkeley's official course descriptions from the saved catalog course pages.

UC Berkeley's school-specific description parser (step 13). Reads every course page
that collect_ucb.py saved (data/raw/ucb/courses/*_<CODE>.html, one page per course) and
writes data/processed/ucb/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Berkeley's catalog runs on Coursedog. Each course page is rendered on the server as a
list of labeled fields: an element with class "field-label" ("Subject", "Course Number",
"Course Title", "Course Description", "Units", ...) followed by its value element. The
code is built from Subject + Course Number, and the description is the "Course
Description" value. The 2026-27 pages have no prerequisite field, so that column is
blank.

Usage:
    python src/parse_ucb_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("ucb")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"


# Tidy text: non-breaking spaces become spaces and runs of whitespace collapse.
def clean(text: str) -> str:
    """Return whitespace-tidied text."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


# Read the labeled fields of one course page into a dict. A label can repeat (e.g.
# "Minimum Hours" for each format), so only the first value of each label is kept.
def fields(path: Path) -> dict[str, str]:
    """Return {field label: value text} for a saved course page."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    out = {}
    for label in soup.select(".field-label"):
        value = label.find_next_sibling()  # the value element right after its label
        key = clean(label.get_text(" "))
        if value is not None and key not in out:
            out[key] = clean(value.get_text(" "))
    return out


# Script entry point: one row per saved course page (newest snapshot of each).
def main() -> None:
    manifest = pd.read_csv(SCHOOL.raw / "sources.csv")
    urls = dict(zip(manifest["file"], manifest["url"]))  # zip pairs the two columns row by row
    newest = {}
    for path in sorted((SCHOOL.raw / "courses").glob("*_*.html")):
        newest[path.name.split("_", 1)[1]] = path  # key without the date: later dates win
    rows, failures = [], []
    for path in newest.values():
        f = fields(path)
        code = f"{f.get('Subject', '')} {f.get('Course Number', '')}".strip()
        # The manifest stores names relative to data/raw/ucb/, e.g. "courses/2026-..._MATH51.html".
        url = urls.get(f"courses/{path.name}", "")
        expected = path.stem.split("_", 1)[1]  # "COMPSCI61A" from the filename
        if code.replace(" ", "") != expected:
            failures.append(f"{rel(path)}: page is for '{code}', expected {expected}.")
        if not f.get("Course Description"):
            failures.append(f"{rel(path)}: no Course Description field.")
        if not url:
            failures.append(f"{rel(path)}: not in sources.csv.")
        rows.append({"course_code": code, "description": f.get("Course Description", ""), "prerequisites": "",
                     "description_url": url, "description_file": rel(path)})
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OFFICIAL_COLUMNS).to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(rows)} official descriptions from {len(newest)} course pages to {rel(OUT_CSV)}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
