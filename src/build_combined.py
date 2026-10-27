"""Stack every school's final table into one combined table, as CSV and JSON.

Shared step over all schools at once; step 14 of specs/plan.md (schema in
specs/04-outputs.md, "Combined table"). Reads, for each school in
data/reference/schools.csv order whose table has been built:

- data/processed/<id>/required_courses.csv (from build_outputs.py)
- data/processed/<id>/required_courses.json (same rows, with nested `matches`)

Writes:

- data/processed/all_required_courses.csv: every row, with `school_id` first.
- data/processed/all_required_courses.json: the same rows for the web views (the
  timeline view reads one file instead of sixteen), matches still nested.

Nothing is recomputed here: each row is copied from its school's table, so every value
still traces to that school's build. The script checks that the combined row count is
the sum of the per-school counts and that the CSV and JSON agree row for row.

Usage:
    python src/build_combined.py
"""

import json

import pandas as pd

from common import ROOT, all_school_ids, rel

PROCESSED = ROOT / "data" / "processed"
OUT_CSV = PROCESSED / "all_required_courses.csv"
OUT_JSON = PROCESSED / "all_required_courses.json"


# Script entry point: read each built school's table, stack them, write both files.
def main() -> None:
    frames, records, counts = [], [], {}
    for sid in all_school_ids():  # registry order: UC first, then the comparison set
        csv_path = PROCESSED / sid / "required_courses.csv"
        json_path = PROCESSED / sid / "required_courses.json"
        if not csv_path.exists():
            print(f"Skipping {sid}: {rel(csv_path)} not built yet.")
            continue
        # dtype=str + keep_default_na=False copy every cell exactly as written (blank
        # stays blank, "07" stays "07"), so the combined CSV is a faithful stack.
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
        df.insert(0, "school_id", sid)  # insert(0, ...): make it the first column
        rows = json.loads(json_path.read_text(encoding="utf-8"))
        if len(rows) != len(df):
            raise SystemExit(f"{sid}: JSON has {len(rows)} rows but the CSV has {len(df)}; rerun build_outputs.py.")
        # {"school_id": sid, **r} builds a new dict with school_id first, then the row's
        # own keys, so the JSON's key order matches the CSV's column order.
        records += [{"school_id": sid, **r} for r in rows]
        frames.append(df)
        counts[sid] = len(df)

    combined = pd.concat(frames, ignore_index=True)  # ignore_index: renumber rows 0..n-1
    if len(combined) != sum(counts.values()) or len(records) != len(combined):
        raise SystemExit("Combined row counts don't add up; nothing written.")
    # Same order on both sides: each JSON record's titles must line up with the CSV's.
    if [r["title"] for r in records] != combined["title"].tolist():
        raise SystemExit("CSV and JSON rows are out of order; nothing written.")

    combined.to_csv(OUT_CSV, index=False)
    # ensure_ascii=False keeps accented characters and dashes readable in the file.
    OUT_JSON.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(combined)} rows from {len(counts)} schools to {rel(OUT_CSV)} and {OUT_JSON.name}")
    print("  " + ", ".join(f"{sid} {n}" for sid, n in counts.items()))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
