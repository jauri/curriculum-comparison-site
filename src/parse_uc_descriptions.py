"""Read UC's official course descriptions from the saved Catalyst pages.

UC's school-specific description parser (phase 2, step 9). It reads every course detail
page that collect_uc_courses.py saved in data/raw/uc/courses/ and writes
data/processed/uc/official_descriptions.csv, one row per course code, with the columns in
common.OFFICIAL_COLUMNS. The shared describe.py then attaches this text to the plan rows
and gives requirement slots their generic descriptions.

Catalyst puts the course text and an auto-generated prerequisite statement in the same
field ("... - Prerequisite Definition: To take this course you must: ..."). The two are
split into `description` and `prerequisites`; prerequisites are a signal for course
matching in step 6.

Pages for courses that aren't plan rows (the science options, e.g. BIOL1081) are read
too. describe.py uses only the codes it needs.

Usage:
    python src/parse_uc_descriptions.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("uc")
COURSES_DIR = SCHOOL.raw / "courses"
MANIFEST = SCHOOL.raw / "sources.csv"
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"

# The PeopleSoft element that holds a course's long description. The "$0" suffix is
# PeopleSoft's row number on the page; each saved page shows exactly one course.
DESCR_ID = "SSR_CRSE_OFF_VW_DESCRLONG$0"
# Where the auto-generated prerequisite statement starts. \s* tolerates the varying
# whitespace around the dash; everything after the match is the prerequisite text.
PREREQ_SPLIT = re.compile(r"\s*-\s*Prerequisite Definition:\s*")
# A saved page's filename: date, "_catalyst_", then the code without its space, e.g.
# 2026-10-17_catalyst_CS2028C.html. Groups: subject (2-5 capitals) and number (4 digits
# plus an optional letter suffix such as the "C" in 2028C).
PAGE_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}_catalyst_([A-Z]{2,5})(\d{4}[A-Z]?)\.html$")


# Tidy one line of catalog text: collapse runs of spaces/tabs (some numbered lists use
# tabs after "1.") into single spaces. Newlines are handled by the caller.
def squash(line: str) -> str:
    """Collapse internal whitespace in a single line and trim the ends."""
    return re.sub(r"\s+", " ", line).strip()


# Read the official description and prerequisites from one saved Catalyst page.
# get_text("\n") turns each <br /> into a line break, which keeps UC's numbered topic
# lists (CS1100, CS2028C, CS4033) one item per line instead of one run-on paragraph.
# Blank lines (e.g. a trailing <br /> before the prerequisite part) are dropped.
def read_official(path: Path) -> tuple[str, str]:
    """Return (description, prerequisites) from a saved Catalyst course page."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    span = soup.find("span", id=DESCR_ID)
    if span is None:
        return "", ""
    lines = [squash(ln) for ln in span.get_text("\n").splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    # maxsplit=1: split at the first prerequisite marker only. Pages without one
    # (e.g. CS3093C, IT2030C) give a one-element list, so the prerequisites are "".
    parts = PREREQ_SPLIT.split(text, maxsplit=1)
    description = parts[0].strip()
    prerequisites = squash(parts[1]) if len(parts) > 1 else ""
    return description, prerequisites


# Map each saved course page to the URL it came from, using the download manifest
# (sources.csv). Catalyst serves every course from the same form-post URL, so this is
# the catalog's address rather than a per-course link; the saved file pins down which
# course it was.
def source_urls() -> dict[str, str]:
    """Return {file path relative to data/raw/uc/: url} from sources.csv."""
    manifest = pd.read_csv(MANIFEST)
    return dict(zip(manifest["file"], manifest["url"]))  # zip pairs the two columns row by row


# Find the newest saved page for each course code. Filenames start with an ISO date, so
# in sorted order a later snapshot of the same course overwrites an earlier one in the
# dict, leaving the newest.
def course_pages() -> dict[str, Path]:
    """Return {course code like 'CS 2028C': newest saved Catalyst page}."""
    pages = {}
    for path in sorted(COURSES_DIR.glob("*_catalyst_*.html")):
        m = PAGE_NAME.match(path.name)
        if m:
            pages[f"{m.group(1)} {m.group(2)}"] = path
    return pages


# Script entry point: read every saved page and write one row per course code.
def main() -> None:
    urls = source_urls()
    rows, failures = [], []
    for code, page in course_pages().items():
        desc, pre = read_official(page)
        manifest_key = page.relative_to(SCHOOL.raw).as_posix()  # e.g. courses/2026-..._CS2028C.html
        rows.append({
            "course_code": code,
            "description": desc,
            "prerequisites": pre,
            "description_url": urls.get(manifest_key, ""),  # dict.get with a default: "" if not logged
            "description_file": rel(page),
        })
        if not desc:
            failures.append(f"No description field found on {page.name}.")
        if not urls.get(manifest_key):
            failures.append(f"{manifest_key} is missing from sources.csv, so it has no description_url.")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OFFICIAL_COLUMNS).to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(rows)} official descriptions to {rel(OUT_CSV)}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
