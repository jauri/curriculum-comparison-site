"""Download Ohio State's BS CSE curriculum sources into data/raw/osu/ and log them.

Ohio State has no plan of study labeled 2026-27 (see PROGRESS.md, step 10). The user
chose the CSE department's July 2025 curriculum sheet (a Word .docx, "Effective Term:
Autumn 2024", Individualized specialization) as the canonical plan. The older PDF that
the College of Engineering advising page labels "2026-2027" (effective Autumn 2022) is
saved as a cross-check, and the advising page itself is saved as evidence of that label.

Course descriptions are collected separately by collect_osu_courses.py.

Usage:
    python src/collect_osu.py
"""

from datetime import date

from collect_common import fetch
from common import load_school

SCHOOL = load_school("osu")

# (slug, url, description, file extension).
SOURCES = [
    ("bs-cse-curriculum-sheet-2025-07",
     "https://cse.osu.edu/media/document/2025-08-27/"
     "cse_curriculum_sheet_with_sample_schedule_july2025accessibleread-only_0.docx",
     "BS CSE curriculum sheet with sample schedule, July 2025, effective AU24, Individualized option (canonical plan)",
     ".docx"),
    ("bs-cse-curriculum-sheet-2023-03",
     "https://cse.osu.edu/sites/default/files/2023-03/CSE-Curriculum-Sheet-New-GE-IND-sample-schedule-with-GE-FINAL-1.pdf",
     "BS CSE curriculum sheet, updated 03/22/2023, effective AU22; linked as 2026-2027 by the advising page (cross-check)",
     ".pdf"),
    # The advising page (https://advising.engineering.osu.edu/node/17) that labels the 2023
    # PDF "2026-2027" was approved too, but it returns 403 Forbidden to every scripted
    # request (bot protection), so it isn't fetched. Its label is recorded in PROGRESS.md.
    ("bs-cse-program-page",
     "https://cse.osu.edu/current-students/undergraduate/majors/bachelors-science-computer-science-engineering-bs-cse",
     "CSE department BS CSE program page: college, AU22+ notes, link to the curriculum sheet", ".html"),
    ("bs-cse-specializations", "https://cse.osu.edu/bscse-and-bscis-specializations",
     "BS CSE and BS CIS specialization options", ".html"),
]


# Entry point: fetch every source with one date prefix.
def main() -> None:
    SCHOOL.raw.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    for slug, url, description, ext in SOURCES:
        fetch(SCHOOL.raw, slug, url, description, today, ext)


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
