"""Read Tennessee's official course descriptions from the saved catalog course entries.

Tennessee's school-specific description parser (batch 4). Reads every course entry saved
through Chrome by collect_utk.py (data/raw/utk/courses/<date>_<CODE>.html) and writes
data/processed/utk/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS). The
shared Acalog layout is read by acalog.py; this script only says how Tennessee's entry
text is laid out:

    3 Credit Hours Design, analysis, and implementation of ... Credit Restriction: ...
    (RE) Prerequisite(s): COSC 103 with a grade of C or better. (RE) Corequisite(s): COSC 204

The credit hours lead the text, the description follows, and labeled parts come after
("(RE)" marks a registration-enforced requisite). Requisites become `prerequisites`.

Usage:
    python src/parse_utk_descriptions.py
"""

from functools import partial

from acalog import description_rows, split_body, write_descriptions
from common import load_school

SCHOOL = load_school("utk")
# Labels that end the description, as Tennessee's entries write them.
LABELS = ["(RE) Prerequisite(s):", "Prerequisite(s):", "(RE) Corequisite(s):", "Corequisite(s):",
          "Credit Restriction:", "Comment(s):", "Contact Hour Distribution:", "Registration Permission:",
          "Registration Restriction(s):", "Recommended Background:", "Repeatability:", "Grading Restriction:",
          "Cross-listed:"]
REQS = ["(RE) Prerequisite(s):", "Prerequisite(s):", "(RE) Corequisite(s):", "Corequisite(s):"]


# Entry point: split every saved entry and write the table.
def main() -> None:
    # partial() fixes the Tennessee-specific arguments, leaving a function of the body alone.
    split = partial(split_body, lead=r"^\d+(?:-\d+)? Credit Hours", labels=LABELS, req_labels=REQS)
    rows, empty = description_rows(SCHOOL, split)
    write_descriptions(SCHOOL, rows, empty)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
