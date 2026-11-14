"""Shared helpers for schools whose catalog runs on Acalog (batch 4).

Tennessee, Kentucky, Buffalo, Stony Brook, and UVA publish their catalogs on Acalog
("Modern Campus Catalog"). Their pages were saved through Chrome as bundles (see
collect_common.acalog_namer), so each school's raw folder holds:
- <date>_bs-cs-catalog.html: the program page (preview_program.php), whose layout and
  plan differ from school to school, so each school's parse_<id>.py reads it;
- courses/<date>_<CODE>.html: one catalog entry per course (preview_course_nopop.php).
  These entries share one layout across schools: an <h1 id="course_preview_title">
  "COSC 203 - Data Structures", followed in the same table cell by the entry's text,
  and ending with a "Back to Top" link. That shared part is read here.

What follows the title differs by school (credits before or after the description;
"Prerequisite(s):", "Prereq:", or "Requisites:"), so read_entry() returns the raw text
after the title, and each school's parse_<id>_descriptions.py splits it.
"""

import re
from pathlib import Path

from bs4 import BeautifulSoup

# The code at the start of an entry title: subject letters, a space (Acalog writes a
# non-breaking one, which clean() turns into a normal space), a number, and an optional
# letter suffix ("CS 450G", "CSE 4939W"); Tennessee marks Volunteer Core courses with
# "*" after the code ("BIOL 101* - ..."), which is skipped. Buffalo appends a component suffix to its
# codes ("CSE 115LLR" = lecture, lab, recitation); course_key() drops that.
TITLE = re.compile(r"^([A-Z]{2,4}) (\d{3,4}[A-Z]*)\*? - (.+)$")
# Buffalo's component suffix: the letters after its three-digit course number, which
# name the class's parts (LEC lecture, LR lecture-recitation, LLB lecture-lab, SR
# seminar-recitation, MNT ...). Buffalo's plans and lists sometimes drop it, and no
# Buffalo course number has a letter of its own, so all trailing letters are dropped.
UB_COMPONENT = re.compile(r"(?<=\d)[A-Z]+$")  # (?<=\d): only letters right after a digit


# Collapse whitespace (including non-breaking spaces) and drop the space that
# get_text(" ") leaves before punctuation after a link.
def clean(text: str) -> str:
    """Return whitespace- and punctuation-tidied text."""
    text = re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()
    return re.sub(r"\s+([.,;:)\]])", r"\1", text)  # \1 puts the punctuation back without the space


# Read one saved course entry. Returns (subject, number, title, body) where body is the
# entry's text after the title and before "Back to Top", or None if the file has no
# course title (not a course entry).
def read_entry(path: Path) -> tuple[str, str, str, str] | None:
    """Return the parts of one Acalog course entry, or None."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    h1 = soup.find("h1", id="course_preview_title")
    if h1 is None:
        return None
    m = TITLE.match(clean(h1.get_text(" ")))
    if not m:
        return None
    cell = h1.find_parent("td")  # the entry's text shares the title's table cell
    full = clean(cell.get_text(" "))
    head = clean(h1.get_text(" "))
    body = full.split(head, 1)[1]  # everything after the title...
    body = body.split("Back to Top", 1)[0].strip()  # ...up to the page's "Back to Top" link
    return m.group(1), m.group(2), m.group(3), body


# A course's lookup key: "SUBJ NUM". For Buffalo the component suffix is dropped
# ("CSE 115LLR" -> "CSE 115"), so one course has one key however it is written.
def course_key(subject: str, number: str, drop_component: bool = False) -> str:
    """Return the code used to match plan rows, e.g. "CSE 115"."""
    if drop_component:
        number = UB_COMPONENT.sub("", number)
    return f"{subject} {number}"


# Split an entry body into (description, prerequisites). `lead` is a regex for text to
# drop from the start (e.g. Tennessee's "3 Credit Hours"); `labels` lists every label
# that ends the description ("Prerequisite(s):", "Credit Restriction:", ...); the text
# from each label in `req_labels` up to the next label is joined as `prerequisites`.
def split_body(body: str, lead: str, labels: list[str], req_labels: list[str]) -> tuple[str, str]:
    """Return (description, prerequisites) cut from one entry body."""
    body = re.sub(lead, "", body, count=1).strip()
    # One alternation of all labels, longest first so "(RE) Prerequisite(s):" wins over
    # "Prerequisite(s):"; re.escape makes "(", ")", and "?" literal.
    pattern = re.compile("|".join(re.escape(l) for l in sorted(labels, key=len, reverse=True)))
    hits = list(pattern.finditer(body))  # every label, in the order it appears
    description = body[:hits[0].start()].strip() if hits else body
    reqs = []
    for i, m in enumerate(hits):
        if m.group(0) in req_labels:
            end = hits[i + 1].start() if i + 1 < len(hits) else len(body)
            reqs.append(body[m.start():end].strip())
    return description, " ".join(reqs)


# The rows of official_descriptions.csv for one school's saved entries: the newest
# snapshot of each courses/<date>_<CODE>.html, split by `split` (a function from body to
# (description, prerequisites)). Entries without description text are returned in
# `empty` so the caller can list them; describe.py fails later for any plan course
# that has none.
def description_rows(school, split, drop_component: bool = False) -> tuple[list[dict], list[str]]:
    """Return (official-description rows, names of entries without a description)."""
    import pandas as pd
    from common import rel
    manifest = pd.read_csv(school.raw / "sources.csv")
    urls = dict(zip(manifest["file"], manifest["url"]))  # zip pairs the two columns row by row
    newest = {}
    for path in sorted((school.raw / "courses").glob("*_*.html")):
        newest[path.name.split("_", 1)[1]] = path  # key without the date: later dates win
    rows, empty = [], []
    for path in newest.values():
        entry = read_entry(path)
        if entry is None:
            empty.append(path.name)
            continue
        subject, number, _, body = entry
        description, prereq = split(body)
        if not description:
            empty.append(path.name)
            continue
        rows.append({"course_code": course_key(subject, number, drop_component), "description": description,
                     "prerequisites": prereq, "description_url": urls.get(f"courses/{path.name}", ""),
                     "description_file": rel(path)})
    return rows, empty


# Write the rows and stop if any saved file is missing from sources.csv.
def write_descriptions(school, rows: list[dict], empty: list[str]) -> None:
    """Write official_descriptions.csv for a school and report skipped entries."""
    import pandas as pd
    from common import OFFICIAL_COLUMNS, rel
    out = school.processed / "official_descriptions.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=OFFICIAL_COLUMNS).to_csv(out, index=False)
    print(f"Wrote {len(rows)} official descriptions to {rel(out)}")
    if empty:
        print(f"Skipped (no description text): {', '.join(empty)}")
    missing = [r["description_file"] for r in rows if not r["description_url"]]
    if missing:
        raise SystemExit("CHECKS FAILED: not in sources.csv:\n  " + "\n  ".join(missing))
