"""Save Ohio State's official course descriptions into data/raw/osu/courses/.

Ohio State has no static course catalog page per course. Its public class search
(classes.osu.edu) is a JavaScript app backed by a JSON API, content.osu.edu/v2/classes/
search, which returns each matching course with its catalog description, credit hours,
and prerequisites (plus every section offered that term). This script saves one raw
API response per course, unchanged, and logs it in data/raw/osu/sources.csv
(method = script-api). parse_osu_descriptions.py later pulls the description out.

The term is Autumn 2026 (OSU term code 1268), the first term of the 2026-27 academic
year. A course not offered that term is looked up in Spring 2027 (1272) instead.

The course list is typed in below from the canonical curriculum sheet (July 2025,
Individualized option), including every option of the "X or Y" choices, because the
sheet is a Word file whose codes are written in shorthand ("CSE 2221 and 2231",
"CSE 591X"). describe.py fails if any plan row lacks a description, so a course
missing from this list is caught later.

Usage:
    python src/collect_osu_courses.py
"""

import time
from datetime import date

import requests

from collect_common import HEADERS, save
from common import load_school

SCHOOL = load_school("osu")
API = "https://content.osu.edu/v2/classes/search"
TERMS = [("1268", "Autumn 2026"), ("1272", "Spring 2027")]  # (OSU term code, name), in order of preference

# (subject, base catalog number). ENGR numbers have decimal variants (1181.01, 1100.15);
# the base number matches all of them, and the parser picks one.
COURSES = [
    ("CSE", n) for n in [
        "1223", "2221", "2231", "2321", "2331", "2421", "2431", "2501", "3231", "3241",
        "3341", "3421", "3461", "3521", "3541", "3901", "3902", "3903",
        "5911", "5912", "5913", "5914", "5915",
    ]
] + [
    ("PHILOS", "2338"), ("ECE", "2060"), ("ECE", "2360"),
    # MATH 1152 appears in the sample schedule where the requirements list says 1172
    # (a likely typo, step 10); both are saved so the parser can show the difference.
    ("MATH", "1151"), ("MATH", "1172"), ("MATH", "1152"), ("MATH", "2568"), ("MATH", "3345"),
    ("STAT", "3470"), ("PHYSICS", "1250"),
    ("ENGR", "1100"), ("ENGR", "1181"), ("ENGR", "1182"), ("GENED", "1201"),
]
PAUSE_SECONDS = 1.0  # be polite to OSU's server between requests


# True if an API response lists the course itself (not just courses that mention the
# number in their text). split(".")[0] drops a decimal suffix: "1181.01" -> "1181".
def has_course(data: dict, subject: str, number: str) -> bool:
    """Return True if the response contains subject/number among its courses."""
    return any(c["course"]["subject"] == subject and c["course"]["catalogNumber"].split(".")[0] == number
               for c in data["courses"])


# Entry point: for each course, try each term until the response contains the course,
# then save that response. Today's existing files are skipped without a request.
def main() -> None:
    today = date.today().isoformat()
    missing = []
    for subject, number in COURSES:
        name = f"courses/{today}_osu-classes_{subject}{number}.json"
        if (SCHOOL.raw / name).exists():
            print(f"skip   {name} (already saved today)")
            continue
        for code, term_name in TERMS:
            # params= builds the query string (and URL-encodes it); resp.url is the full URL.
            resp = requests.get(API, params={"q": number, "subject": subject.lower(), "campus": "col",
                                             "term": code, "p": 1}, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            time.sleep(PAUSE_SECONDS)
            if has_course(resp.json()["data"], subject, number):
                save(SCHOOL.raw, name, resp.url, f"OSU class search API, {subject} {number}, {term_name}",
                     "script-api", resp, today)
                break
        else:
            # for/else: this runs only when the loop finished without `break`, i.e. no term had it.
            missing.append(f"{subject} {number}")
    # A warning, not an error: some options are simply not offered in 2026-27 (CSE 5913,
    # one of the capstone choices, wasn't on 2026-10-17). describe.py still fails if a
    # course that is a plan row of its own has no description.
    if missing:
        print(f"WARNING: not offered in {' or '.join(t for _, t in TERMS)}: {', '.join(missing)}")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
