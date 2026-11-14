"""Read UVA's official course descriptions from the saved Undergraduate Record entries.

UVA's school-specific description parser (batch 4). Reads every course entry saved
through Chrome by collect_uva.py (data/raw/uva/courses/<date>_<CODE>.html) and writes
data/processed/uva/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS). The
shared Acalog layout is read by acalog.py; this script only says how UVA's entry text is
laid out:

    Effective Date 08/01/2025 A second course in computing ... Prereq: CS 1110 or ...
    Requisites Must have completed CS 1110 ... with a grade of C- or better ... Credits: 4

An "Effective Date" leads the text and is dropped; the description runs to the first
requisite label ("Prereq:", "Prerequisite:", "Pre-requisite:", "Co-requisite:", ...),
and everything from there to "Credits:" becomes `prerequisites`, including UVA's
"Requisites" block (no colon), which restates the enforced rule.

Usage:
    python src/parse_uva_descriptions.py
"""

from functools import partial

from acalog import description_rows, split_body, write_descriptions
from common import load_school

SCHOOL = load_school("uva")
# Labels that end the description, as UVA's entries write them.
# "Requisites " (no colon) opens UVA's block restating the enforced rule, and some entries
# write "Prereq " without a colon; both start requisite text. Matching is case-sensitive,
# so "Requisites" never matches inside "Co-requisites".
REQS = ["Prerequisites:", "Prerequisite:", "Pre-requisite:", "Prereq:", "Co-requisites:", "Co-requisite:",
        "Corequisite:", "Requisites ", "Prereq "]
LABELS = REQS + ["Credits:", "Note:"]


# Entry point: split every saved entry and write the table.
def main() -> None:
    # partial() fixes UVA's arguments, leaving a function of the body alone.
    split = partial(split_body, lead=r"^Effective Date \d{2}/\d{2}/\d{4}", labels=LABELS, req_labels=REQS)
    rows, empty = description_rows(SCHOOL, split)
    write_descriptions(SCHOOL, rows, empty)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
