"""Turn a school's plan of study into a 4-year, 8-semester equivalent.

Shared step (any school). Written first for UC's 5-year co-op plan. Reads
data/processed/<id>/plan_parsed.csv (written by the school's parse_<id>.py) and writes
data/processed/<id>/plan_4year.csv, applying the normalization rule in
specs/03-processing.md:

1. List all of the school's terms in chronological order, each marked academic or coop.
2. Drop the co-op terms. Co-op courses stay in the table, flagged is_coop = true, with
   no normalized placement.
3. Number the remaining academic terms 1..k in order, including academic summer terms:
   academic term k -> normalized semester k.
4. normalized year = ceil(k / 2); odd semesters are Fall, even are Spring.
5. If there aren't exactly 8 academic terms, stop instead of forcing a fit.
6. Half-terms (Northeastern's "Summer 1" / "Summer 2", added in step 13): each academic
   half-term is half a semester. They are paired in chronological order, and a pair
   becomes one semester in the place of its first half. An unpaired half-term stops
   the script.

The original placement columns are kept next to the new ones, so every row's move from
the 5-year plan to the 4-year plan can be audited. For a 4-year school without co-op,
the rule just numbers its 8 terms 1-8 and checks there are exactly 8.

Usage:
    python src/normalize.py --school uc
"""

import math

import pandas as pd

from common import PARSED_COLUMNS, rel, require, school_from_args

EXPECTED_SEMESTERS = 8  # a standard 4-year program; the rule requires exactly this many

# Order of terms within one year of a plan. A plan year starts in the fall, so Fall,
# then Spring, then Summer, and (plan year, this rank) sorts terms chronologically.
# Sorting by plan year rather than calendar year works for every school: many sample
# plans say only "Year 2, Spring", with no calendar year. (Parsers must number plan
# years this way: a summer belongs to the plan year that began the previous fall.)
TERM_ORDER = {"Fall": 0, "Autumn": 0, "Spring": 1, "Summer": 2,  # Autumn: Ohio State's name for fall
              "Summer 1": 2, "Summer 2": 3}  # Northeastern's two half-summer terms, in order
# Terms that are half a semester long (rule step 6).
HALF_TERMS = {"Summer 1", "Summer 2"}


# Rule steps 3 and 6: give each academic term its normalized semester. A full term opens
# a new semester. A half-term either opens a new semester and waits for a partner, or,
# if an earlier half-term is waiting, joins that one's semester. Because the pair takes
# its FIRST half's number, the second half's courses move back to that earlier place.
# Co-op terms (not academic) get no semester. For schools without half-terms this is
# exactly "academic term k -> semester k".
def semester_numbers(terms: pd.DataFrame) -> list:
    """Return a normalized semester number (or pd.NA) for each term, in order."""
    numbers, k, waiting = [], 0, None  # waiting: semester number of an unpaired half-term
    for _, t in terms.iterrows():
        if t["orig_term_type"] != "academic":
            numbers.append(pd.NA)
        elif t["orig_term"] not in HALF_TERMS:
            k += 1
            numbers.append(k)
        elif waiting is None:
            k += 1
            numbers.append(k)
            waiting = k
        else:
            numbers.append(waiting)
            waiting = None
    if waiting is not None:
        raise SystemExit(f"Half-term in semester {waiting} has no partner. Review before normalizing.")
    return numbers


# Build the list of distinct terms in chronological order and give each academic term
# its position among academic terms only (steps 1-3 of the rule). Co-op terms get no
# index, so they drop out of the sequence and later academic terms (including summers)
# slide forward to fill the gap.
def term_mapping(df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per term with its academic_term_index and normalized placement."""
    terms = (
        df[["orig_year", "orig_term", "orig_calendar_year", "orig_term_type"]]
        .drop_duplicates()  # one row per term, however many courses it holds
        # assign(...) adds a temporary sort key column; map() looks each term up in TERM_ORDER.
        .assign(_order=lambda t: t["orig_term"].map(TERM_ORDER))
        .sort_values(["orig_year", "_order"])
        .drop(columns="_order")
        .reset_index(drop=True)
    )
    if terms.duplicated(["orig_year", "orig_term"]).any():
        # The same term marked both academic and coop (or given two calendar years)
        # would mean a parsing problem.
        raise SystemExit("A term appears twice with different details; check plan_parsed.csv.")

    academic = terms["orig_term_type"] == "academic"
    # cumsum over the True/False mask counts academic terms seen so far: 1, 2, 3, ...
    # .where(academic) blanks it out (NaN) for co-op terms. Int64 (capital I) is pandas'
    # nullable integer type, so blanks stay blank instead of forcing floats.
    terms["academic_term_index"] = academic.cumsum().where(academic).astype("Int64")
    # Rule step 3 (term k -> semester k), with half-terms paired by step 6.
    terms["norm_semester"] = pd.array(semester_numbers(terms), dtype="Int64")
    # Rule step 4. The lambdas skip blanks (pd.isna) so co-op terms stay unplaced.
    terms["norm_year"] = terms["norm_semester"].map(
        lambda k: pd.NA if pd.isna(k) else math.ceil(k / 2)
    ).astype("Int64")
    terms["norm_term"] = terms["norm_semester"].map(
        lambda k: "" if pd.isna(k) else ("Fall" if k % 2 == 1 else "Spring")
    )
    return terms


# Script entry point: compute the term mapping, check it has 8 semesters, attach it to
# every course row, print the mapping for review, and write the 4-year table.
def main() -> None:
    school, _ = school_from_args(__doc__.splitlines()[0])  # first docstring line as --help text
    in_csv = school.processed / "plan_parsed.csv"
    out_csv = school.processed / "plan_4year.csv"
    require([(in_csv, f"parse_{school.id}.py")])
    # keep_default_na=False keeps empty strings as "" rather than NaN, so blank text
    # columns (course_code for slots, notes) round-trip unchanged.
    df = pd.read_csv(in_csv, keep_default_na=False)
    # Every parser must write the shared column set (common.PARSED_COLUMNS).
    missing = [c for c in PARSED_COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"{rel(in_csv)} is missing columns: {', '.join(missing)}.")

    terms = term_mapping(df)
    n = terms["norm_semester"].max()  # with half-terms paired, this can be less than the term count
    if n != EXPECTED_SEMESTERS:
        # Rule step 5: stop and review rather than forcing a fit.
        raise SystemExit(f"Found {n} academic terms, expected {EXPECTED_SEMESTERS}. Review before normalizing.")

    # Left merge: every course row gets its term's normalized placement; co-op rows get blanks.
    out = df.merge(
        terms.drop(columns="orig_term_type"),
        on=["orig_year", "orig_term", "orig_calendar_year"],
        how="left",
        validate="many_to_one",  # raise if a term somehow matched twice
    )

    # Rule step 2: only the COOP courses themselves lack a placement. A non-co-op row
    # without one would mean a course sits in a co-op term, which the rule doesn't cover.
    unplaced = out[out["norm_semester"].isna() & ~out["is_coop"].astype(bool)]
    if not unplaced.empty:
        raise SystemExit("Non-co-op rows in co-op terms:\n" + unplaced[["course_code", "title"]].to_string())

    # Order the table as a 4-year plan: by normalized semester, with co-op rows last
    # (na_position="last"), keeping the school's within-term order (stable mergesort).
    out = out.sort_values("norm_semester", na_position="last", kind="mergesort")

    # Put the new placement columns right after the original ones, for easy auditing.
    cols = list(df.columns)
    at = cols.index("is_coop")
    cols[at:at] = ["academic_term_index", "norm_semester", "norm_year", "norm_term"]  # slice assignment inserts
    out[cols].to_csv(out_csv, index=False)

    # Print the original -> normalized mapping with credits per semester for review.
    credits = out.groupby("norm_semester")[["credits_min", "credits_max"]].sum()
    print(f"{school.short_name + ' term':<29}-> 4-year plan")
    for _, t in terms.iterrows():
        # orig_calendar_year may be blank (sample plans without dates); join skips it.
        orig = " ".join(str(x) for x in [f"Y{t.orig_year}", t.orig_term, t.orig_calendar_year] if x != "")
        orig += f" ({t.orig_term_type})"
        if pd.isna(t.norm_semester):
            print(f"  {orig:<28} -> dropped (co-op)")
        else:
            c = credits.loc[t.norm_semester]
            cr = f"{c.credits_min}" if c.credits_min == c.credits_max else f"{c.credits_min}-{c.credits_max}"
            print(f"  {orig:<28} -> semester {t.norm_semester}: Year {t.norm_year} {t.norm_term} ({cr} cr)")
    print(f"Wrote {len(out)} rows to {rel(out_csv)}")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
