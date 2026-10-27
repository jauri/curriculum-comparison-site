# 03 — Processing

## Step 1: Parse the plan of study

Turn the raw UC plan of study into one row per course or requirement slot, keeping UC's
original placement (e.g., "Year 3, Spring semester").

## Step 2: Normalize the 5-year co-op timeline to 4 years

UC's plan alternates academic semesters with co-op semesters. To compare with 4-year
programs, we map each course to an **academic-semester index** that ignores co-op terms.

**Rule (decided):**

1. List all UC terms in chronological order and mark each as `academic` or `coop`.
2. Remove co-op terms. Co-op / professional development courses stay in the table but are
   flagged (`is_coop = true`) and have no normalized placement.
3. Shift the remaining academic terms, including any academic summer terms, into one
   consecutive sequence of regular semesters: academic term k → normalized semester k.
   A summer academic term becomes the next regular semester in sequence.
4. The result should be a 4-year, 8-semester program: normalized year = ceil(k / 2), and
   Fall/Spring are assigned by position (odd = Fall, even = Spring).
5. If the result is not exactly 8 academic terms, stop and review it with the user rather
   than forcing a fit.
6. **Half-terms (decided in step 13, for Northeastern).** A school that splits summer
   into two half-terms ("Summer 1", "Summer 2") counts each academic half-term as half a
   semester. Academic half-terms are paired in chronological order, skipping full terms
   and co-op terms in between, and each pair becomes one normalized semester **in the
   place of its first half**. Example (Northeastern): Y1 Summer 1 + Y1 Summer 2 → one
   semester; Y2 Summer 2 + Y3 Summer 2 → one semester placed before Y3 Fall, which moves
   Y3 Summer 2's courses one term earlier. A half-term left without a partner is an
   error (stop and review). `academic_term_index` still counts every academic term
   (half-terms included), so it can differ from `norm_semester`.

Keep both the original and normalized placement in the table so the mapping is auditable.

## Step 3: Attach descriptions

For each course:

1. Look up the official UC catalog description. If found → `description_source = official`,
   store `description_url`.
2. Otherwise write a generic description → `description_source = generic`.
3. Elective or gen-ed slots get a generic description of the slot (e.g., "Student chooses
   an upper-level CS course from an approved list").
4. A named course whose school publishes no public official text (added in step 13 for
   Michigan, whose MATH, PHYS, and CHEM descriptions are in a login-only course guide)
   gets a generic description keyed by its course code in the school's
   `generic_descriptions.csv`, labeled `generic`. A course with official text always
   uses it.

## Step 4: Match courses to the canonical course list

Courses at different schools are matched through a shared list of **canonical courses**
(`data/reference/canonical_courses.csv`, schema in `04-outputs.md`). Each canonical course
has a stable ID and a generic description written for this project, not copied from any
one school.

For each course at a school, in order:

1. Compare it to the existing canonical courses using its title, description, credits,
   course level, and prerequisites.
2. If one fits, assign that `canonical_id`, with a confidence level (`high` / `medium` /
   `low`) and a one-sentence rationale.
3. If none fits, add a new canonical course (new ID and generic description) and assign it.
   Mark the match `new`.
4. Every match starts as `proposed`. The user reviews it and sets it to `approved` or
   `rejected`. Rejected matches are redone.

Rules:

- **Many-to-one is normal:** many schools' courses map to one canonical course.
- **Splits and merges:** if a course covers parts of two canonical courses (e.g., one
  school's 2-semester intro sequence vs. another's single course), assign the closest
  canonical course and set `partial_match = true` with a note. Don't create a canonical
  course for every combination.
- **Requirement slots** (e.g., "upper-level CS elective", "gen-ed humanities") get
  canonical slot entries too, so slots can be compared.
- **A row may match several canonical courses** (decided in step 13, replacing the
  one-concept-per-row rule). Each match has a **role**:
  - `covers`: the course teaches this concept, possibly alongside others (Northeastern's
    CS 3650 → `computer-organization` and `operating-systems`, each partial). A row with
    one ordinary match has one `covers` match.
  - `one_of`: a real choice. The student takes one option, so the row *may* be any of
    these concepts (OSU's CSE 32X1 → `software-engineering` or `databases`).
  - `all_of_group`: timing flexibility (see "Choice kinds" below). Every row of the
    group matches every option's concept, and the group as a whole requires all of them.
- **Choices** ("CSE 3231 or 3241") are one slot row with the option codes in `options`.
  If every option is the same course (UIC's CS 111/112/113, three versions of Program
  Design I; Berkeley's COMPSCI 61B/61BL), the row has one `covers` match to that course
  concept (decided in step 10). Otherwise each option's concept is a `one_of` match;
  this replaces `core-choice` for those rows (step 13). A slot concept is used only
  when the options are too many or too open to list (e.g. "any upper-level CS course").
- **Choice kinds** (decided in step 13). The parser sets `choice_kind` on every choice
  row from the school's own text, citing the sentence or footnote in `notes`:
  - `choose`: take one of the options (the default when the source says nothing more).
  - `all_in_any_order`: the options are all required, and the plan lists them as
    choices only so students can pick the order. Example: Berkeley's "ELENG 66 or
    ELENG 64" appears in both semester 4 and semester 5, and students take both. These
    rows share a `choice_group` id. Checks: every row in a group lists the same options,
    and the group has as many rows as options. When the same option set appears in more
    than one row without a stated reason, the parser stops and asks for review rather
    than guessing.
- **Credits are never counted twice.** A course's credits stay on its row. When credits
  are summarized by concept, an `all_of_group` group's total credits are split evenly
  across its concepts (Berkeley: 2 rows × 4 units → 4 units for each course, not 8).
- **A slot may match a course concept only by exception** (step 13, for the user's
  review): Michigan's "Approved CS Capstone course" is a required capstone chosen from a
  list the saved schedule doesn't include, so it matches `capstone-design`
  (`SLOT_MAY_FILL_COURSE` in `check_canonical.py`, the mirror of step 10's
  `COURSE_MAY_FILL_SLOT` for `lab-science`). Step 13 batch 3 adds Georgia Tech's Junior
  Design and VT's capstone slots under the same rule, and `first-year-seminar` for Penn
  State's "First-Year Seminar" slot (for the user's review).
- **A slot with a short list of one kind of option** (step 13 batch 3): when the source
  lists a slot's options and they are all one or a few course concepts (CMU's
  probability course, VT's statistics elective, Georgia Tech's ethics course), the
  parser puts them in `options`, so the slot matches those concepts (`covers` or
  `one_of`) like any choice row. Long or mixed lists stay in notes and the slot matches
  a slot concept.
- **UC is processed first**, so UC's courses seed the canonical list. Expect the list to
  be revised during the phase 2 pilot as other schools reveal better groupings.
- Credits are a matching signal (e.g., a 4-credit course with lab vs. a 3-credit lecture),
  but a mismatch in credits alone doesn't rule out a match.

## Units and fractional credits (step 13 batch 3)

- CMU counts **units** (hours of work per week; 360 for the degree), not credit hours.
  Credits are units / 3, rounded to 2 decimals (decided with the user), with the units
  kept in each row's notes.
- Credits may have a fractional part (CMU's 3.33; Penn State's 1.5-credit courses), so
  the credit-total check allows 0.05 of rounding.

## Step 5: Programs without a semester-by-semester plan

Use the school's official sample 4-year plan when one exists. If none exists, leave
`norm_semester` / `norm_year` blank and explain in `notes`. Don't infer typical semesters
from prerequisites: prerequisites only give a lower bound (a course can't come before its
prerequisites), not when students actually take it. A prerequisite-depth "earliest
possible semester" may be added later as a separate, clearly-named column.

## Plan conflicts and uncounted courses (decided in step 10)

- If a school's sample schedule disagrees with its own requirements list (a typo), the
  requirements list wins. The parser records each correction in the row's `notes`.
- A course that is in the plan but not in the stated total (placement-dependent or
  explicitly excluded) stays in the table with `counts_toward_total = false`.

## Validation checks

- Total credit hours of rows that count (`counts_toward_total`, not co-op) match the
  school's stated degree total (from `schools.csv`, checked by the parser against the source).
- Every row has a normalized placement unless it is flagged as co-op.
- Exactly 8 normalized semesters result after removing co-op terms.
- Every row has a non-empty description and a `description_source`.
- Every row has a `canonical_id` that exists in the canonical course list.
- No canonical course is unused, and no two canonical courses have the same name.
- Spot-check a handful of rows against the source by hand.

## Open questions

- [x] Normalization rule decided (above). Verify the 8-term result once UC data is parsed.
