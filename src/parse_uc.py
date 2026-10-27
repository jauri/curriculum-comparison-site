"""Parse UC's saved plan of study (major map) into one row per course or requirement slot.

Reads the newest saved Class of 2031 Section I major map from data/raw/uc/ and writes
data/processed/uc/plan_parsed.csv. Each row keeps UC's original placement (calendar term,
year of the 5-year plan) and whether that term is an academic or a co-op term. This is
an intermediate table: normalization to 8 semesters (step 4), descriptions (step 5), and
canonical matching (step 6) add the remaining columns of the final schema in
specs/04-outputs.md.

Modeling decisions (made with the user in step 3; see PROGRESS.md):
- The first-year science choice (PHYS, CHEM, or BIOL) becomes ONE slot row per term,
  with the options listed in `notes`.
- Gen-ed slots follow Section I's layout. The first of UC's two alternative gen-ed
  bundles is recorded in `notes`; the alternative is noted too.
- PD1011 and PD2050 (1-credit co-op prep courses taken in academic terms) are ordinary
  academic courses: is_coop = false.

Credits are stored as a range (credits_min, credits_max) because the science slots are
4 or 5 credits depending on the choice; UC's own degree total is a range (124-126) for
the same reason.

The script also parses Section II and compares its courses with Section I as a
cross-check, then runs the step 3 checks and exits with an error if any fail. One check
compares the credit total stated on the page with the one recorded for UC in
data/reference/schools.csv, which the shared validate.py later checks the final table
against.

This is UC's school-specific parser (phase 2, step 9: one parser per school). It writes
the columns in common.PARSED_COLUMNS so the shared steps can process its output.

Usage:
    python src/parse_uc.py
"""

import re
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

# common.py lives next to this file; running `python src/parse_uc.py` puts src/ on the
# import path. It holds the folder layout and the school registry (schools.csv).
from common import PARSED_COLUMNS, finish_choices, load_school, rel

# Institution, program, catalog year (2026-27 = Class of 2031, entering Fall 2026; see
# specs/02-data.md), and the stated credit total come from the registry row.
SCHOOL = load_school("uc")
OUT_CSV = SCHOOL.processed / "plan_parsed.csv"

COHORT = "Class of 2031"
FIRST_FALL = 2026  # calendar year of the cohort's first fall term; anchors orig_year

# A whole cell that is exactly one UC course code: 2-5 capital letters (subject), 4
# digits, and an optional letter suffix (the "C" in CS2028C). The ^...$ anchors reject
# cells that only *contain* a code, such as the science options' prose.
COURSE_CODE = re.compile(r"^([A-Z]{2,5})(\d{4}[A-Z]?)$")
# A credit cell: either one number ("3") or a range ("4 - 5"). The second group is
# optional ((...)? ), so for a single number it comes back as None.
CREDITS = re.compile(r"^(\d+)(?:\s*-\s*(\d+))?$")
# Minimum-grade notes UC appends to titles, e.g. "(C- min)". [A-D][+-]? matches a
# letter grade with an optional plus or minus.
MIN_GRADE = re.compile(r"\(([A-D][+-]?) min\)")
# A term heading such as "Summer 2029": season, then a 4-digit year.
TERM_HEADING = re.compile(r"^(Fall|Spring|Summer) (\d{4})$")


# Convert a calendar term to its year in UC's 5-year plan. A plan year runs Fall, Spring,
# Summer, so Spring and Summer belong to the plan year that started the previous fall:
# Fall 2026 and Spring 2027 are year 1, Summer 2028 is year 2, Fall 2028 is year 3.
def plan_year(season: str, year: int) -> int:
    """Return the 1-based year of the plan that a calendar term falls in."""
    return year - FIRST_FALL + (1 if season == "Fall" else 0)


# Turn a credit cell into (min, max). A single number gives min == max; "4 - 5" gives
# (4, 5). Returning a pair for every row keeps the credit columns uniform.
def parse_credits(text: str) -> tuple[int, int]:
    """Parse '3' or '4 - 5' into a (min, max) pair of ints."""
    m = CREDITS.match(text.strip())
    if not m:
        raise ValueError(f"Unrecognized credit value: {text!r}")
    low = int(m.group(1))
    high = int(m.group(2)) if m.group(2) else low  # no second number -> not a range
    return low, high


# Split a table cell into its visible lines of text. get_text("\n") puts a newline
# between the text of separate tags (<br>, <div>), and UC's HTML is full of tab
# indentation, so each line is stripped and blank lines are dropped.
def cell_lines(cell) -> list[str]:
    """Return the non-empty, whitespace-trimmed text lines of a BeautifulSoup tag."""
    return [line.strip() for line in cell.get_text("\n").splitlines() if line.strip()]


# Gather every table that sits under one <h2> heading. The page is a flat sequence of
# <h2> term headings, each followed by one or more tables, so a table belongs to the
# heading that most recently precedes it. find_all_next walks forward through the
# document; checking find_previous("h2") stops us at the next term's tables.
def tables_under(h2) -> list:
    """Return the <table> elements between this <h2> and the next one."""
    return [t for t in h2.find_all_next("table") if t.find_previous("h2") is h2]


# Read one table row of a normal (non-choice) group into a dict.
# The three cells are: course code (with an optional "GenEd: XXX" tag in a nested
# <div>), title (with an optional "(C- min)" grade note and extra prose), and credits.
# Rows without a course code are requirement slots, such as "CS Electives" (whose code
# cell holds just the subject "CS") or "General Education course".
def parse_row(tr) -> dict:
    """Parse a 3-cell plan row into course/slot fields."""
    code_cell, title_cell, credit_cell = tr.find_all("td")
    code_lines = cell_lines(code_cell)
    title_lines = cell_lines(title_cell)

    # The GenEd tag sits in its own <div>; its text reads "GenEd:\n ENC" (or "GenEd: AH, CD").
    gened_div = code_cell.find("div")
    gened_tag = ""
    if gened_div:
        gened_tag = " ".join(cell_lines(gened_div)).removeprefix("GenEd:").strip()

    # The first line of the code cell is the code itself, if there is one at all.
    first = code_lines[0] if code_lines else ""
    code_match = COURSE_CODE.match(first)

    # Pull the grade note out of the title lines and keep anything else after the title
    # line (e.g. "See requirement below.") as a note.
    title_text = " ".join(title_lines)
    grade = MIN_GRADE.search(title_text)
    rest = [ln for ln in title_lines[1:] if not MIN_GRADE.fullmatch(ln)]

    low, high = parse_credits(credit_cell.get_text())
    return {
        "subject": code_match.group(1) if code_match else first,  # "CS" for CS Electives, else blank
        "number": code_match.group(2) if code_match else "",
        "course_code": f"{code_match.group(1)} {code_match.group(2)}" if code_match else "",
        "title": title_lines[0] if title_lines else "",
        "credits_min": low,
        "credits_max": high,
        "gened_tag": gened_tag,
        "min_grade": grade.group(1) if grade else "",
        "uc_note": " ".join(rest),
    }


# Decide which of the spec's requirement types a parsed row is (specs/04-outputs.md):
# coop, required (a named course), gen_ed (a gen-ed slot), or elective_slot (CS or
# directed electives). Named courses that also satisfy gen-ed (e.g. ENGL1001, tagged
# ENC) stay "required" because the course itself is fixed; their tag is kept in
# gened_tag.
def requirement_type(row: dict) -> str:
    """Classify a parsed row as required / elective_slot / gen_ed / coop."""
    if row["subject"] == "COOP":
        return "coop"
    if row["number"]:
        return "required"
    if "General Education" in row["title"]:
        return "gen_ed"
    return "elective_slot"


# Collapse a "Select one of ..." choice table (the first-year science options) into a
# single slot row, as decided with the user. The credit range spans the options.
# Edge case: in the spring table UC lists the "continue in the same discipline" option
# (PHYS2002 / CHEM1041 / BIOL1082 with lab) as 0 credits, which is clearly a data-entry
# error since those are 4-5 credit lecture/lab pairs like the fall ones. Zero-credit
# options are therefore ignored when computing the range, and the note says so.
def parse_choice(table, part: int) -> dict:
    """Return one science-slot row summarizing a 'Select one of' choice table."""
    options, codes, lows, highs, zero_credit = [], [], [], [], False
    for tr in table.select("tbody tr"):  # CSS selector: every <tr> inside the <tbody>
        code_cell, title_cell, credit_cell = tr.find_all("td")
        low, high = parse_credits(credit_cell.get_text())
        options.append(" ".join(cell_lines(title_cell)))
        # Every course code named in the option, written "PHYS 2001" like course_code.
        # UC puts the code inside the option's prose ("College Physics I (PHYS2001) with
        # Lab"), so both cells are searched. findall returns (subject, number) pairs.
        text = code_cell.get_text(" ") + " " + title_cell.get_text(" ")
        codes += [f"{s} {n}" for s, n in re.findall(r"\b([A-Z]{2,5})(\d{4}[A-Z]?)\b", text)]
        if high == 0:
            zero_credit = True
            continue
        lows.append(low)
        highs.append(high)

    note = "Student chooses one: " + " | ".join(options)
    if zero_credit:
        note += " [UC lists the same-discipline option as 0 credits; treated as a UC typo and ignored for the credit range.]"
    sequence = "I" if part == 1 else "II"
    return {
        "subject": "",
        "number": "",
        "course_code": "",
        "title": f"Science sequence {sequence} (PHYS/CHEM/BIOL lecture + lab)",
        "credits_min": min(lows),
        "credits_max": max(highs),
        "gened_tag": "",
        "min_grade": "",
        "uc_note": note,
        # dict.fromkeys keeps the first occurrence of each code in order (an ordered de-dup).
        "options": "; ".join(dict.fromkeys(codes)),
    }


# Read UC's "General Education" section: two alternative bundles of gen-ed categories,
# each a list of (tag, title, credits). These aren't placed in any term, so they become
# notes on the gen-ed slot rows and a credit check, not rows of their own.
def parse_gened_bundles(h2) -> list[dict]:
    """Return [{'title': ..., 'items': [(tag, title, credits), ...]}, ...] for each bundle."""
    bundles = []
    for table in tables_under(h2):
        title = " ".join(cell_lines(table.find("h3")))
        items = []
        for tr in table.select("tbody tr"):
            code_cell, title_cell, credit_cell = tr.find_all("td")
            tag = " ".join(cell_lines(code_cell)).removeprefix("GenEd:").strip()
            items.append((tag, " ".join(cell_lines(title_cell)), parse_credits(credit_cell.get_text())[0]))
        bundles.append({"title": title, "items": items})
    return bundles


# Format a gen-ed bundle as one readable line for the notes column,
# e.g. "AH, CD 3 cr + AH 3 cr + SBS 6 cr".
def bundle_summary(bundle: dict) -> str:
    """Return a compact 'TAG n cr + ...' summary of a gen-ed bundle."""
    return " + ".join(f"{tag} {credits} cr" for tag, _, credits in bundle["items"])


# Parse a whole major map into a DataFrame, plus the stated credit range and gen-ed
# bundles for the checks. Walks the <h2> headings in page order: term headings produce
# rows; the "General Education" heading produces the bundles.
# A term is a co-op term if it contains a COOP course: UC's co-op terms hold exactly
# one 0-credit COOP course and nothing else.
def parse_map(path: Path) -> tuple[pd.DataFrame, tuple[int, int], list[dict]]:
    """Return (rows, (stated_min, stated_max), gened_bundles) for one major map file."""
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")

    # The stated degree total appears as "124 - 126 Credits" near the top of the page.
    stated = re.search(r"(\d+)\s*-\s*(\d+)\s*Credits", soup.get_text(" "))
    stated_range = (int(stated.group(1)), int(stated.group(2)))

    rows, bundles, science_part = [], [], 0
    for h2 in soup.find_all("h2"):
        heading = h2.get_text(strip=True)
        if heading == "General Education":
            bundles = parse_gened_bundles(h2)
            continue
        term = TERM_HEADING.match(heading)
        if not term:
            continue  # some other heading; not part of the plan
        season, year = term.group(1), int(term.group(2))

        term_rows = []
        for table in tables_under(h2):
            group_title = " ".join(cell_lines(table.find("h3")))
            if group_title.startswith("Select one of"):
                science_part += 1
                term_rows.append(parse_choice(table, science_part))
            else:
                term_rows.extend(parse_row(tr) for tr in table.select("tbody tr"))

        # Generator inside any(): True as soon as one row in this term is a COOP course.
        term_type = "coop" if any(r["subject"] == "COOP" for r in term_rows) else "academic"
        for r in term_rows:
            r.update(
                orig_year=plan_year(season, year),
                orig_term=season,
                orig_calendar_year=year,
                orig_term_type=term_type,
                requirement_type=requirement_type(r),
            )
            # Only the COOP courses themselves are co-op rows (PD1011/PD2050 are academic).
            r["is_coop"] = r["requirement_type"] == "coop"
            r["counts_toward_total"] = True  # every UC row counts toward 124-126
            r.setdefault("options", "")  # only choice slots have options; setdefault keeps theirs
        rows.extend(term_rows)

    return pd.DataFrame(rows), stated_range, bundles


# Build the notes column from the pieces collected while parsing: UC's own remarks,
# the gen-ed bundle assumption, and the science-slot description.
def add_notes(df: pd.DataFrame, bundles: list[dict]) -> pd.Series:
    """Return a notes Series for the parsed rows."""
    gened_note = (
        f"Gen-ed slot. Assumed bundle (UC's first option, C&D counted as AH): {bundle_summary(bundles[0])}. "
        f"Alternative (C&D counted as SBS): {bundle_summary(bundles[1])}. "
        "UC does not say which category goes in which term."
    )
    notes = []
    for _, r in df.iterrows():  # iterrows yields (index, row-as-Series) pairs
        parts = []
        if r["requirement_type"] == "gen_ed":
            parts.append(gened_note)
        if r["uc_note"]:
            parts.append(f"UC: {r['uc_note']}")
        if r["number"] in ("1011", "2050") and r["subject"] == "PD":
            parts.append("Co-op preparation course taken in an academic term; counted as academic (is_coop = false).")
        notes.append(" ".join(parts))
    return pd.Series(notes, index=df.index)


# Run the step 3 checks and return a list of failure messages (empty = all passed).
# - The credit range must equal UC's stated degree total.
# - There must be exactly 8 academic terms (the normalization rule in
#   specs/03-processing.md depends on it).
# - The gen-ed slots in the terms must add up to each bundle's total.
def check(df: pd.DataFrame, stated: tuple[int, int], bundles: list[dict]) -> list[str]:
    """Return a list of failed-check messages."""
    failures = []
    total = (df["credits_min"].sum(), df["credits_max"].sum())
    if total != stated:
        failures.append(f"Credit total {total} does not match UC's stated {stated}.")
    # The registry copy is what validate.py checks the final table against, so it must
    # agree with the page it was typed in from.
    if SCHOOL.credits != stated:
        failures.append(f"schools.csv says {SCHOOL.credits} credits but the page states {stated}.")

    # drop_duplicates on (year, season) counts each academic term once, however many rows it has.
    academic_terms = df[df["orig_term_type"] == "academic"].drop_duplicates(["orig_calendar_year", "orig_term"])
    if len(academic_terms) != 8:
        failures.append(f"Expected 8 academic terms, found {len(academic_terms)}.")

    gened_slots = df.loc[df["requirement_type"] == "gen_ed", "credits_min"].sum()
    for b in bundles:
        bundle_total = sum(credits for _, _, credits in b["items"])
        if bundle_total != gened_slots:
            failures.append(f"Gen-ed slots total {gened_slots} cr but bundle '{b['title']}' needs {bundle_total}.")
    return failures


# Compare two sections' course lists. Sections differ only in co-op rotation, so the
# same courses and slots (code + requirement type + credits) should appear in both,
# possibly in different terms. Titles are left out of the key on purpose: Section II
# words its slot titles differently (e.g. "Directedl Elective", "General Education
# course - See requirement below"), which isn't a real curriculum difference.
# Counter-like comparison via value_counts handles slots that appear more than once
# (e.g. several "General Education course" rows).
def compare_sections(sec1: pd.DataFrame, sec2: pd.DataFrame) -> list[str]:
    """Return human-readable differences between two sections' rows (ignoring placement)."""
    key = ["course_code", "requirement_type", "credits_min", "credits_max"]
    # value_counts over several columns counts each distinct combination; subtracting
    # the two (fill_value=0 for combinations missing on one side) leaves the mismatches.
    diff = sec1.value_counts(key).sub(sec2.value_counts(key), fill_value=0)
    return [f"{'only in I' if n > 0 else 'only in II'}: {k}" for k, n in diff.items() if n != 0]


# Script entry point: parse both sections, check, cross-check, and write the CSV.
def main() -> None:
    sec1_path = SCHOOL.newest(SCHOOL.credits_source)  # the Section I map states the total
    sec2_path = SCHOOL.newest("*_cs-bs-majormap-class2031-sec2.html")
    df, stated, bundles = parse_map(sec1_path)
    sec2, _, _ = parse_map(sec2_path)

    df["notes"] = add_notes(df, bundles)
    df.insert(0, "institution", SCHOOL.institution)  # insert(position, column, value) puts constants first
    df.insert(1, "program", SCHOOL.program)
    df.insert(2, "catalog_year", SCHOOL.catalog_year)
    df.insert(3, "plan", f"{COHORT} Section I")
    df["source_file"] = rel(sec1_path)

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    finish_choices(df)[PARSED_COLUMNS].to_csv(OUT_CSV, index=False)  # choice rules: common.py
    print(f"Wrote {len(df)} rows to {rel(OUT_CSV)}")
    print(f"Credits: {df['credits_min'].sum()}-{df['credits_max'].sum()} (UC states {stated[0]}-{stated[1]})")

    diffs = compare_sections(df, sec2)
    print("Section II cross-check:", "same courses and slots" if not diffs else "")
    for d in diffs:
        print("  ", d)

    failures = check(df, stated, bundles)
    if failures:
        raise SystemExit("CHECKS FAILED:\n  " + "\n  ".join(failures))
    print("All step 3 checks passed.")


# Run main() only when executed as a script, not when imported.
if __name__ == "__main__":
    main()
