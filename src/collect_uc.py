"""Download UC CS BS source pages into data/raw/uc/ and record them in a manifest.

Each file is saved unchanged with the retrieval date as a filename prefix
(e.g. 2026-10-17_cs-bs-majormap-class2031-sec1.html). Existing files are never
overwritten, so rerunning on a later date adds a new dated snapshot.

Every saved file gets a row in data/raw/uc/sources.csv (URL, file, date, checksum),
so any value parsed later can be traced back to the page it came from.

Usage:
    python src/collect_uc.py
"""

import csv
import hashlib
from datetime import date
from pathlib import Path

import requests

# Paths are built from this file's own location (__file__) rather than the current
# working directory, so the script works no matter which folder it is run from.
# .resolve() makes the path absolute; .parent.parent climbs from src/ to the repo root.
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "uc"
MANIFEST = RAW_DIR / "sources.csv"
COURSES_DIR = RAW_DIR / "courses"  # course detail pages, written by collect_uc_courses.py
# Column order for the manifest. Shared with collect_uc_courses.py so both scripts
# write rows with the same schema into the same file.
MANIFEST_COLUMNS = [
    "retrieved_date", "file", "url", "description", "method",
    "http_status", "bytes", "sha256",
]

# (slug, url, description). "Class of 2031" = students entering Fall 2026, which is
# how this project interprets the 2026-27 catalog year (see specs/02-data.md).
SOURCES = [
    (
        "cs-bs-majormap-class2031-sec1",
        "https://webapps2.uc.edu/ecurriculum/DegreePrograms/Home/MajorMap/11017",
        "Plan of study, Class of 2031 Section I (canonical plan)",
    ),
    (
        "cs-bs-majormap-class2031-sec2",
        "https://webapps2.uc.edu/ecurriculum/DegreePrograms/Home/MajorMap/11018",
        "Plan of study, Class of 2031 Section II (cross-check)",
    ),
    (
        "cs-bs-program-detail",
        "https://webapps2.uc.edu/ecurriculum/DegreePrograms/Program/Detail/20BC-CS-BSCS",
        "eCurriculum program detail: college, credit total, accreditation",
    ),
    (
        "cs-bs-ceas-program-page",
        # Two adjacent string literals are joined by Python at compile time; this just
        # splits one long URL across lines.
        "https://www.ceas.uc.edu/academics/departments/computer-science/degrees-programs/"
        "computer-science-bachelor-of-science.html",
        "CEAS program page: college, links to all major maps",
    ),
]

# Identify the script honestly to UC's servers instead of the default
# "python-requests/x.y" User-Agent, so site admins can see what is making the requests.
HEADERS = {"User-Agent": "curriculum-comparison research script (python-requests)"}


# Add one record to the shared manifest (sources.csv). The file is opened in append
# mode ("a"), so earlier rows are never rewritten. That makes the manifest an
# append-only log of every snapshot ever taken. The header row is written only the
# first time, when the file doesn't exist yet.
def append_manifest(row: dict) -> None:
    """Append one row to the manifest, writing the header if the file is new."""
    is_new = not MANIFEST.exists()  # check before open(): opening in "a" mode creates the file
    # newline="" is required by the csv module so it controls line endings itself
    # (otherwise Windows would get blank lines between rows).
    with MANIFEST.open("a", newline="", encoding="utf-8") as f:
        # DictWriter maps dict keys to columns by name, so the order of keys in `row`
        # doesn't matter; a missing or extra key raises an error instead of silently
        # misaligning columns.
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


# Download a single source page and save it as data/raw/uc/<date>_<slug>.html, then log
# it in the manifest.
# - Raw files are never overwritten: if today's snapshot already exists, the page is
#   skipped. A rerun on a different day creates a new dated file alongside the old one.
# - resp.content (raw bytes) is saved instead of resp.text (decoded string), so the file
#   is byte-for-byte what the server sent, and the SHA-256 checksum matches it exactly.
#   Anyone can later recompute the hash to confirm the raw file hasn't been edited.
def fetch(slug: str, url: str, description: str, today: str) -> None:
    path = RAW_DIR / f"{today}_{slug}.html"
    if path.exists():
        print(f"skip   {path.name} (already saved today)")
        return

    resp = requests.get(url, headers=HEADERS, timeout=30)  # timeout keeps a dead server from hanging the script forever
    resp.raise_for_status()  # turn 4xx/5xx responses into an exception, so an error page is never saved as a source
    path.write_bytes(resp.content)

    append_manifest({
        "retrieved_date": today,
        "file": path.name,
        "url": url,
        "description": description,
        "method": "script",
        "http_status": resp.status_code,
        "bytes": len(resp.content),
        "sha256": hashlib.sha256(resp.content).hexdigest(),  # fingerprint of the exact bytes saved
    })
    print(f"saved  {path.name} ({len(resp.content):,} bytes)")  # :, adds thousands separators


# Entry point: make sure the output folder exists, then fetch every page in SOURCES.
# The date is computed once, so all files from one run share the same prefix even if
# the run crosses midnight.
def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)  # parents=True creates missing parent folders; exist_ok avoids an error on reruns
    today = date.today().isoformat()  # e.g. "2026-10-17"; ISO format sorts correctly as text
    for slug, url, description in SOURCES:  # tuple unpacking: each SOURCES entry is (slug, url, description)
        fetch(slug, url, description, today)


# Run main() only when the file is executed as a script, not when it's imported.
# collect_uc_courses.py imports constants and append_manifest from this module, and
# this guard keeps that import from triggering a download.
if __name__ == "__main__":
    main()
