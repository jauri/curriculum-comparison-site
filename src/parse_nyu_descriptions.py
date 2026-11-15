"""Read NYU's official course descriptions from the saved bulletin subject pages.

NYU's school-specific description parser (batch 5). Reads every subject page that
collect_nyu.py saved (data/raw/nyu/*_courses-<subject>.html) and writes
data/processed/nyu/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Each subject page is a CourseLeaf list of <div class="courseblock"> elements, in a
newer template than Colorado's: there is no data-coursecode attribute, and each field
is a <span> whose class names it ("detail-code", "detail-title", "detail-hours_html",
"detail-prerequisites", ...). The description is a "courseblockextra" div in which
NYU appends campus-specific prerequisite notes after " | " separators ("... basics of
algorithm analysis. | Prerequisite for Brooklyn Students: ..."). So:
- course_code is the detail-code text ("CS-UY 1134");
- description is the courseblockextra text before the first " | ", without a trailing
  "ABET competencies: a,b,c, ..." list (accreditation outcome codes, not course content);
- prerequisites is the detail-prerequisites text without its "Prerequisites:" label,
  or, when a course has none, the Brooklyn (Tandon's campus) part of the
  courseblockextra text.

Usage:
    python src/parse_nyu_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("nyu")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# The Brooklyn-campus prerequisite note inside the description div, up to the next " | ".
# Written "Prerequisite for Brooklyn Students:", "Prereq for Brooklyn Students:", or
# "Prerequisites for Brooklyn Engineering Students:"; [^:]* skips the words before the colon.
BROOKLYN = re.compile(r"Prereq(?:uisites?)? for Brooklyn[^:]*:\s*([^|]*)")
# A trailing list of ABET outcome letters, e.g. "ABET competencies: a,b,c, e, f, g, k".
ABET = re.compile(r"\s*ABET competencies:.*$")


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
        code = block.select_one("span.detail-code")
        extra = block.select_one("div.courseblockextra")
        if code is None:
            continue  # not a course entry
        body = clean(extra.get_text(" ")) if extra else ""
        description = body.split(" | ")[0].strip()  # campus prerequisite notes follow the first " | "
        description = ABET.sub("", description)
        prereq_span = block.select_one("span.detail-prerequisites")
        if prereq_span:
            label = prereq_span.select_one("span.label")
            if label:
                label.decompose()  # drop the "Prerequisites:" label, keep the requirement
            prereq = clean(prereq_span.get_text(" "))
        else:
            m = BROOKLYN.search(body)
            prereq = m.group(1).strip() if m else ""
        rows.append({
            "course_code": clean(code.get_text(" ")),
            "description": description,
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
