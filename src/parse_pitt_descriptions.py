"""Read Pitt's official course descriptions from the saved catalog course entries.

Pitt's school-specific description parser (batch 5). Reads every course entry saved
through Chrome by collect_pitt.py (data/raw/pitt/courses/<date>_<CODE>.html) and writes
data/processed/pitt/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS). The
shared Acalog layout is read by acalog.py; this script only says how Pitt's entry text
is laid out:

    Minimum Credits: 3 Maximum Credits: 3 Long Description As the second in a ...
    Academic Career: Undergraduate Course Component: Lecture ... Course Requirements:
    PREQ: (CS 0441 or ...) ... Click here for class schedule information.

The credit range and the "Long Description" label lead the text, the description
follows, and labeled course attributes come after. "Course Requirements:" (the
requisites) becomes `prerequisites`.

Usage:
    python src/parse_pitt_descriptions.py
"""

from functools import partial

from acalog import description_rows, split_body, write_descriptions
from common import load_school

SCHOOL = load_school("pitt")
# Labels that end the description, as Pitt's entries write them.
LABELS = ["Academic Career:", "Course Component:", "Grade Component:", "Course Requirements:",
          "Course Attributes:", "Click here for class schedule information"]
REQS = ["Course Requirements:"]
# What leads every entry: "Minimum Credits: 3 Maximum Credits: 3 Long Description".
# [\d.]+ allows fractional credits; (?: Long Description)? because a few entries lack it.
LEAD = r"^Minimum Credits: [\d.]+ Maximum Credits: [\d.]+(?: Long Description)?"


# Entry point: split every saved entry and write the table.
def main() -> None:
    # partial() fixes the Pitt-specific arguments, leaving a function of the body alone.
    split = partial(split_body, lead=LEAD, labels=LABELS, req_labels=REQS)
    rows, empty = description_rows(SCHOOL, split)
    write_descriptions(SCHOOL, rows, empty)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
