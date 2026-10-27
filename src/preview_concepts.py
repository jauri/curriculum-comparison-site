"""Write a review aid for the concept vocabulary: where each concept's synonyms occur.

Step 16 of specs/plan.md (specs/08-concepts.md, step A). Before any course is tagged,
the user reviews data/reference/concepts.csv. To judge a concept's name, definition,
and granularity, it helps to see which in-scope descriptions use its synonyms. This
script finds those occurrences by plain phrase matching and writes them for the review
page (web/concepts_review.html).

These matches are NOT tags. A synonym can occur in a sense the concept doesn't mean
("functions" in a discrete-math course is not programming functions), and a concept can
be stated in words no synonym covers. Tags are proposed by reading each description
(step 17); the page says so.

Reads:
- data/reference/concepts.csv (the draft vocabulary)
- data/processed/all_required_courses.csv (from build_combined.py)

Writes:
- data/processed/concepts_preview.json: {"concepts": [...], "rows": [...]}, where each
  concept lists its matching rows with the phrase found, and `rows` lists every
  in-scope row (so the page can show a full description on demand).

Since step 17 each row also carries its proposed tags (`tags`, from
data/reference/<id>/concept_tags.csv when the school has one), so the tag review page
(web/concept_tags_review.html) can show them without reading reference files itself.
Run src/check_concepts.py first: this script copies the tags as they are. Each row also
carries its untagged notes (`untagged_notes`, from data/reference/<id>/untagged_notes.csv;
run src/check_untagged.py first), so the page can show why the rest of the text is not
a concept.

It also checks the vocabulary's shape (unique ids, every synonym found somewhere,
first_seen pointing at a real in-scope row) and stops without writing if any check
fails, so the page never shows a vocabulary that doesn't trace to the descriptions.

Usage:
    python src/preview_concepts.py
"""

import json
import re

import pandas as pd

from common import (ALL_COURSES_CSV, CONCEPTS_CSV, ROOT, all_school_ids, concept_scope_rows, load_school, rel,
                    split_evidence)

OUT_JSON = ROOT / "data" / "processed" / "concepts_preview.json"


# Lowercase and collapse runs of whitespace, the same normalization the checker uses
# for evidence phrases (08-concepts.md), so "Hash  Tables" matches "hash tables".
def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().lower()


# Build a regex that finds a synonym as a whole phrase. re.escape makes characters like
# "+" in "C++" or "/" in "I/O" literal. The lookarounds (?<![a-z0-9]) and (?![a-z0-9])
# require that no letter or digit touches the phrase on either side, so "heap" does not
# match inside "heaps" and "C" does not match inside "CS". (\b would fail for "C++",
# whose last character is not a word character.)
def phrase_pattern(phrase: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(normalize(phrase)) + r"(?![a-z0-9])")


# Split a "; "-separated synonyms cell into a list, dropping empty pieces.
def split_synonyms(cell: str) -> list[str]:
    return [s.strip() for s in cell.split(";") if s.strip()]


# Return every school's tag lines (step 17), keyed by (school_id, course code), as
# dicts with the concept_tags.csv columns. A school with no tag file yet contributes
# nothing, so the vocabulary page still works before tagging is finished.
def load_tags() -> dict[tuple[str, str], list[dict]]:
    tags = {}
    for sid in all_school_ids():
        path = load_school(sid).reference / "concept_tags.csv"
        if not path.exists():
            continue
        # to_dict("records"): one plain dict per CSV line, ready for json.dumps.
        for t in pd.read_csv(path, dtype=str, keep_default_na=False).to_dict("records"):
            # The evidence cell may list several " | "-separated phrases; the pages get
            # them as a list so they never have to know the separator.
            t["evidence_phrases"] = split_evidence(t["evidence"])
            tags.setdefault((sid, t.pop("match_key")), []).append(t)
    return tags


# Return every school's untagged notes (text judged not to be a concept, with a
# reason), keyed by (school_id, course code), as dicts with phrase, reason, and notes.
# A school without a notes file contributes nothing. The import is local because
# check_untagged.py imports normalize() from this module.
def load_untagged_notes() -> dict[tuple[str, str], list[dict]]:
    from check_untagged import load_notes
    out = {}
    for sid in all_school_ids():
        for n in load_notes(sid).to_dict("records"):
            out.setdefault((sid, n.pop("match_key")), []).append(n)
    return out


# Script entry point: match every concept's synonyms against every in-scope row's title
# and description, check the vocabulary, and write the JSON for the review page.
def main() -> None:
    concepts = pd.read_csv(CONCEPTS_CSV, dtype=str, keep_default_na=False)
    courses = pd.read_csv(ALL_COURSES_CSV, dtype=str, keep_default_na=False)
    rows = concept_scope_rows(courses)

    # Each row's searchable text: title and description, normalized. Matching the title
    # too mirrors the tagging rule that a title is evidence for a concept it names.
    texts = {
        (r.school_id, r.course_code): normalize(r.title) + " | " + normalize(r.description)
        for r in rows.itertuples()
    }
    first_seen_ok = {f"{r.institution} / {r.course_code}" for r in rows.itertuples()}

    problems = []
    dupes = concepts["concept_id"][concepts["concept_id"].duplicated()].tolist()
    if dupes:
        problems.append(f"duplicate concept_id: {', '.join(dupes)}")

    out_concepts = []
    for c in concepts.itertuples():
        synonyms = split_synonyms(c.synonyms)
        patterns = [(s, phrase_pattern(s)) for s in synonyms]
        hits = []
        for (sid, code), text in texts.items():
            # Every synonym found in this row, in the order listed in concepts.csv.
            found = [s for s, p in patterns if p.search(text)]
            if found:
                hits.append({"school_id": sid, "course_code": code, "phrases": found})
        used = {s for h in hits for s in h["phrases"]}
        problems += [f"{c.concept_id}: synonym '{s}' occurs in no in-scope row" for s in synonyms if s not in used]
        if c.first_seen not in first_seen_ok:
            problems.append(f"{c.concept_id}: first_seen '{c.first_seen}' is not an in-scope row")
        out_concepts.append({
            "concept_id": c.concept_id,
            "name": c.name,
            "group": c.group,
            "definition": c.definition,
            "synonyms": synonyms,
            "first_seen": c.first_seen,
            "notes": c.notes,
            "matches": hits,
        })

    if problems:
        raise SystemExit("Vocabulary problems; nothing written:\n  " + "\n  ".join(problems))

    tags = load_tags()
    notes = load_untagged_notes()
    out_rows = [
        {
            "school_id": r.school_id,
            "institution": r.institution,
            "course_code": r.course_code,
            "title": r.title,
            "norm_semester": r.norm_semester,
            # The row's approved canonical courses ("; "-separated in the table), so the
            # page can say which kinds of course a concept appears in.
            "canonical_ids": [c for c in r.canonical_ids.split("; ") if c],
            "description": r.description,
            "notes": r.notes,
            # .get with a default: rows of schools not yet tagged get an empty list.
            "tags": tags.get((r.school_id, r.course_code), []),
            # Description text judged not to be a concept, with the reason
            # (data/reference/<id>/untagged_notes.csv, checked by check_untagged.py).
            "untagged_notes": notes.get((r.school_id, r.course_code), []),
        }
        for r in rows.itertuples()
    ]
    OUT_JSON.write_text(json.dumps({"concepts": out_concepts, "rows": out_rows}, indent=1), encoding="utf-8")
    print(f"Wrote {rel(OUT_JSON)}: {len(out_concepts)} concepts, {len(out_rows)} in-scope rows.")


if __name__ == "__main__":  # run main() only when executed as a script, not on import
    main()
