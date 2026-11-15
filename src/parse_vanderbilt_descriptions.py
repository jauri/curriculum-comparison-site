"""Read Vanderbilt's official course descriptions from the saved catalog course records.

Vanderbilt's school-specific description parser (batch 5). Reads every course record
saved by collect_vanderbilt.py (data/raw/vanderbilt/courses/<date>_<CODE>.json, from
the 2026-27 Undergraduate Catalog's Kuali API) and writes
data/processed/vanderbilt/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

Each record is JSON with "__catalogCourseId" ("CS2201"), "title", and "description",
an HTML fragment such as

    <p>Also listed as ECE 2201. Continuation of CS 1101. ... Prerequisite: CS 1101 or
    1104. FALL, SPRING. [3]</p>

The text after "Prerequisite:" (or "Corequisite:") up to the end becomes
`prerequisites`. The bracketed credit hours at the very end ("[3]", "[1-3]") are
dropped: they are not description text (the roadmap gives each course's hours), and
left in place they make describe.py's cut-off check fire. The offering terms
("FALL, SPRING.") are kept as the catalog shows them.

Usage:
    python src/parse_vanderbilt_descriptions.py
"""

import json
import re

import pandas as pd
from bs4 import BeautifulSoup

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("vanderbilt")
# Where the requisites start: "Prerequisite:", "Prerequisites:", "Corequisite:", or
# "Prerequisite or corequisite:" (?: ... ) groups without capturing; IGNORECASE because
# the catalog capitalizes inconsistently.
REQ = re.compile(r"\b(?:Pre|Co)requisites?(?: or corequisites?)?:", re.IGNORECASE)
# "CS2201" -> "CS 2201": subject letters, then the number and any suffix.
COURSE_ID = re.compile(r"^([A-Z]+)(\d{4}[A-Z]?)$")


# Plain text of a record's HTML description, whitespace collapsed.
def plain(html: str) -> str:
    """Return the description's text without tags."""
    return re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ")).strip()


# Entry point: one row per newest saved record.
def main() -> None:
    manifest = pd.read_csv(SCHOOL.raw / "sources.csv")
    urls = dict(zip(manifest["file"], manifest["url"]))  # zip pairs the two columns row by row
    newest = {}
    for path in sorted((SCHOOL.raw / "courses").glob("*_*.json")):
        newest[path.name.split("_", 1)[1]] = path  # key without the date: later dates win
    rows, empty = [], []
    for path in newest.values():
        record = json.loads(path.read_text(encoding="utf-8"))
        m = COURSE_ID.match(record["__catalogCourseId"])
        # Drop the trailing credit marker: " [3]", " [1-3]", " [Variable credit: 1-3]".
        text = re.sub(r"\s*\[[^\]]*\d\]$", "", plain(record.get("description", "")))
        if not m or not text:
            empty.append(path.name)
            continue
        hit = REQ.search(text)
        description = text[:hit.start()].strip() if hit else text
        prereq = text[hit.start():].strip() if hit else ""
        rows.append({"course_code": f"{m.group(1)} {m.group(2)}", "description": description,
                     "prerequisites": prereq, "description_url": urls.get(f"courses/{path.name}", ""),
                     "description_file": rel(path)})
    out = SCHOOL.processed / "official_descriptions.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OFFICIAL_COLUMNS).to_csv(out, index=False)
    print(f"Wrote {len(rows)} official descriptions to {rel(out)}")
    if empty:
        print(f"Skipped (no description text): {', '.join(empty)}")
    missing = [r["description_file"] for r in rows if not r["description_url"]]
    if missing:
        raise SystemExit("CHECKS FAILED: not in sources.csv:\n  " + "\n  ".join(missing))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
