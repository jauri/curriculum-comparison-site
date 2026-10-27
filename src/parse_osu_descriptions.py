"""Read Ohio State's official course descriptions from the saved class-search API files.

Ohio State's school-specific description parser (phase 2, step 10). Reads every JSON file
that collect_osu_courses.py saved in data/raw/osu/courses/ and writes
data/processed/osu/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Each saved file is one API response: a list of class sections, each carrying a copy of
its course's catalog data (title, description, credit hours). The course itself is the
first entry whose subject and base catalog number match the file name. Some courses
have decimal variants (ENGR 1181.01 / .02 "Scholars", STAT 3470.01 / .02); the lowest
variant, the standard version, is used.

The API puts the prerequisite statement at the end of the description, after a line
break: "...layered data representation.\\nPrereq: 1212, 1221, ...". The two parts are
split into `description` and `prerequisites`.

parse_osu.py imports load_courses() to take official titles and credit hours, because
the curriculum sheet's sample schedule lists course codes without titles.

Usage:
    python src/parse_osu_descriptions.py
"""

import json
import re
from pathlib import Path

import pandas as pd

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("osu")
COURSES_DIR = SCHOOL.raw / "courses"
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# Saved filename: date, "_osu-classes_", subject, base number, e.g.
# 2026-10-17_osu-classes_PHYSICS1250.json -> ("PHYSICS", "1250").
FILE_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}_osu-classes_([A-Z]+)(\d{4})\.json$")
# Where the prerequisite statement starts: a "Prereq" or "Concur" sentence after the
# course text. (?=...) is a lookahead, so the split keeps the word "Prereq" itself.
PREREQ_SPLIT = re.compile(r"\s*\n\s*(?=(?:Prereq|Concur))")


# Pick the course record out of one saved API response. Returns None if the response
# doesn't contain the course (collect_osu_courses.py only saves files that do).
def course_record(path: Path, subject: str, number: str) -> dict | None:
    """Return the catalog data for subject/number from a saved API response."""
    courses = [c["course"] for c in json.loads(path.read_text(encoding="utf-8"))["data"]["courses"]]
    matches = [c for c in courses if c["subject"] == subject and c["catalogNumber"].split(".")[0] == number]
    # min() by catalogNumber picks the lowest variant ("1181.01" before "1181.02").
    return min(matches, key=lambda c: c["catalogNumber"]) if matches else None


# Read every saved course file (newest snapshot per course) into one dict per course.
# Sorted order means a later date replaces an earlier one for the same course.
def load_courses() -> dict[str, dict]:
    """Return {'CSE 2221': {title, credits_min, credits_max, description, prerequisites, ...}}."""
    urls = dict(zip(*[pd.read_csv(SCHOOL.raw / "sources.csv")[c] for c in ("file", "url")]))  # file -> url
    out = {}
    for path in sorted(COURSES_DIR.glob("*_osu-classes_*.json")):
        m = FILE_NAME.match(path.name)
        if not m:
            continue
        subject, number = m.groups()  # groups() returns all captured groups as a tuple
        rec = course_record(path, subject, number)
        if rec is None:
            continue
        # maxsplit=1: only the first Prereq/Concur sentence starts the prerequisite part.
        parts = PREREQ_SPLIT.split(rec["description"].strip(), maxsplit=1)
        out[f"{subject} {number}"] = {
            "title": rec["title"],
            "catalog_number": rec["catalogNumber"],  # e.g. "1181.01", kept for notes
            "credits_min": rec["minUnits"],
            "credits_max": rec["maxUnits"],
            "description": re.sub(r"\s+", " ", parts[0]).strip(),
            "prerequisites": re.sub(r"\s+", " ", parts[1]).strip() if len(parts) > 1 else "",
            "description_url": urls.get(path.relative_to(SCHOOL.raw).as_posix(), ""),
            "description_file": rel(path),
        }
    return out


# Script entry point: write one row per course with the shared column set.
def main() -> None:
    courses = load_courses()
    rows = [{"course_code": code, **{k: c[k] for k in OFFICIAL_COLUMNS[1:]}} for code, c in courses.items()]
    failures = [f"{r['course_code']}: no description" for r in rows if not r["description"]]
    failures += [f"{r['course_code']}: not in sources.csv" for r in rows if not r["description_url"]]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OFFICIAL_COLUMNS).to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(rows)} official descriptions to {rel(OUT_CSV)}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
