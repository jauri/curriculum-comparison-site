"""Write the course categories (canonical courses grouped into major categories) for the web views.

Specs/12-category-view.md. The category view draws one band per category and one
sub-band per canonical course inside it, so it needs to know which canonical courses
belong to which category, and in what order the categories go.

Reads:
- data/reference/course_categories.csv: one line per category (id, name, display
  order, description), hand-reviewed with the user.
- data/reference/category_members.csv: one line per canonical course placed in a
  category (canonical_id, category_id), hand-reviewed with the user.
- data/reference/canonical_courses.csv: to check that every member is a real canonical
  course.
- data/processed/all_required_courses.csv (from build_combined.py): to report which
  computing-area canonical courses some school requires but no category holds.

Writes:
- data/processed/course_categories.json: the categories in display order, each with its
  member canonical ids in the order listed in category_members.csv.

Nothing is judged here: the grouping is copied from the two reference files. The script
stops if a member names an unknown canonical course or category, or if a canonical
course is placed in two categories, since the view would draw it twice.

Usage:
    python src/build_categories.py
"""

import json

import pandas as pd

from common import ALL_COURSES_CSV, CANON_CSV, ROOT, rel

REFERENCE = ROOT / "data" / "reference"
CATEGORIES_CSV = REFERENCE / "course_categories.csv"
MEMBERS_CSV = REFERENCE / "category_members.csv"
OUT_JSON = ROOT / "data" / "processed" / "course_categories.json"


# Check the two reference files against each other and the canonical list. Returns a
# list of problems (empty when everything joins), so all of them print at once instead
# of one per run.
def problems(categories: pd.DataFrame, members: pd.DataFrame, canon_ids: set[str]) -> list[str]:
    found = []
    for cid in sorted(set(members["canonical_id"]) - canon_ids):
        found.append(f"{cid}: not in {rel(CANON_CSV)}")
    for cat in sorted(set(members["category_id"]) - set(categories["category_id"])):
        found.append(f"category {cat}: not in {rel(CATEGORIES_CSV)}")
    # duplicated(keep=False) marks every copy of a repeated id, not just the second one.
    dupes = members.loc[members["canonical_id"].duplicated(keep=False), "canonical_id"]
    for cid in sorted(set(dupes)):
        found.append(f"{cid}: placed in more than one category")
    if categories["category_id"].duplicated().any():
        found.append(f"{rel(CATEGORIES_CSV)}: a category id is listed twice")
    return found


# Computing-area canonical courses that some school requires but no category holds,
# for the report printed at the end. "Computing area" is the most common subject_area of
# the rows matched to the course, the same rule the timeline view uses in the browser.
def uncategorized_computing(members: pd.DataFrame) -> list[str]:
    rows = pd.read_csv(ALL_COURSES_CSV, dtype=str, keep_default_na=False)
    rows = rows[rows["canonical_ids"] != ""]
    # A row may match several canonical courses, written "a; b". str.split makes a list
    # per row; explode turns each list item into its own line, copying the row's other
    # columns, so every (row, canonical course) pair is one line.
    pairs = rows.assign(cid=rows["canonical_ids"].str.split(";")).explode("cid")
    pairs["cid"] = pairs["cid"].str.strip()
    # mode() returns the most common values (sorted); iloc[0] takes the first on a tie.
    area = pairs.groupby("cid")["subject_area"].agg(lambda s: s.mode().iloc[0])
    placed = set(members["canonical_id"])
    return sorted(cid for cid, a in area.items() if a == "cs" and cid not in placed)


# Script entry point: check the reference files, then write the JSON for the view.
def main() -> None:
    categories = pd.read_csv(CATEGORIES_CSV, dtype=str, keep_default_na=False)
    members = pd.read_csv(MEMBERS_CSV, dtype=str, keep_default_na=False)
    canon_ids = set(pd.read_csv(CANON_CSV, dtype=str, keep_default_na=False)["canonical_id"])

    found = problems(categories, members, canon_ids)
    if found:
        raise SystemExit("Category files don't join:\n  " + "\n  ".join(found))

    # Sort categories by their display order (as numbers, not strings, so 10 follows 9).
    categories = categories.assign(order=categories["order"].astype(int)).sort_values("order")
    out = [
        {
            "category_id": c.category_id,
            "name": c.name,
            "description": c.description,
            # Members in the order listed in category_members.csv (boolean filtering
            # keeps the file's row order).
            "canonical_ids": members.loc[members["category_id"] == c.category_id, "canonical_id"].tolist(),
        }
        for c in categories.itertuples()  # itertuples: one named tuple per row, fields by column name
    ]
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
        f.write("\n")

    n = sum(len(c["canonical_ids"]) for c in out)
    print(f"Wrote {rel(OUT_JSON)}: {len(out)} categories, {n} canonical courses.")
    left = uncategorized_computing(members)
    if left:
        print("Computing-area canonical courses in no category (not drawn): " + ", ".join(left))


if __name__ == "__main__":  # run main() only when executed as a script, not when imported
    main()
