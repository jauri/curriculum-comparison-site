"""Read USC's official course descriptions from the saved Catalogue course entries.

USC's school-specific description parser (batch 5). Reads every course entry saved
through Chrome by collect_usc.py (data/raw/usc/courses/<date>_<CODE>.html) and writes
data/processed/usc/official_descriptions.csv (columns in common.OFFICIAL_COLUMNS).

USC's Catalogue is Acalog, but its entry titles differ from the other Acalog schools'
in two ways, so acalog.read_entry() can't be used as is:
- the code and title have no " - " between them: "CSCI 270 Introduction to Algorithms";
- codes carry letter suffixes that mark labs and general education ("CSCI 103L",
  "MATH 125g", "CHEM 105aLg"), and the Viterbi guide writes some codes with a
  different suffix than the Catalogue ("CSCI 201L" vs "CSCI 201", "CSCI 104" vs
  "CSCI 104L").
So each course is keyed by subject and number alone ("CSCI 103", "CHEM 105"), the
form parse_usc.py also uses for the plan, and the suffix is dropped. No two saved
entries share a subject and number.

The entry text after the title is laid out as

    Units: 4 Terms Offered: FaSpSm Algorithm analysis. ... Prerequisite: ( CSCI 104 or
    CSCI 114 ) and CSCI 170 Duplicates Credit In former CSCI 303 Instruction Mode: ...

The units and terms lead, the description follows, and labeled parts come after;
"Prerequisite:", "Corequisite:" and "Recommended Preparation:" become `prerequisites`.

Usage:
    python src/parse_usc_descriptions.py
"""

import re
from functools import partial

import pandas as pd
from bs4 import BeautifulSoup

from acalog import clean, split_body
from common import OFFICIAL_COLUMNS, load_school, rel

SCHOOL = load_school("usc")
# Title: subject, a space, three digits, any letter suffix (upper or lower case), the title.
TITLE = re.compile(r"^([A-Z]{2,4}) (\d{3})[A-Za-z]* (.+)$")
LABELS = ["Prerequisite:", "Corequisite:", "Recommended Preparation:", "Concurrent Enrollment:",
          "Satisfies New General Education", "Satisfies Old General Education", "Duplicates Credit In",
          "Restriction:", "Registration Restriction:", "Mutually Exclusive", "Instruction Mode:", "Grading Option:"]
REQS = ["Prerequisite:", "Corequisite:", "Recommended Preparation:", "Concurrent Enrollment:"]
# "Units: 4 Terms Offered: FaSpSm" leads every entry; units may be a range ("1-4") or
# "4, max 8", a repeatable course adds "Maximum Units: max 8" (CSCI 401), and Terms
# Offered may be missing, hence the optional groups.
LEAD = r"^Units: [\d.\-, a-z]+?(?= [A-Z])(?: Maximum Units: max \d+)?(?: Terms Offered: \S+)?"


# Read one entry: (key, title, body) or None if the file has no course title.
def read_usc_entry(path) -> tuple[str, str, str] | None:
    """Return ("CSCI 270", title, body after the title) for one saved entry."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    h1 = soup.find("h1", id="course_preview_title")
    if h1 is None:
        return None
    head = clean(h1.get_text(" "))
    m = TITLE.match(head)
    if not m:
        return None
    full = clean(h1.find_parent("td").get_text(" "))  # the entry's text shares the title's table cell
    body = full.split(head, 1)[1].split("Back to Top", 1)[0].strip()
    return f"{m.group(1)} {m.group(2)}", m.group(3), body


# Entry point: split every newest saved entry and write the table.
def main() -> None:
    manifest = pd.read_csv(SCHOOL.raw / "sources.csv")
    urls = dict(zip(manifest["file"], manifest["url"]))  # zip pairs the two columns row by row
    newest = {}
    for path in sorted((SCHOOL.raw / "courses").glob("*_*.html")):
        newest[path.name.split("_", 1)[1]] = path  # key without the date: later dates win
    split = partial(split_body, lead=LEAD, labels=LABELS, req_labels=REQS)
    rows, empty = [], []
    for path in newest.values():
        entry = read_usc_entry(path)
        description, prereq = split(entry[2]) if entry else ("", "")
        if not description:
            empty.append(path.name)
            continue
        rows.append({"course_code": entry[0], "description": description, "prerequisites": prereq,
                     "description_url": urls.get(f"courses/{path.name}", ""), "description_file": rel(path)})
    codes = [r["course_code"] for r in rows]
    if len(codes) != len(set(codes)):
        raise SystemExit("CHECKS FAILED: two entries share a subject and number.")
    out = SCHOOL.processed / "official_descriptions.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OFFICIAL_COLUMNS).to_csv(out, index=False)
    print(f"Wrote {len(rows)} official descriptions to {rel(out)}")
    if empty:
        print(f"Skipped (no description text): {', '.join(empty)}")
    missing = [r["description_file"] for r in rows if not r["description_url"]]
    if missing:
        raise SystemExit("CHECKS FAILED: not in sources.csv:\n  " + "\n  ".join(missing))


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
