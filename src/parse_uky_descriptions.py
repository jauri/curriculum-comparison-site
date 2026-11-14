"""Read Kentucky's official course descriptions from the saved catalog course entries.

Kentucky's school-specific description parser (batch 4). Reads every course entry saved
through Chrome by collect_uky.py (data/raw/uky/courses/<date>_<CODE>.html) and writes
data/processed/uky/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS). The
shared Acalog layout is read by acalog.py; this script only says how Kentucky's entry
text is laid out:

    [ 4 Credit Hours] The course covers introductory object-oriented problem solving ...
    Prereq: EGR 102 or CS 115 or equivalent. Course Attributes: ...

The bracketed credit hours lead the text, the description follows, and labeled parts
come after. "Prereq:" and "Prereq or concur:" become `prerequisites`.

Usage:
    python src/parse_uky_descriptions.py
"""

from functools import partial

from acalog import description_rows, split_body, write_descriptions
from common import load_school

SCHOOL = load_school("uky")
# Labels that end the description, as Kentucky's entries write them.
LABELS = ["Prereq or concur:", "Prereq:", "Course Attributes:", "Crosslisted with:"]
REQS = ["Prereq or concur:", "Prereq:"]


# Entry point: split every saved entry and write the table.
def main() -> None:
    # partial() fixes the Kentucky-specific arguments, leaving a function of the body alone.
    split = partial(split_body, lead=r"^\[\s*\d+(?:-\d+)? Credit Hours\s*\]", labels=LABELS, req_labels=REQS)
    rows, empty = description_rows(SCHOOL, split)
    write_descriptions(SCHOOL, rows, empty)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
