"""Check the concept tags of one school, or of every school, against the vocabulary.

Step 17 of specs/plan.md (specs/08-concepts.md, step B). Each school's in-scope CS
courses are tagged with concepts from data/reference/concepts.csv in the hand-reviewed
file data/reference/<id>/concept_tags.csv: one line per (course, concept), each with an
evidence phrase copied word for word from the course's title or description.

Like check_canonical.py, this script only reads. It never writes or "fixes" a tag file,
because a silent rewrite could undo a reviewed decision. Checks:

- every concept_id exists in concepts.csv, and every concept is used at least once
  (across all schools, so this check runs only once every school has a tag file),
- every match_key is an in-scope row of the school (CS, named, official description),
- every in-scope row has at least one line; a "no concept" line (empty concept_id)
  has a note saying why and is the row's only line,
- every evidence phrase occurs in its field, after lowercasing and collapsing
  whitespace (so case and line breaks may differ from the source); an evidence cell
  may list several phrases separated by " | ", each checked on its own, none repeated,
- no duplicate (row, concept) lines,
- evidence_field, tag_confidence, and tag_status hold allowed values.

It then prints each row with its tags, for review.

Reads:
- data/reference/concepts.csv
- data/reference/<id>/concept_tags.csv
- data/processed/all_required_courses.csv (from build_combined.py; in-scope rows come
  from concept_scope_rows() in common.py, the same rule the preview uses)

Usage:
    python src/check_concepts.py              # every school
    python src/check_concepts.py --school uc  # one school
"""

import argparse

import pandas as pd

from common import (ALL_COURSES_CSV, CONCEPTS_CSV, EVIDENCE_SEP, all_school_ids, concept_scope_rows, load_school,
                    rel, require, split_evidence)
# normalize() lowercases and collapses whitespace; shared with the preview so a phrase
# the preview highlights and a phrase the checker accepts follow the same rule.
from preview_concepts import normalize

# Allowed values (specs/08-concepts.md, concept_tags.csv).
FIELDS = {"description", "title"}
CONFIDENCES = {"high", "medium", "low"}
STATUSES = {"proposed", "approved", "rejected"}
COLUMNS = ["match_key", "concept_id", "evidence_field", "evidence", "tag_confidence", "tag_status", "notes"]


# Return the path of a school's tag file (kept in one place for main and the shared check).
def tags_path(school_id: str):
    return load_school(school_id).reference / "concept_tags.csv"


# Check one school's tag lines against its in-scope rows and the vocabulary. `rows` is
# that school's slice of concept_scope_rows(), indexed by course code. Returns failure
# messages, each prefixed with the school id so a run over every school stays readable.
def check_school(school_id: str, tags: pd.DataFrame, rows: pd.DataFrame, concept_ids: set[str]) -> list[str]:
    """Return failure messages for one school's concept_tags.csv."""
    failures = []
    p = f"{school_id}:"
    missing_cols = [c for c in COLUMNS if c not in tags.columns]
    if missing_cols:
        return [f"{p} missing columns {missing_cols}"]

    for i, t in tags.iterrows():
        # i + 2: CSV line number (1 for the header, and pandas counts from 0).
        where = f"{p} line {i + 2} ({t['match_key']}, {t['concept_id'] or 'no concept'})"
        if t["match_key"] not in rows.index:
            failures.append(f"{where}: match_key is not an in-scope row")
            continue
        if t["tag_status"] not in STATUSES:
            failures.append(f"{where}: tag_status '{t['tag_status']}' not in {sorted(STATUSES)}")
        if t["concept_id"] == "":
            # A "no concept" line: nothing to check against the text, but it must say why.
            if not t["notes"]:
                failures.append(f"{where}: a no-concept line needs a note saying why")
            continue
        if t["concept_id"] not in concept_ids:
            failures.append(f"{where}: unknown concept_id")
        if t["evidence_field"] not in FIELDS:
            failures.append(f"{where}: evidence_field '{t['evidence_field']}' not in {sorted(FIELDS)}")
            continue
        if t["tag_confidence"] not in CONFIDENCES:
            failures.append(f"{where}: tag_confidence '{t['tag_confidence']}' not in {sorted(CONFIDENCES)}")
        # A plain substring test on normalized text: the spec asks only that the phrase
        # occur in the field, so "process" in "processes" is allowed here; whether it is
        # the right sense is the reviewer's call.
        source = normalize(rows.at[t["match_key"], t["evidence_field"]])
        phrases = split_evidence(t["evidence"])
        if not phrases:
            failures.append(f"{where}: no evidence phrase")
        for phrase in phrases:
            if normalize(phrase) not in source:
                failures.append(f"{where}: evidence '{phrase}' not found in the {t['evidence_field']}")
        # The same phrase listed twice adds nothing and usually means a copy-paste slip.
        normalized = [normalize(ph) for ph in phrases]
        if len(set(normalized)) < len(normalized):
            failures.append(f"{where}: an evidence phrase is listed twice")

    # duplicated(keep=False) marks every copy, so each repeated pair is reported.
    dup = tags[tags["concept_id"] != ""].duplicated(["match_key", "concept_id"], keep=False)
    for key, cid in sorted(set(zip(tags.loc[dup[dup].index, "match_key"], tags.loc[dup[dup].index, "concept_id"]))):
        failures.append(f"{p} duplicate line for ({key}, {cid})")

    per_key = tags.groupby("match_key")["concept_id"].apply(list)  # each row's concept ids
    for key in rows.index:
        if key not in per_key.index:
            failures.append(f"{p} in-scope row {key} has no line")
        elif "" in per_key[key] and len(per_key[key]) > 1:
            failures.append(f"{p} {key} has a no-concept line and other lines")
    return failures


# Print each in-scope row with its tags (concept, confidence, status, evidence), in
# plan order, so the user can read a school's tags alongside the course titles.
def print_review(school_id: str, tags: pd.DataFrame, rows: pd.DataFrame) -> None:
    """Print one school's rows and their tags."""
    print(f"\n=== {school_id}: {rel(tags_path(school_id))}")
    for key, r in rows.iterrows():
        print(f"\n{key}  {r['title']}  (sem {r['norm_semester'] or '-'})")
        for t in tags[tags["match_key"] == key].itertuples():
            if t.concept_id == "":
                print(f"    (no concept)  {t.notes}")
                continue
            flag = "" if t.tag_confidence == "high" else f" [{t.tag_confidence}]"
            src = " (title)" if t.evidence_field == "title" else ""
            # Each phrase quoted on its own, so "a | b" reads as two phrases.
            quoted = EVIDENCE_SEP.join(f'"{ph}"' for ph in split_evidence(t.evidence))
            print(f"    {t.concept_id:<34} {t.tag_status:<9} {quoted}{src}{flag}")


# Script entry point: check the chosen school(s), print the review listing, and run
# the vocabulary-wide check (every concept used) when every school has a tag file.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--school", help="one school id (default: every school)")
    args = parser.parse_args()
    school_ids = [load_school(args.school).id] if args.school else all_school_ids()

    require([(CONCEPTS_CSV, "the reference file"), (ALL_COURSES_CSV, "build_combined.py")]
            + [(tags_path(s), "the reference file") for s in school_ids])
    # dtype=str + keep_default_na=False: every cell is text, and blanks stay "" (not NaN).
    concepts = pd.read_csv(CONCEPTS_CSV, dtype=str, keep_default_na=False)
    concept_ids = set(concepts["concept_id"])
    scope = concept_scope_rows(pd.read_csv(ALL_COURSES_CSV, dtype=str, keep_default_na=False))

    failures, n_lines = [], 0
    for sid in school_ids:
        tags = pd.read_csv(tags_path(sid), dtype=str, keep_default_na=False)
        rows = scope[scope["school_id"] == sid].set_index("course_code")
        failures += check_school(sid, tags, rows, concept_ids)
        print_review(sid, tags, rows)
        n_lines += len(tags)

    # "Every concept is used" is about the whole vocabulary, so it needs every school's
    # tags. Rejected tags don't count: a concept whose only tags were rejected is unused.
    all_paths = [tags_path(s) for s in all_school_ids()]
    if all(p.exists() for p in all_paths):
        every = pd.concat([pd.read_csv(p, dtype=str, keep_default_na=False) for p in all_paths])
        used = set(every.loc[every["tag_status"] != "rejected", "concept_id"])
        failures += [f"concept '{c}' is not used by any tag" for c in concepts["concept_id"] if c not in used]
    else:
        print("\n(Skipped the every-concept-used check: not every school has a tag file yet.)")

    print(f"\n{len(school_ids)} school(s), {n_lines} tag lines.")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All concept tag checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
