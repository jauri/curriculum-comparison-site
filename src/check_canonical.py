"""Check the canonical course list and one school's matches against it.

Shared step (any school). Step 6 of specs/plan.md seeded two kinds of hand-reviewed
reference files:

- data/reference/canonical_courses.csv: one row per course concept shared across all
  schools (schema in specs/04-outputs.md).
- data/reference/<id>/matches.csv: assigns each of a school's courses or slots a
  canonical_id, with match_confidence, match_rationale, partial_match, and match_status
  (step 4 of specs/03-processing.md). Since step 13 a row may have several lines, one
  per canonical course, each with a match_role: covers, one_of (a real choice), or
  all_of_group (options all required, in any order).

Both files are written and edited by hand, so this script only reads them. It never
writes or "fixes" them, because a silent rewrite could undo a reviewed decision. It reads
data/processed/<id>/plan_described.csv (from describe.py) to make sure every row of the
school's plan is matched, then prints the matches grouped by canonical course for review.

A row's match key is its course code, or its title for slots (which have no code).
Slots that share a title (e.g. UC's two "Directed Elective" rows) are the same
requirement in different semesters, so one match row covers them all.

Two checks look at every school's match file, not just this one's, because they are
about the shared list: no canonical course is unused, and each canonical course was
created by exactly one match marked "new" (the school and course in its first_seen).

Usage:
    python src/check_canonical.py --school uc
"""

import re

import pandas as pd

from common import CANON_CSV, all_school_ids, load_school, rel, require, school_from_args

# Allowed values, from specs/04-outputs.md.
KINDS = {"course", "slot"}
CONFIDENCES = {"high", "medium", "low", "new"}
STATUSES = {"proposed", "approved", "rejected"}
# Match roles (specs/03-processing.md, step 4; added in step 13).
ROLES = {"covers", "one_of", "all_of_group"}
# The role a choice row's matches must have, by its choice_kind. A "choose" row may use
# covers (every option is the same concept) or one_of (options are different concepts).
ROLES_FOR_CHOICE = {"": {"covers"}, "choose": {"covers", "one_of"}, "all_in_any_order": {"all_of_group"}}
# Plan rows of these types are requirement slots and must match a canonical "slot".
SLOT_TYPES = {"elective_slot", "gen_ed"}
# Slot concepts that a named required course may also match. lab-science's own note says
# a program that requires one specific science (e.g. OSU's PHYSICS 1250) still maps to
# it, so the science requirement compares across schools. Decided with the user in step 10.
COURSE_MAY_FILL_SLOT = {"lab-science"}
# The reverse: course concepts that a slot row may match. Michigan's "Approved CS
# Capstone course" is a required capstone chosen from a list the saved schedule doesn't
# include, so it can't list options, but it is still the program's capstone and should
# line up with other schools' capstone courses. Added in step 13 (for the user's review).
# Step 13 batch 3 adds first-year-seminar (for the user's review): Penn State's plan
# has a "First-Year Seminar" slot (1 credit chosen per the college's engagement plan),
# a required first-year seminar like other schools' named seminar courses.
SLOT_MAY_FILL_COURSE = {"capstone-design", "first-year-seminar"}
# Readable slug: lowercase words and digits joined by single hyphens (e.g. "calculus-1").
SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


# The key that links a plan row to its match: course code if it has one, else the
# slot title. Kept in one function so the plan side and the error messages agree.
def match_key(row: pd.Series) -> str:
    """Return a plan row's match key (course code, or title for slots)."""
    return row["course_code"] or row["title"]


# Checks on the canonical list by itself: IDs and names unique, slugs well formed,
# required fields filled in, kind valid. Returns a list of failure messages.
def check_canonical(canon: pd.DataFrame) -> list[str]:
    """Return failure messages for problems within canonical_courses.csv."""
    failures = []
    for col in ["canonical_id", "name"]:
        # duplicated(keep=False) marks every copy of a repeated value, not just the later ones.
        dups = sorted(set(canon.loc[canon[col].duplicated(keep=False), col]))
        failures += [f"Duplicate {col} in canonical list: {d}" for d in dups]
    for _, r in canon.iterrows():
        cid = r["canonical_id"]
        if not SLUG.match(cid):
            failures.append(f"canonical_id '{cid}' is not a lowercase hyphenated slug.")
        if r["kind"] not in KINDS:
            failures.append(f"{cid}: kind '{r['kind']}' is not one of {sorted(KINDS)}.")
        for col in ["name", "description", "typical_credits", "first_seen"]:
            if not r[col].strip():
                failures.append(f"{cid}: {col} is empty.")
    return failures


# Checks on the match file by itself and against the canonical list: each (key,
# canonical course) pair listed once, one role per key, valid enumerated values, a
# rationale on every line, and an existing canonical_id.
def check_matches(matches: pd.DataFrame, canon_ids: set[str]) -> list[str]:
    """Return failure messages for problems within one school's matches.csv."""
    failures = []
    pair = ["match_key", "canonical_id"]
    dups = matches.loc[matches.duplicated(pair, keep=False), pair].drop_duplicates()
    failures += [f"{k} -> {c} listed more than once in matches.csv." for k, c in dups.itertuples(index=False)]
    # A row's lines all share one role: a row is either a course (covers), a real choice
    # (one_of), or a timing group (all_of_group); mixing them would be ambiguous.
    roles = matches.groupby("match_key")["match_role"].nunique()
    failures += [f"{k}: its lines mix match roles." for k in roles[roles > 1].index]
    one_of = matches[matches["match_role"] == "one_of"].groupby("match_key").size()
    failures += [f"{k}: a one_of choice needs at least two concepts." for k in one_of[one_of < 2].index]
    for _, m in matches.iterrows():
        key = m["match_key"]
        if m["match_role"] not in ROLES:
            failures.append(f"{key}: match_role '{m['match_role']}' is not one of {sorted(ROLES)}.")
        if m["canonical_id"] not in canon_ids:
            failures.append(f"{key}: canonical_id '{m['canonical_id']}' is not in the canonical list.")
        if m["match_confidence"] not in CONFIDENCES:
            failures.append(f"{key}: match_confidence '{m['match_confidence']}' is not one of {sorted(CONFIDENCES)}.")
        if m["match_status"] not in STATUSES:
            failures.append(f"{key}: match_status '{m['match_status']}' is not one of {sorted(STATUSES)}.")
        if m["partial_match"] not in {"true", "false"}:
            failures.append(f"{key}: partial_match must be 'true' or 'false'.")
        if not m["match_rationale"].strip():
            failures.append(f"{key}: match_rationale is empty.")
    return failures


# Checks that link one school's plan to its match file: every plan row is matched,
# every match is used, and slots match slots and courses match courses.
def check_links(plan: pd.DataFrame, canon: pd.DataFrame, matches: pd.DataFrame) -> list[str]:
    """Return failure messages for problems between a school's plan, matches, and the list."""
    failures = []
    plan_keys = set(plan["key"])
    match_keys = set(matches["match_key"])
    failures += [f"Plan row '{k}' has no match in matches.csv." for k in sorted(plan_keys - match_keys)]
    failures += [f"Match '{k}' does not correspond to any plan row." for k in sorted(match_keys - plan_keys)]

    # A slot must map to a slot concept and a course to a course concept; mixing them
    # would make slot-vs-course comparisons across schools meaningless. Exception: a
    # choice row (one with `options`, e.g. UIC's "CS 111 or CS 112 or CS 113", three
    # versions of Program Design I) may map to a course concept when every option is
    # that course (decided in step 10), and, since step 13, to each option's course
    # concept (one_of or all_of_group).
    kind_of = dict(zip(canon["canonical_id"], canon["kind"]))  # zip pairs the two columns row by row
    merged = plan.merge(matches, left_on="key", right_on="match_key", how="inner")
    # The role must suit the row's choice_kind (ROLES_FOR_CHOICE): a timing group's rows
    # must be all_of_group, and only choice rows may be one_of.
    for _, r in merged.drop_duplicates("key").iterrows():
        allowed = ROLES_FOR_CHOICE.get(r["choice_kind"], set())
        if r["match_role"] not in allowed:
            failures.append(f"{r['key']} (choice_kind '{r['choice_kind'] or 'none'}') has match_role "
                            f"'{r['match_role']}'; expected one of {sorted(allowed)}.")
    for _, r in merged.drop_duplicates(["key", "canonical_id"]).iterrows():
        want = "slot" if r["requirement_type"] in SLOT_TYPES else "course"
        have = kind_of.get(r["canonical_id"])  # None if the id is missing (reported by check_matches)
        if r.get("options", "") and have == "course":
            continue  # a choice row mapped to its options' course concept(s)
        if want == "course" and r["canonical_id"] in COURSE_MAY_FILL_SLOT:
            continue  # a required course that fills a slot requirement (see COURSE_MAY_FILL_SLOT)
        if want == "slot" and r["canonical_id"] in SLOT_MAY_FILL_COURSE:
            continue  # a slot that is a required course chosen from a list (see SLOT_MAY_FILL_COURSE)
        if have and have != want:
            failures.append(f"{r['key']} is a {want} row but maps to {r['canonical_id']} (kind {have}).")
    return failures


# Read every school's match file that exists so far, tagged with the school's
# institution name. Schools listed in schools.csv but not yet matched are skipped.
def load_all_matches() -> pd.DataFrame:
    """Return all schools' matches.csv rows with an added `institution` column."""
    frames = []
    for sid in all_school_ids():
        s = load_school(sid)
        path = s.reference / "matches.csv"
        if path.exists():
            # assign adds a constant column, so each row remembers which school it came from.
            frames.append(pd.read_csv(path, keep_default_na=False, dtype=str).assign(institution=s.institution))
    return pd.concat(frames, ignore_index=True)  # stack them into one table


# Checks on the shared list against every school's matches. specs/03-processing.md: no
# canonical course is unused. And each canonical course was created by exactly one
# match marked "new" (UC seeded the list; later schools add to it), and first_seen
# names that same school and course or slot, as "Institution / match key".
def check_shared(canon: pd.DataFrame, all_matches: pd.DataFrame) -> list[str]:
    """Return failure messages for unused canonical courses and wrong first_seen values."""
    failures = []
    used = set(all_matches["canonical_id"])
    failures += [f"Canonical course '{c}' is not used by any match." for c in sorted(set(canon["canonical_id"]) - used)]

    new = all_matches[all_matches["match_confidence"] == "new"]
    for _, c in canon.iterrows():
        creators = new[new["canonical_id"] == c["canonical_id"]]
        if len(creators) != 1:
            failures.append(f"{c['canonical_id']}: expected 1 match marked 'new', found {len(creators)}.")
            continue
        expected = f"{creators.iloc[0]['institution']} / {creators.iloc[0]['match_key']}"
        if c["first_seen"] != expected:
            failures.append(f"{c['canonical_id']}: first_seen '{c['first_seen']}' should be '{expected}'.")
    return failures


# Print each canonical course with the school's rows mapped to it, for the user's
# review. Canonical courses this school doesn't use are listed with "(none)", which
# shows at a glance what the school lacks compared with the list so far. A row with
# several concepts is listed under each. Its role is shown: "possible" for one_of (the
# student may take a different option), and "group" for all_of_group, whose credits are
# split evenly across the group's concepts so they are never counted twice
# (03-processing.md: Berkeley's 2 rows x 4 units -> 4 units per course).
def print_review(plan: pd.DataFrame, canon: pd.DataFrame, matches: pd.DataFrame) -> None:
    """Print the canonical list with one school's matches and credit totals."""
    merged = plan.merge(matches, left_on="key", right_on="match_key", how="left")
    n_concepts = matches.groupby("match_key").size()  # concepts per key, for the group split
    for _, c in canon.iterrows():
        rows = merged[merged["canonical_id"] == c["canonical_id"]]
        if rows.empty:
            print(f"\n{c['canonical_id']}  ({c['kind']}, {c['name']})  (none)")
            continue
        print(f"\n{c['canonical_id']}  ({c['kind']}, {c['name']})")
        # groupby(sort=False) keeps plan order; one line per key even when a slot repeats.
        for key, g in rows.groupby("key", sort=False):
            m = g.iloc[0]
            sems = ",".join(str(int(s)) for s in g["norm_semester"] if s != "")  # co-op rows have no semester
            lo, hi = g["credits_min"].sum(), g["credits_max"].sum()
            if m["match_role"] == "all_of_group":
                lo, hi = lo / n_concepts[key], hi / n_concepts[key]
            # :g drops a trailing ".0" (4.0 -> 4) but keeps a real fraction (1.5).
            cr = f"{lo:g}" if lo == hi else f"{lo:g}-{hi:g}"
            partial = " partial" if m["partial_match"] == "true" else ""
            role = {"one_of": " possible", "all_of_group": " group"}.get(m["match_role"], "")
            print(f"  {key:<52} sem {sems or '-':<5} {cr:>5} cr  {m['match_confidence']}{partial}{role}")


# Script entry point: load the three files, run every check, print the review listing.
def main() -> None:
    school, _ = school_from_args(__doc__.splitlines()[0])  # first docstring line as --help text
    plan_csv = school.processed / "plan_described.csv"
    match_csv = school.reference / "matches.csv"
    require([(plan_csv, "describe.py"), (CANON_CSV, "the reference file"),
             (match_csv, "the reference file")])
    # keep_default_na=False keeps blank cells as "" instead of NaN (no NaN checks needed).
    plan = pd.read_csv(plan_csv, keep_default_na=False)
    # dtype=str on the reference files: every value there is text, including "true"/"false".
    canon = pd.read_csv(CANON_CSV, keep_default_na=False, dtype=str)
    matches = pd.read_csv(match_csv, keep_default_na=False, dtype=str)
    plan["key"] = plan.apply(match_key, axis=1)  # axis=1: call match_key once per row

    print(f"{school.institution}: {rel(match_csv)}")
    failures = check_canonical(canon)
    failures += check_matches(matches, set(canon["canonical_id"]))
    failures += check_links(plan, canon, matches)
    failures += check_shared(canon, load_all_matches())

    print_review(plan, canon, matches)
    counts = matches["match_confidence"].value_counts()
    print(f"\n{len(canon)} canonical courses ({(canon['kind'] == 'slot').sum()} slots); "
          f"{len(matches)} match lines for {matches['match_key'].nunique()} keys covering {len(plan)} plan rows; confidence: "
          + ", ".join(f"{k} {counts.get(k, 0)}" for k in ["new", "high", "medium", "low"]))
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 6 checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
