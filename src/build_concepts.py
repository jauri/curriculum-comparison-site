"""Write the concept tags of every school as one processed table, for the web views.

Step 18 of specs/plan.md (specs/08-concepts.md, step C), first part. The concept
alignment view (specs/10-concept-alignment-view.md) needs every school's tags joined
with their courses and concepts; the coverage table (concept_coverage) is the second
part of step 18 and is not built yet.

Reads:
- data/reference/<id>/concept_tags.csv (hand-reviewed tags, step 17)
- data/reference/concepts.csv (the vocabulary)
- data/processed/all_required_courses.csv (from build_combined.py)

Writes:
- data/processed/all_concept_tags.csv / .json: one line per tag that is not rejected
  and names a concept ("no concept" lines are left out), joined with its row (school,
  code, title, norm_semester, description) and its concept (name, group). The JSON
  adds `evidence_phrases`, the evidence cell split at " | ".
- data/processed/concepts.json: a copy of concepts.csv for the web views.

Nothing is judged here: every line is a reviewed (or proposed) tag copied as it is,
with columns looked up from the two other tables. Run src/check_concepts.py first; this
script still stops if a tag points at a row or concept it can't find, so a broken join
never reaches the views.

Usage:
    python src/build_concepts.py
"""

import json

import pandas as pd

from common import (ALL_COURSES_CSV, CONCEPTS_CSV, ROOT, all_school_ids, concept_scope_rows, load_school, rel,
                    split_evidence)

PROCESSED = ROOT / "data" / "processed"
OUT_CSV = PROCESSED / "all_concept_tags.csv"
OUT_JSON = PROCESSED / "all_concept_tags.json"
CONCEPTS_JSON = PROCESSED / "concepts.json"

# Output columns, in order: who (school and row), what (concept), and the tag itself.
COLUMNS = [
    "school_id", "institution", "course_code", "title", "norm_semester",
    "concept_id", "name", "group",
    "evidence_field", "evidence", "tag_confidence", "tag_status", "notes", "description",
]


# Read every school's concept_tags.csv into one DataFrame with a school_id column.
# Schools without a tag file are skipped (with a message), so a partial build still runs.
def load_all_tags() -> pd.DataFrame:
    frames = []
    for sid in all_school_ids():
        path = load_school(sid).reference / "concept_tags.csv"
        if not path.exists():
            print(f"Skipping {sid}: {rel(path)} not found.")
            continue
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        df.insert(0, "school_id", sid)  # insert(0, ...): make it the first column
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


# Script entry point: filter the tags, join them with rows and concepts, write the files.
def main() -> None:
    concepts = pd.read_csv(CONCEPTS_CSV, dtype=str, keep_default_na=False)
    rows = concept_scope_rows(pd.read_csv(ALL_COURSES_CSV, dtype=str, keep_default_na=False))
    tags = load_all_tags()

    # Keep tags that name a concept and were not rejected (08-concepts.md, step C:
    # coverage counts tags that are not rejected; "no concept" lines have no concept_id).
    tags = tags[(tags["concept_id"] != "") & (tags["tag_status"] != "rejected")]

    # Join with the rows on (school, code). The tag file calls the code match_key.
    # validate="many_to_one" makes pandas raise if a (school, code) appears twice in
    # `rows`, which would silently duplicate tags. indicator=True adds a _merge column
    # saying whether each tag found its row ("both") or not ("left_only").
    row_cols = ["school_id", "course_code", "institution", "title", "norm_semester", "description"]
    out = tags.rename(columns={"match_key": "course_code"}).merge(
        rows[row_cols], on=["school_id", "course_code"], how="left", validate="many_to_one", indicator=True)
    missing = out[out["_merge"] == "left_only"]
    if len(missing):
        lost = ", ".join(f"{r.school_id} {r.course_code}" for r in missing.itertuples())
        raise SystemExit(f"Tags for rows that are not in concept scope: {lost}. Run check_concepts.py.")
    out = out.drop(columns="_merge")

    # Same check for concepts: every tag's concept_id must be in the vocabulary.
    out = out.merge(concepts[["concept_id", "name", "group"]], on="concept_id", how="left")
    unknown = sorted(out.loc[out["name"].isna(), "concept_id"].unique())
    if unknown:
        raise SystemExit(f"Unknown concept ids: {', '.join(unknown)}. Run check_concepts.py.")

    out = out[COLUMNS]
    out.to_csv(OUT_CSV, index=False)
    # to_dict("records"): one plain dict per line. ensure_ascii=False keeps dashes and
    # accented characters readable in the file.
    records = out.to_dict("records")
    # The JSON also lists each tag's evidence phrases (the CSV keeps the " | "-joined
    # cell), so the views highlight every phrase without parsing the separator.
    for rec in records:
        rec["evidence_phrases"] = split_evidence(rec["evidence"])
    OUT_JSON.write_text(json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8")
    CONCEPTS_JSON.write_text(json.dumps(concepts.to_dict("records"), indent=1, ensure_ascii=False), encoding="utf-8")

    n_proposed = (out["tag_status"] == "proposed").sum()
    print(f"Wrote {len(out)} tags ({n_proposed} proposed) from {out['school_id'].nunique()} schools "
          f"to {rel(OUT_CSV)} and {OUT_JSON.name}; {len(concepts)} concepts to {rel(CONCEPTS_JSON)}.")


if __name__ == "__main__":  # run main() only when executed as a script, not on import
    main()
