"""Read Stony Brook's official course descriptions from the saved catalog course entries.

Stony Brook's school-specific description parser (batch 4). Reads every course entry
saved through Chrome by collect_sbu.py (data/raw/sbu/courses/<date>_<CODE>.html) and
writes data/processed/sbu/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).
The shared Acalog layout is read by acalog.py; this script only says how Stony Brook's
entry text is laid out:

    ... Includes required laboratory. 4 credits Prerequisite(s): Level 5 or higher on the
    math placement exam Advisory Preq: CSE 101, CSE 103 or ISE 108 SBC: TECH

The description runs up to the credits ("4 credits", sometimes "3 credits,"), then come
labeled parts. The credits phrase has no label of its own, so it is first replaced by
one ("Credits:") and the shared splitter does the rest. "Prerequisite(s):",
"Corequisite(s):", and "Advisory Preq:" become `prerequisites`.

Usage:
    python src/parse_sbu_descriptions.py
"""

import re

from acalog import description_rows, split_body, write_descriptions
from common import load_school

SCHOOL = load_school("sbu")
# Labels that end the description, as Stony Brook's entries write them.
LABELS = ["Credits:", "Prerequisite(s):", "Corequisite(s):", "Advisory Preq:", "Advisory Prerequisite(s):",
          "Anti-requisite:", "DEC:", "SBC:", "Partially fulfills:", "Offered:", "Repeatable:"]
REQS = ["Prerequisite(s):", "Corequisite(s):", "Advisory Preq:", "Advisory Prerequisite(s):"]
# The credits phrase: " 4 credits" or " 0-3 credits," before the labeled parts.
CREDITS = re.compile(r"\s\d+(?:-\d+)? credits?,?(?=\s|$)")


# Split one entry body: label the credits phrase, then use the shared splitter.
def split(body: str) -> tuple[str, str]:
    """Return (description, prerequisites) for one Stony Brook entry body."""
    labeled = CREDITS.sub(" Credits:", body, count=1)  # count=1: only the first (the entry's own credits)
    return split_body(labeled, lead=r"^(?!)", labels=LABELS, req_labels=REQS)  # (?!) never matches: no lead


# Entry point: split every saved entry and write the table.
def main() -> None:
    rows, empty = description_rows(SCHOOL, split)
    write_descriptions(SCHOOL, rows, empty)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
