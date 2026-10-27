"""Read Carnegie Mellon's official course descriptions from the saved department pages.

CMU's school-specific description parser (step 13, batch 3). Reads every department
course page that collect_cmu.py saved (data/raw/cmu/*_courses-<dept>.html) and writes
data/processed/cmu/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

CMU's CourseLeaf course lists use definition lists rather than the usual divs:
    <dl class="courseblock">
      <dt>15-112 Fundamentals of Programming and Computer Science</dt>
      <dd>All Semesters: 12 units<br/>Description ...<br/>Prerequisites: ...<br/>
          Course Website: ...</dd>
    </dl>
The <dd> is split at its <br/> line breaks: the first line is the offering pattern and
units, a line starting "Prerequisite" becomes `prerequisites`, lines starting
"Corequisite" or "Course Website" are dropped, and the rest is the description. Every
course on the page is written (describe.py uses only the ones in the plan); a block
with no description text is skipped and listed.

Usage:
    python src/parse_cmu_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("cmu")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
CODE = re.compile(r"^(\d{2}-\d{3}) ")
# Lines of the <dd> that are neither description nor prerequisite.
DROP = ("Corequisite", "Course Website", "Course website")


# Tidy CourseLeaf text: non-breaking spaces become spaces, runs of whitespace collapse,
# and the space get_text(" ") leaves before punctuation after a link is removed.
def clean(text: str) -> str:
    """Return whitespace- and punctuation-tidied text."""
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    return re.sub(r"\s+([.,;:)])", r"\1", text)  # \1 puts the punctuation back without the space


# Split a <dd> into its lines: <br/> tags become a marker, then the text is split on it.
def dd_lines(dd) -> list[str]:
    """Return the non-empty, cleaned lines of a course block's <dd>."""
    for br in dd.find_all("br"):
        br.replace_with("\n")  # a real newline survives get_text(), so the lines can be split
    return [line for line in (clean(x) for x in dd.get_text(" ").split("\n")) if line]


# Read all course blocks on one saved department page.
def read_page(path: Path, url: str) -> list[dict]:
    """Return one official-description row per course block on a department page."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    rows = []
    for block in soup.select("dl.courseblock"):
        dt, dd = block.find("dt"), block.find("dd")
        m = CODE.match(clean(dt.get_text(" "))) if dt else None
        if not m or dd is None:
            continue  # not a course block (none seen, but don't guess)
        lines = dd_lines(dd)[1:]  # [1:] skips "Fall and Spring: 12 units"
        desc = [x for x in lines if not x.startswith(("Prerequisite",) + DROP)]
        pre = [x for x in lines if x.startswith("Prerequisite")]
        rows.append({
            "course_code": m.group(1),
            "description": " ".join(desc),
            "prerequisites": re.sub(r"^Prerequisites?:\s*", "", " ".join(pre)),
            "description_url": url,
            "description_file": rel(path),
        })
    return rows


# Script entry point: read the newest snapshot of each department page.
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
    print(f"Wrote {len(rows)} official descriptions from {len(newest)} department pages to {rel(OUT_CSV)}")
    if empty:
        print(f"Skipped (course block without description text): {', '.join(empty)}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(sorted(set(failures))))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
