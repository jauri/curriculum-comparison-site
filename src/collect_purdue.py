"""Import Purdue's CS BS catalog pages into data/raw/purdue/ and log them in sources.csv.

Purdue's 2026-2027 University Catalog (Acalog, catalog id 19) sits behind an AWS bot
filter that answers scripts with an empty "challenge" response (HTTP 202), so, as for
Virginia Tech, the pages are saved through the user's Chrome: a same-origin fetch() in
an open catalog page reads each page, and the unchanged bytes go into a JSON bundle.
Two bundles were downloaded, each from a fresh tab (Chrome blocks a tab's second
automatic download):

- purdue_bundle_programs.json: the Department of Computer Science page (College of
  Science; lists the programs) and the nine "Computer Science: <Track>, BS" program
  pages. Purdue's CS BS is one degree with nine tracks, and each track's page has its
  own eight-semester plan of study. The parser builds one plan from all nine (common
  courses required, track-specific requirements as slots; specs/05-comparison-set.md).
- purdue_bundle_courses.json: one course page (preview_course_nopop.php) per course
  code named in the plans, 20 in all. The course ids come from the plans' course links;
  COM 21700, named only as text, was looked up with the catalog search.

Purdue's 2026 "Degree Progression Guide" is on SharePoint behind a Purdue login, so
the catalog's own plans are used (decided with the user).

Sources were reviewed and approved by the user before downloading (step 13, batch 3).

Usage:
    python src/collect_purdue.py --import-bundle ~/Downloads/purdue_bundle_programs.json \
                                 --import-bundle ~/Downloads/purdue_bundle_courses.json
"""

import argparse
import base64
import re
from datetime import date
from pathlib import Path

from collect_common import import_bundle
from common import load_school

SCHOOL = load_school("purdue")
# Acalog program title, e.g. "Computer Science: Machine Intelligence, BS".
TRACK = re.compile(r"Computer Science: ([^,<]+), BS")


# Raw-folder name for a bundle page: the department page, a track's program page
# (program-<track-slug>.html), or a course page (courses/<code>.html).
def name_for(page: dict) -> str:
    """Return the file name (without date) for one bundle page."""
    if "course_code" in page:
        return f"courses/{page['course_code'].replace(' ', '')}.html"
    if "preview_entity.php" in page["url"]:
        return "dept-cs-catalog.html"
    html = base64.b64decode(page["base64"]).decode("utf-8", "replace")
    track = TRACK.search(html).group(1)
    # "Database and Information Systems" -> "database-and-information-systems"
    return f"program-{re.sub(r'[^a-z]+', '-', track.lower()).strip('-')}.html"


# Manifest description for a bundle page.
def describe(page: dict) -> str:
    """Return the sources.csv description for one bundle page."""
    if "course_code" in page:
        return f"Course page, {page['course_code']}, 2026-2027 University Catalog."
    if "preview_entity.php" in page["url"]:
        return ("Department of Computer Science, 2026-2027 University Catalog (College of Science): lists the "
                "nine CS BS track programs.")
    html = base64.b64decode(page["base64"]).decode("utf-8", "replace")
    return (f"Computer Science: {TRACK.search(html).group(1)}, BS, 2026-2027 University Catalog: requirements "
            "and eight-semester plan of study (one of nine track plans combined into the canonical plan).")


# Entry point: import each Chrome-saved bundle.
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    # action="append": the flag may be given several times, collecting a list.
    parser.add_argument("--import-bundle", type=Path, action="append", required=True,
                        help="path of a Purdue bundle JSON (repeatable)")
    args = parser.parse_args()
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()  # one date for the whole run, e.g. "2026-10-17"
    for bundle in args.import_bundle:
        import_bundle(SCHOOL.raw, bundle.expanduser(), name_for, describe, today)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
