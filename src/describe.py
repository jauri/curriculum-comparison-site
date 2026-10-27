"""Attach a description to every row of a school's 4-year plan.

Shared step (any school). Reads data/processed/<id>/plan_4year.csv (written by
normalize.py) and writes data/processed/<id>/plan_described.csv, following step 3 of
specs/03-processing.md:

- Named courses get the school's official catalog text from
  data/processed/<id>/official_descriptions.csv, written by the school's own
  parse_<id>_descriptions.py. description_source = official.
- Requirement slots (science choice, gen-ed, electives) get a hand-written generic
  description from data/reference/<id>/generic_descriptions.csv, keyed by slot title.
  description_source = generic. That file is hand-reviewed reference data, so this
  script only reads it.
- A named course with no official text may also get a generic description, keyed by
  its course code in the same file, when the school publishes none (added in step 13
  for Michigan). It is labeled generic; a course with official text always uses it.

The script stops with an error if any row ends up without a description, if an official
row has no source URL, or if a generic description in the reference file goes unused.

Usage:
    python src/describe.py --school uc
"""

import pandas as pd

from common import OFFICIAL_COLUMNS, require, rel, school_from_args


# Script entry point: describe every row, run the checks, and write the CSV.
def main() -> None:
    school, _ = school_from_args(__doc__.splitlines()[0])  # first docstring line as --help text
    in_csv = school.processed / "plan_4year.csv"
    official_csv = school.processed / "official_descriptions.csv"
    generic_csv = school.reference / "generic_descriptions.csv"
    out_csv = school.processed / "plan_described.csv"
    require([(in_csv, "normalize.py"), (official_csv, f"parse_{school.id}_descriptions.py"),
             (generic_csv, "the reference file")])

    # keep_default_na=False keeps blank cells as "" instead of NaN; dtype=str on the
    # 4-year table would also work, but numbers (credits, semesters) should stay numeric.
    df = pd.read_csv(in_csv, keep_default_na=False)
    # set_index makes each lookup table addressable by its key: .loc[code] or .loc[title].
    official = pd.read_csv(official_csv, keep_default_na=False, dtype=str).set_index("course_code")
    generic = pd.read_csv(generic_csv, keep_default_na=False).set_index("title")

    descriptions, sources, links, files, prereqs = [], [], [], [], []
    failures = []
    for _, row in df.iterrows():  # iterrows yields (index, row-as-Series) pairs
        has_official = row["course_code"] in official.index and official.loc[row["course_code"], "description"]
        if row["course_code"] and not has_official and row["course_code"] in generic.index:
            # A named course whose school publishes no public official text (Michigan's
            # MATH, PHYS, and CHEM courses are in a login-only course guide; decided with
            # the user in step 13) gets a generic description keyed by its course code,
            # labeled generic like a slot's (step 3.2 of 03-processing.md).
            descriptions.append(generic.loc[row["course_code"], "description"])
            sources.append("generic")
            links.append("")
            files.append(rel(generic_csv))
            prereqs.append("")
        elif row["course_code"]:
            code = row["course_code"]
            # A code without saved catalog text gets empty fields and a check failure.
            o = official.loc[code] if code in official.index else pd.Series("", index=OFFICIAL_COLUMNS[1:])
            descriptions.append(o["description"])
            sources.append("official")
            links.append(o["description_url"])
            files.append(o["description_file"])
            prereqs.append(o["prerequisites"])
            if not o["description"]:
                failures.append(f"No official description found for {code}.")
            elif not o["description_url"]:
                failures.append(f"{code} has official text but no description_url.")
        else:
            # Slots are looked up by their title from the school's parser.
            desc = generic.loc[row["title"], "description"] if row["title"] in generic.index else ""
            descriptions.append(desc)
            sources.append("generic")
            links.append("")
            files.append(rel(generic_csv) if desc else "")
            prereqs.append("")
            if not desc:
                failures.append(f"No generic description for slot '{row['title']}' in {rel(generic_csv)}.")

    df["description"] = descriptions
    df["description_source"] = sources
    df["description_url"] = links
    df["description_file"] = files
    df["prerequisites"] = prereqs

    # Flag official text that seems cut off in the school's catalog: it ends without
    # sentence punctuation (e.g. UC's CS2028C ends "Sets,"). The flag goes in notes for
    # the user to see.
    cut = (df["description_source"] == "official") & ~df["description"].str.rstrip().str.endswith((".", "?", "!", ")"))
    flag = f"{school.short_name}'s catalog description may be cut off (ends without punctuation)."
    # .where keeps the old note where cond is False; for flagged rows, append the flag.
    df["notes"] = df["notes"].where(~cut, (df["notes"] + " " + flag).str.strip())

    # Every generic description in the reference file should describe some row; an
    # unused one usually means a slot title changed in the school's parser.
    generic_rows = df[df["description_source"] == "generic"]
    # A generic entry is used by a slot's title or by a named course's code.
    unused = sorted(set(generic.index) - set(generic_rows["title"]) - set(generic_rows["course_code"]))
    failures += [f"Generic description for '{t}' is not used by any row." for t in unused]

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_csv, index=False)

    counts = df["description_source"].value_counts()
    print(f"Wrote {len(df)} rows to {rel(out_csv)}: "
          f"{counts.get('official', 0)} official, {counts.get('generic', 0)} generic")
    for _, r in df[cut].iterrows():
        print(f"  Possibly cut off in {school.short_name}'s catalog: {r['course_code']} ({r['title']})")
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 5 checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
