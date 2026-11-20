"""Write the source links behind each school's plan, for the credits view's evidence.

Shared step over all displayed schools (specs/13-credits-view.md, "Evidence"). The
credits view shows, for any school and subject area, which published page the plan rows
came from and which page states the degree total. Those URLs live in each school's
data/raw/<id>/sources.csv (written by collect_<school>.py when the file was downloaded),
but data/raw/ is not published and the pages may only read data/processed/ (CLAUDE.md),
so this step copies the needed entries there.

Reads:

- data/reference/schools.csv (through displayed_school_ids() and load_school()), for
  each school's `credits_source` pattern (the file that states the total) and notes.
- data/processed/<id>/required_courses.json, for the `source_file` of every plan row.
- data/raw/<id>/sources.csv, for each file's URL, description, and retrieval date.

Writes data/processed/sources.json: {school_id: {"files": {file name: {url,
description, retrieved_date}}, "plan_files": [...], "total_file": name}}. Only files
the plan rows or the stated total actually use are copied, so nothing in it is unused.

Usage:
    python src/build_sources.py
"""

import json

import pandas as pd

from common import ROOT, displayed_school_ids, load_school, rel

PROCESSED = ROOT / "data" / "processed"
OUT_JSON = PROCESSED / "sources.json"


# Build one school's entry: the plan files its rows cite, the file that states the
# degree total, and the URL record of each. Fails loudly if a file has no URL, so the
# evidence never shows a source that can't be followed back to the web.
def school_sources(sid: str) -> dict:
    school = load_school(sid)
    rows = json.loads((PROCESSED / sid / "required_courses.json").read_text(encoding="utf-8"))
    # dtype=str + keep_default_na=False: read every cell as written (no NaN for blanks).
    src = pd.read_csv(ROOT / "data" / "raw" / sid / "sources.csv", dtype=str, keep_default_na=False)
    by_file = {r["file"]: r for r in src.to_dict("records")}

    # Row source_file values are repo paths (data/raw/uc/...); sources.csv keys are paths
    # relative to the school's raw folder, so compare by the name inside that folder.
    raw_dir = f"data/raw/{sid}/"
    plan_files = sorted({r["source_file"].removeprefix(raw_dir) for r in rows if r.get("source_file")})

    # credits_source in schools.csv is a glob ("*_bs-cs-catalog.html") because the file
    # names start with the download date; newest() picks the latest snapshot, the same
    # file validate.py checks the stated total against.
    total_file = school.newest(school.credits_source).name

    files = {}
    for f in [*plan_files, total_file]:
        rec = by_file.get(f)
        if rec is None or not rec["url"]:
            raise SystemExit(f"{sid}: {f} has no URL in {rel(ROOT / raw_dir / 'sources.csv')}")
        files[f] = {"url": rec["url"], "description": rec["description"], "retrieved_date": rec["retrieved_date"]}
    return {"files": files, "plan_files": plan_files, "total_file": total_file}


# Script entry point: one entry per displayed school, in registry order.
def main() -> None:
    out = {sid: school_sources(sid) for sid in displayed_school_ids()}
    OUT_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    n_files = sum(len(v["files"]) for v in out.values())
    print(f"Wrote {n_files} source links for {len(out)} schools to {rel(OUT_JSON)}")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
