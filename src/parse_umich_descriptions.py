"""Read Michigan's official course descriptions from the saved bulletin course guides.

Michigan's school-specific description parser (step 13, batch 2). Reads every course
guide that collect_umich.py imported (data/raw/umich/*_courses-<subject>.html; in step
13 only EECS) and writes data/processed/umich/official_descriptions.csv (columns in
common.OFFICIAL_COLUMNS).

The bulletin is a WordPress site. Each course is one <p> paragraph:
    <strong>EECS 281. Data Structures and Algorithms</strong><br/>
    <em>Advisory Prerequisite: ... Enforced Prerequisite: ... (4 credits)</em><br/>
    Description text ... <a href="https://atlas.ai.umich.edu/...">CourseProfile (ATLAS)</a>
The <strong> gives the code; the <em> parts give the prerequisites (with the trailing
"(4 credits)" removed); the text that remains once the <strong>, the <em> parts, and the
ATLAS link are removed is the description.

Courses without saved text (MATH, PHYS, CHEM in a login-only course guide; ENGR and
TCHNCLCM, whose guides Chrome did not save) get generic descriptions in
data/reference/umich/generic_descriptions.csv, keyed by course code.

Usage:
    python src/parse_umich_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("umich")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# The heading of a course paragraph: "EECS 281. Data Structures and Algorithms".
HEADING = re.compile(r"^([A-Z]+) (\d{3})\.")
CREDITS = re.compile(r"\s*\(\d+(?:-\d+)? credits?\)\.?\s*$")  # "(4 credits)" or "(3-4 credits)." at the end


# Collapse whitespace and drop the space get_text(" ") leaves before punctuation.
def clean(text: str) -> str:
    """Return whitespace- and punctuation-tidied text."""
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    return re.sub(r"\s+([.,;:)])", r"\1", text)  # \1 puts the punctuation back without the space


# Read all course paragraphs on one saved course guide.
def read_page(path: Path, url: str) -> list[dict]:
    """Return one official-description row per course paragraph on a guide page."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    rows = []
    for p in soup.select("p"):
        strong = p.find("strong")
        m = HEADING.match(clean(strong.get_text(" "))) if strong else None
        if not m:
            continue  # not a course paragraph
        prereq = clean(" ".join(em.get_text(" ") for em in p.find_all("em")))
        strong.decompose()  # decompose() deletes the tag and its text from the tree
        for tag in p.find_all("em") + [a for a in p.find_all("a") if "ATLAS" in a.get_text()]:
            tag.decompose()
        # A comma (between two <em> parts) or a period (after the last one) can be left
        # at the start; lstrip removes any of those characters from the left end.
        description = clean(p.get_text(" ")).lstrip(",. ")
        rows.append({"course_code": f"{m.group(1)} {m.group(2)}", "description": description,
                     "prerequisites": CREDITS.sub("", prereq), "description_url": url,
                     "description_file": rel(path)})
    return rows


# Script entry point: read the newest snapshot of each course guide.
def main() -> None:
    manifest = pd.read_csv(SCHOOL.raw / "sources.csv")
    urls = dict(zip(manifest["file"], manifest["url"]))  # zip pairs the two columns row by row
    newest = {}
    for path in sorted(SCHOOL.raw.glob("*_courses-*.html")):
        newest[path.name.split("_", 1)[1]] = path  # key without the date: later dates win
    rows = [r for path in newest.values() for r in read_page(path, urls.get(path.name, ""))]
    empty = sorted(r["course_code"] for r in rows if not r["description"])
    df = pd.DataFrame([r for r in rows if r["description"]], columns=OFFICIAL_COLUMNS)
    df = df.drop_duplicates("course_code")  # a course listed twice on a page keeps its first entry
    failures = [f"{f}: not in sources.csv" for f in df.loc[df["description_url"] == "", "description_file"]]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(df)} official descriptions from {len(newest)} course guides to {rel(OUT_CSV)}")
    if empty:
        print(f"Skipped (course paragraph without description text): {', '.join(empty)}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(sorted(set(failures))))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
