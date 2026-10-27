"""List the description text that no concept tag covers, course by course: the review queue.

Step 17 revision (specs/08-concepts.md, "Untagged text"). A tag's evidence phrases show
which words of a description were turned into concepts. Whatever is left over is either
a concept that was missed, or text that is not a concept (a course label, framing, a
prerequisite...). To make misses visible, every piece of leftover text must be accounted
for: tagged, or listed with a reason in data/reference/<id>/untagged_notes.csv.

How leftover text is found, for one course's description:
1. Mark every occurrence of every evidence phrase of the course's description tags, and
   of every phrase in its untagged notes (case-insensitive, whitespace-flexible, whole
   words only).
2. Cut the unmarked text at punctuation (. , ; : parentheses, line breaks) into
   fragments.
3. Trim filler words (FILLER: articles, prepositions, catalog verbs like "introduces")
   from both ends of each fragment, and drop fragments with no word left that is not
   filler. What remains is the queue.

Like check_concepts.py, this script only reads. It fails if a note is malformed (unknown
course, phrase not in the description, unknown reason, duplicate); leftover fragments
are printed but don't fail the run, because the queue is work to do, not an error.
`--strict` also fails while any fragment is left.

Reads:
- data/reference/<id>/concept_tags.csv
- data/reference/<id>/untagged_notes.csv (optional; a school without one has no notes)
- data/processed/all_required_courses.csv (from build_combined.py)

Usage:
    python src/check_untagged.py              # every school
    python src/check_untagged.py --school neu # one school
    python src/check_untagged.py --strict     # also fail while fragments are left
"""

import argparse
import re

import pandas as pd

from common import ALL_COURSES_CSV, all_school_ids, concept_scope_rows, load_school, rel, require, split_evidence
from preview_concepts import normalize

NOTE_COLUMNS = ["match_key", "phrase", "reason", "notes"]

# Why a piece of description text is not tagged. Each reason is a rule from
# specs/08-concepts.md ("Granularity", "Scope"), so a note can be judged against it.
REASONS = {
    "course-label": "names the whole course or a canonical course (\"data structures\", \"algorithms\")",
    "framing": "about the course itself: audience, format, companion labs, aims, outcomes",
    "generic-aim": "an aim with no topic (\"problem solving\", \"critical thinking\")",
    "prerequisite": "what students must already know",
    "too-general": "names an area too broadly to pick one concept (\"methods\", \"structures\")",
    "no-concept": "a concrete topic the vocabulary lacks; a candidate for a new concept",
}

# Words that carry no topic on their own: articles, prepositions, conjunctions, and the
# verbs and nouns catalogs use to frame a list of topics. Trimmed from the ends of a
# fragment; a fragment made only of these is dropped. Kept short on purpose: a word
# that could name a topic ("design", "analysis", "data") is never filler.
FILLER = set("""
a an the and or nor but of in on to for with without by as at from into onto via per
its it is are be been being this that these those such than then so who whom which what
how why when where whose their they them there here both either each all any some other
also too very well more most much many few its own same new
including include includes included e.g i.e etc
introduces introduce introduced introduction introductory covers cover covered covering
course courses class classes student students topic topics concept concepts principle principles
basic basics fundamental fundamentals emphasis emphasizes study studies studied discuss discusses
discussed discussion examine examines considers consider consideration describes describe
presents present reviews review provides provide offers offer explores explore illustrates
continues continue builds build concludes conclude seeks seek will may can must should
use uses using used learn learns learning understand understanding gain gains area areas
skill skills needed opportunity opportunities show shows subject subjects several exposes expose focus focuses effective simple
application applications example examples through
""".split())


# Return the [start, end) spans where `phrase` occurs in `text` as whole words: case is
# ignored, any whitespace run in the phrase matches any run in the text, and the
# lookarounds (?<![a-z0-9]) / (?![a-z0-9]) keep "sets" from matching inside "subsets".
# The same rule as the review page's highlighting, so what is marked there is what this
# script treats as covered.
def phrase_spans(text: str, phrase: str) -> list[tuple[int, int]]:
    words = phrase.lower().split()
    if not words:
        return []
    pattern = r"(?<![a-z0-9])" + r"\s+".join(re.escape(w) for w in words) + r"(?![a-z0-9])"
    return [(m.start(), m.end()) for m in re.finditer(pattern, text.lower())]


# Return the leftover fragments of `text` once every phrase in `phrases` is marked as
# covered (steps 1-3 in the module docstring). Fragments keep the source's wording and
# case, with filler trimmed from both ends.
def untagged_fragments(text: str, phrases: list[str]) -> list[str]:
    covered = [False] * len(text)
    for phrase in phrases:
        for s, e in phrase_spans(text, phrase):
            covered[s:e] = [True] * (e - s)
    # Replace covered characters with NUL so one split cuts at both covered spans and
    # punctuation. NUL never occurs in catalog text.
    masked = "".join("\0" if c else ch for ch, c in zip(text, covered))
    out = []
    for piece in re.split(r"[\0.,;:()\[\]\n!?]+", masked):
        # Words, keeping characters that belong to topic names (C++, C#, A*, I/O, don't).
        words = re.findall(r"[A-Za-z0-9+#*/'’-]+", piece)
        while words and words[0].lower() in FILLER:
            words.pop(0)
        while words and words[-1].lower() in FILLER:
            words.pop()
        # Keep the fragment only if some word is neither filler nor a lone number or
        # letter (list markers like "2." or "a." in UC's numbered descriptions).
        if any(w.lower() not in FILLER and len(w) > 1 and not w.isdigit() for w in words):
            out.append(" ".join(words))
    return out


# Return a school's untagged notes as a DataFrame with NOTE_COLUMNS (empty if the
# school has no notes file yet).
def load_notes(school_id: str) -> pd.DataFrame:
    path = load_school(school_id).reference / "untagged_notes.csv"
    if not path.exists():
        return pd.DataFrame(columns=NOTE_COLUMNS)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


# Return the phrases that count as covered in one course's description: every evidence
# phrase of its description tags (rejected tags included: a rejected tag means the
# phrase was looked at and judged, so it is not a miss) plus every note phrase.
def covered_phrases(key: str, tags: pd.DataFrame, notes: pd.DataFrame) -> list[str]:
    mine = tags[(tags["match_key"] == key) & (tags["evidence_field"] == "description")]
    phrases = [ph for cell in mine["evidence"] for ph in split_evidence(cell)]
    return phrases + notes.loc[notes["match_key"] == key, "phrase"].tolist()


# Check one school's notes file. `rows` is the school's in-scope rows indexed by course
# code. Returns failure messages prefixed with the school id.
def check_notes(school_id: str, notes: pd.DataFrame, rows: pd.DataFrame) -> list[str]:
    p = f"{school_id}:"
    missing = [c for c in NOTE_COLUMNS if c not in notes.columns]
    if missing:
        return [f"{p} untagged_notes.csv is missing columns {missing}"]
    failures = []
    for i, n in notes.iterrows():
        where = f"{p} untagged_notes line {i + 2} ({n['match_key']}, \"{n['phrase']}\")"
        if n["match_key"] not in rows.index:
            failures.append(f"{where}: match_key is not an in-scope row")
            continue
        if n["reason"] not in REASONS:
            failures.append(f"{where}: reason '{n['reason']}' not in {sorted(REASONS)}")
        if not phrase_spans(rows.at[n["match_key"], "description"], n["phrase"]):
            failures.append(f"{where}: phrase not found (as whole words) in the description")
    # A normalized copy of the phrase, so case or spacing differences still count as repeats.
    keyed = notes.assign(_p=notes["phrase"].map(normalize))
    for key, ph in sorted(set(keyed.loc[keyed.duplicated(["match_key", "_p"], keep=False), ["match_key", "_p"]]
                              .itertuples(index=False, name=None))):
        failures.append(f"{p} duplicate note for ({key}, \"{ph}\")")
    return failures


# Script entry point: check the notes, then print each course's leftover fragments.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--school", help="one school id (default: every school)")
    parser.add_argument("--strict", action="store_true", help="fail while any fragment is left")
    args = parser.parse_args()
    school_ids = [load_school(args.school).id] if args.school else all_school_ids()

    require([(ALL_COURSES_CSV, "build_combined.py")]
            + [(load_school(s).reference / "concept_tags.csv", "the reference file") for s in school_ids])
    scope = concept_scope_rows(pd.read_csv(ALL_COURSES_CSV, dtype=str, keep_default_na=False))

    failures, n_left, n_notes = [], 0, 0
    for sid in school_ids:
        tags = pd.read_csv(load_school(sid).reference / "concept_tags.csv", dtype=str, keep_default_na=False)
        notes = load_notes(sid)
        rows = scope[scope["school_id"] == sid].set_index("course_code")
        failures += check_notes(sid, notes, rows)
        n_notes += len(notes)
        print(f"\n=== {sid}: {rel(load_school(sid).reference / 'untagged_notes.csv')}")
        for key, r in rows.iterrows():
            left = untagged_fragments(r["description"], covered_phrases(key, tags, notes))
            n_left += len(left)
            if left:
                print(f"{key}  {r['title']}")
                for frag in left:
                    print(f"    - {frag}")

    print(f"\n{len(school_ids)} school(s), {n_notes} notes, {n_left} untagged fragments left.")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    if args.strict and n_left:
        raise SystemExit(f"{n_left} untagged fragments left (--strict).")
    print("Untagged-notes checks passed.")


if __name__ == "__main__":  # run main() only when executed as a script, not on import
    main()
