"""Read Utah's official course descriptions from the saved Coursedog courses response.

Utah's school-specific description parser (batch 4). Reads the newest saved courses API
response (data/raw/utah/*_cs-bs-courses-api.json, saved through Chrome by
collect_utah.py) and writes data/processed/utah/official_descriptions.csv (columns in
common.OFFICIAL_COLUMNS).

The response is one JSON object keyed "<course id>-<effective date>"; each record has
the compact code ("CS1420"), the titles, and the catalog "description" text. Utah
stores prerequisites as structured rules (course ids and conditions), not as text, so
`prerequisites` is left blank rather than rebuilt from those rules.

Usage:
    python src/parse_utah_descriptions.py
"""

import json
import re

import pandas as pd

from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("utah")
OUT_CSV = SCHOOL.processed / "official_descriptions.csv"


# Entry point: one row per course record with description text.
def main() -> None:
    path = SCHOOL.newest("*_cs-bs-courses-api.json")
    manifest = pd.read_csv(SCHOOL.raw / "sources.csv")
    url = dict(zip(manifest["file"], manifest["url"])).get(path.name, "")  # zip pairs file names with URLs
    if not url:
        raise SystemExit(f"{rel(path)} is not in sources.csv.")
    rows = []
    for rec in json.loads(path.read_text(encoding="utf-8")).values():
        m = re.fullmatch(r"([A-Z]+)(\d{4})", rec["code"])  # "CS1420" -> ("CS", "1420")
        text = re.sub(r"\s+", " ", rec.get("description") or "").strip()
        if m and text:
            rows.append({"course_code": f"{m.group(1)} {m.group(2)}", "description": text, "prerequisites": "",
                         "description_url": url, "description_file": rel(path)})
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OFFICIAL_COLUMNS).to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(rows)} official descriptions to {rel(OUT_CSV)}")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
