"""Read Minnesota's official course descriptions from the saved catalog course pages.

Minnesota's school-specific description parser (step 13, batch 2). Reads every course
page that collect_umn.py saved (data/raw/umn/courses/*.html) and writes
data/processed/umn/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Each page is a Coursedog course page whose course record is embedded as Nuxt JSON
(read with parse_umn.course_record). The record's `description` holds the catalog text
followed by a blank line and "prereq: ..." when the course has prerequisites, so the
text is split there: before is `description`, after is `prerequisites`. The record's
code has no space ("CSCI4041"); the plan's form ("CSCI 4041") is used as the key.

Usage:
    python src/parse_umn_descriptions.py
"""

import re

import pandas as pd

from common import OFFICIAL_COLUMNS, load_school, rel
from parse_umn import course_record

SCHOOL = load_school("umn")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"
# The prerequisite marker, usually on its own paragraph: "...\n\nprereq: CSCI 1933 ..."
# or "prereq or concurrent: MATH 1271/1371 ..." (PHYS 1301W). (?: ...)? makes the
# "or concurrent" part optional without capturing it.
PREREQ = re.compile(r"\s*\bprereq(?: or concurrent)?:\s*", re.IGNORECASE)


# Script entry point: one row per saved course page (newest snapshot per course).
def main() -> None:
    manifest = pd.read_csv(SCHOOL.raw / "sources.csv")
    urls = dict(zip(manifest["file"], manifest["url"]))  # zip pairs the two columns row by row
    newest = {}
    for path in sorted((SCHOOL.raw / "courses").glob("*.html")):
        newest[path.name.split("_", 1)[1]] = path  # key without the date: later dates win
    rows, failures = [], []
    for path in newest.values():
        rec = course_record(path)
        code = re.sub(r"^([A-Z]+)(\d)", r"\1 \2", rec["code"])  # "CSCI4041" -> "CSCI 4041"
        # split(..., maxsplit=1) gives [description] or [description, prerequisites].
        parts = PREREQ.split(rec.get("description") or "", maxsplit=1)
        name = f"courses/{path.name}"  # manifest file names are relative to data/raw/umn/
        if name not in urls:
            failures.append(f"{rel(path)}: not in sources.csv")
        rows.append({"course_code": code, "description": re.sub(r"\s+", " ", parts[0]).strip(),
                     "prerequisites": parts[1].strip() if len(parts) > 1 else "",
                     "description_url": urls.get(name, ""), "description_file": rel(path)})
    df = pd.DataFrame(rows, columns=OFFICIAL_COLUMNS)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(df)} official descriptions from {len(newest)} course pages to {rel(OUT_CSV)}")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
