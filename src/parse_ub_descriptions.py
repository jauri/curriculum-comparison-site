"""Read Buffalo's official course descriptions from the saved catalog course entries.

Buffalo's school-specific description parser (batch 4). Reads every course entry saved
through Chrome by collect_ub.py (data/raw/ub/courses/<date>_<CODE>.html) and writes
data/processed/ub/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS). The
shared Acalog layout is read by acalog.py; this script only says how Buffalo's entry
text is laid out:

    Provides the fundamentals of computer science ... Credits: 4 Grading Graded (GRD)
    Typically Offered: Fall, Spring, Summer Requisites: Prerequisite: ...

The description comes first and ends at "Credits:"; "Requisites:" (or "Prerequisite:")
starts `prerequisites`. Codes are keyed without Buffalo's component suffix
("CSE 115LLR" -> "CSE 115"), matching parse_ub.py.

Usage:
    python src/parse_ub_descriptions.py
"""

from functools import partial

from acalog import description_rows, split_body, write_descriptions
from common import load_school

SCHOOL = load_school("ub")
# Labels that end the description, as Buffalo's entries write them.
LABELS = ["Credits:", "Grading", "Typically Offered:", "Requisites:", "Requisite:", "Prerequisites:",
          "Prerequisite:", "Corequisite:"]
REQS = ["Requisites:", "Requisite:", "Prerequisites:", "Prerequisite:", "Corequisite:"]


# Entry point: split every saved entry and write the table.
def main() -> None:
    # partial() fixes Buffalo's arguments; nothing leads the text, so `lead` matches nothing.
    split = partial(split_body, lead=r"^(?!)", labels=LABELS, req_labels=REQS)  # (?!) never matches
    rows, empty = description_rows(SCHOOL, split, drop_component=True)
    write_descriptions(SCHOOL, rows, empty)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
