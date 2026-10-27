"""Read UT Austin's official course descriptions from the saved catalog subject pages.

UT Austin's school-specific description parser (step 13). Reads every subject page that
collect_utaustin.py saved (data/raw/utaustin/*_courses-<subject>.html) and writes
data/processed/utaustin/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

UT's "Courses A-Z" pages are plain HTML, not CourseLeaf course blocks: each course is an
<h5> heading followed by a <p> with its description, e.g.

    <h5>C S X12. Introduction to Programming.</h5>
    <p>First part of a two-part sequence in programming. ...</p>

The "X" stands for the first digit of the course number, which at UT is the number of
credit hours: the catalog describes C S 312 (3 hours) under "C S X12", and the same text
covers a 1-hour or 4-hour version. Plans name the real number (C S 312), so this script
writes every course under its X-form and also writes a resolved row for each course
code the plan uses (read from plan_parsed.csv), so describe.py can look up "C S 312"
directly. These pages carry no prerequisites, so that column is blank.

Usage:
    python src/parse_utaustin_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("utaustin")
PLAN_CSV = SCHOOL.processed / "plan_parsed.csv"
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# A heading: subject (may contain a space, "C S"), "X" plus the rest of the number with
# optional letters, then ". Title." The title group is lazy so it stops at the final period.
HEADING = re.compile(r"^((?:[A-Z] )*[A-Z]+) X(\d{2}[A-Z]{0,2}(?:\.\d+)?)\.\s+(.+?)\.?$")


# Tidy text: non-breaking spaces become spaces and runs of whitespace collapse.
def clean(text: str) -> str:
    """Return whitespace-tidied text."""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


# Read every <h5> course heading on one subject page with the paragraph after it.
# Headings for topic umbrellas ("C S X09. Topics in Computer Science.") are followed
# directly by another heading, so they get no description and are skipped.
def read_page(path: Path, url: str) -> list[dict]:
    """Return one official-description row (X-form code) per described course."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    rows = []
    for h5 in soup.find_all("h5"):
        m = HEADING.match(clean(h5.get_text(" ")))
        if not m:
            continue
        nxt = h5.find_next_sibling()  # the element right after the heading
        if nxt is None or nxt.name != "p":
            continue  # an umbrella heading with no text of its own
        rows.append({
            "course_code": f"{m.group(1)} X{m.group(2)}",
            "description": clean(nxt.get_text(" ")),
            "prerequisites": "",
            "description_url": url,
            "description_file": rel(path),
        })
    return rows


# The course codes the plan uses: named courses plus every option of a choice slot.
def plan_codes() -> set[str]:
    """Return the course codes in plan_parsed.csv (courses and choice options)."""
    plan = pd.read_csv(PLAN_CSV, keep_default_na=False, dtype=str)
    codes = set(plan["course_code"]) - {""}
    for options in plan["options"]:
        codes |= {c for c in options.split("; ") if c}  # |= adds to the set in place
    return codes


# "C S 312" -> "C S X12": replace the first digit of the number (the credit hours) by X.
def x_form(code: str) -> str:
    """Return the catalog's X-form of a UT course code."""
    subject, number = code.rsplit(" ", 1)
    return f"{subject} X{number[1:]}"


# Script entry point: read the newest snapshot of each subject page, add resolved rows
# for the plan's codes, check, and write.
def main() -> None:
    manifest = pd.read_csv(SCHOOL.raw / "sources.csv")
    urls = dict(zip(manifest["file"], manifest["url"]))  # zip pairs the two columns row by row
    newest = {}
    for path in sorted(SCHOOL.raw.glob("*_courses-*.html")):
        newest[path.name.split("_", 1)[1]] = path  # key without the date: later dates win
    rows = [r for path in newest.values() for r in read_page(path, urls.get(path.name, ""))]
    by_x = {r["course_code"]: r for r in rows}

    failures = []
    for code in sorted(plan_codes()):
        if x_form(code) in by_x:
            # {**d, key: value} copies the dict with one field replaced.
            rows.append({**by_x[x_form(code)], "course_code": code})
        else:
            failures.append(f"{code}: no catalog entry {x_form(code)}")
    failures += [f"{r['description_file']}: not in sources.csv" for r in rows if not r["description_url"]]

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OFFICIAL_COLUMNS).to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(rows)} official descriptions ({len(by_x)} X-form courses from {len(newest)} "
          f"subject pages, plus {len(rows) - len(by_x)} plan codes resolved) to {rel(OUT_CSV)}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(sorted(set(failures))))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
