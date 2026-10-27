# 08 — Concepts

A table of the **concepts** (topics and practices) that schools' required CS courses
say they teach, so the committee can see which concepts UC's required courses cover
compared with the other fifteen schools, and what share of schools cover each one.
Decisions below were made with the user on 2026-10-17 (after step 13).

Canonical courses (`04-outputs.md`) answer "does this school have a Data Structures
course?". Concepts answer a finer question: "does any required course at this school
mention hash tables?". A concept can be spread across courses that match different
canonical courses at different schools (e.g. recursion in intro programming at one
school, in data structures at another).

## Scope

- **CS courses only** (the user's choice): named rows whose `subject_area` is `cs`
  (step 14). Math, science, writing, engineering, and gen-ed courses are not tagged.
- **Named courses with official descriptions only.** Generic descriptions were written
  for this project, not by the school, so they are not evidence of what a school
  teaches. Such rows are listed as "not assessed" and do not count as covering
  anything.
- **Slots are not tagged.** An elective slot ("CS elective") has no fixed content, and a
  choice slot's options have no descriptions of their own in our data. Both are listed
  as "not assessed".
- All sixteen schools are tagged. UC is reported separately from the fifteen comparison
  schools, which form the denominator of every percentage.

## What "covers" means here

A school **covers** a concept when at least one of its in-scope required rows has an
approved tag for that concept. The evidence is the catalog description (and title), so
pages say **"mentioned in a required course's description"**, never "taught". Catalog
descriptions are short (median 38 words across the sixteen schools), so a concept that
isn't mentioned may still be taught. Every page that shows concept coverage says this.

## Step A: Concept vocabulary (bottom-up)

The vocabulary comes from the descriptions themselves, with no outside framework (the
user's choice; ACM/IEEE CS2023 is not used for the list or its grouping).

1. Read every in-scope description and list candidate concepts with the phrases that
   state them.
2. Merge candidates that name the same idea into one concept, recording the variants as
   synonyms ("hash tables; hashing; hash maps").
3. **Granularity.** A concept is a topic or practice a course could spend about a week or
   more on: "hash tables", "recursion", "process scheduling", "TCP/IP", "unit testing",
   "team projects". Two kinds of phrase are not concepts:
   - whole-course labels that are already canonical courses ("data structures",
     "operating systems"); their content is what gets tagged,
   - generic aims with no topic ("problem solving", "critical thinking"), unless a
     description makes them a concrete practice.
4. **Groups.** Concepts are then grouped into areas named for this project (e.g.
   "Algorithms", "Systems", "Software practice"), formed from the concepts themselves.
   A concept belongs to exactly one group.
5. The user reviews the vocabulary and groups **before any tagging**.

### `data/reference/concepts.csv`

Hand-reviewed; never overwritten silently.

| Column | Example | Notes |
|---|---|---|
| `concept_id` | `hash-tables` | Stable, readable slug; never reused or renamed |
| `name` | `Hash tables` | |
| `group` | `Data structures` | Project-defined group (step A.4) |
| `definition` | `Storing and finding keys by hashing them into an array of buckets...` | One or two sentences, written for this project |
| `synonyms` | `hash tables; hashing; hash maps` | "; "-separated phrases seen in descriptions; helps tagging and review |
| `first_seen` | `University of Cincinnati / CS 2028C` | Which description first named it |
| `notes` | | |

## Step B: Tag each course

Claude proposes tags; the user reviews them (the user's choice), as with course matches.

- One line per (row, concept). A row usually has several tags.
- **Every tag carries evidence phrases copied word for word** from the row's title or
  description: **every** phrase in that field that states the concept, not just one
  (revised 2026-10-19 with the user: CS 1800's "sets, tuples, sequences" and "basic logic"
  were tagged but looked missed, because only one phrase per tag was recorded). The
  checker verifies that each phrase occurs there, so every tag traces to the source text.
- Tag only what the text states. Don't infer topics from the course's title alone when
  the title is a whole-course label ("Operating Systems" alone does not tag
  `process-scheduling`); the title is evidence only for a concept it names directly.
- If a row has no taggable concept, it gets one line with `concept_id` empty and a note
  saying why, so every in-scope row is accounted for.

### `data/reference/<school>/concept_tags.csv`

| Column | Example | Notes |
|---|---|---|
| `match_key` | `CS 2028C` | Course code, as in `matches.csv` |
| `concept_id` | `hash-tables` | Link to `concepts.csv`; empty only for a "no concept" line |
| `evidence_field` | `description` | `description` or `title` |
| `evidence` | `hash tables \| hashing` | Exact phrases from that field (case and whitespace may differ), separated by ` \| ` (no in-scope text contains `\|`); the first is the one the tag was proposed with |
| `tag_confidence` | `high` | `high`, `medium`, `low` |
| `tag_status` | `proposed` | `proposed`, `approved`, `rejected` |
| `notes` | | |

### `src/check_concepts.py --school <id>`

Validates without writing, like `check_canonical.py`:

- every `concept_id` exists in `concepts.csv`, and every concept is used at least once,
- every `match_key` is an in-scope row of the school (CS, named, official description),
- every in-scope row has at least one line,
- every evidence phrase occurs in its field (after lowercasing and collapsing
  whitespace), and no phrase is listed twice in one tag,
- no duplicate (row, concept) lines.

### Untagged text (added 2026-10-19, the user's choice)

To catch missed concepts, every piece of in-scope description text is accounted for:
either it is inside an evidence phrase, or it is listed with a reason in
`data/reference/<school>/untagged_notes.csv`. Leftover text is the review queue.

`src/check_untagged.py [--school <id>] [--strict]` finds leftovers: it marks every
occurrence (whole words, case-insensitive) of every description evidence phrase and
every note phrase, cuts the rest at punctuation, trims filler words (articles,
prepositions, catalog verbs like "introduces"), and prints what remains. It fails on a
malformed note (unknown row or reason, phrase not in the description, duplicate);
leftovers fail only with `--strict`. Read-only, like `check_concepts.py`.

| Column | Example | Notes |
|---|---|---|
| `match_key` | `CS 3000` | Course code |
| `phrase` | `optimization techniques` | Exact text from the description (may include punctuation) |
| `reason` | `no-concept` | See below |
| `notes` | `Could mean greedy algorithms, dynamic programming, or linear programming...` | Why, when the reason alone doesn't say |

Reasons, each tied to a rule above:

- `course-label`: names the whole course or a canonical course ("data structures").
- `framing`: about the course itself: audience, format, companion labs, aims, credit rules.
- `generic-aim`: an aim with no topic ("problem solving").
- `prerequisite`: what students must already know.
- `too-general`: names an area too broadly to pick one concept ("structures", "memory").
- `no-concept`: a concrete topic the vocabulary lacks. These are the candidates for new
  concepts; the review page can list just the courses that have them.

The rules are unchanged: whole-course labels and generic aims are still not concepts,
and the title is still not evidence for topics it doesn't name.

## Step C: Coverage table

`src/build_concepts.py` (all schools at once) writes:

- `data/processed/all_concept_tags.csv` / `.json`: one line per non-rejected tag, joined
  with its row (school, code, title, `norm_semester`, description) and concept (name,
  group).
- `data/processed/concept_coverage.csv` / `.json`: one line per concept.

| Column | Example | Notes |
|---|---|---|
| `concept_id`, `name`, `group` | `hash-tables`, `Hash tables`, `Data structures` | From `concepts.csv` |
| `n_schools` | `11` | Comparison schools (UC excluded) that cover it |
| `n_comparison` | `15` | Comparison schools in the table |
| `pct_schools` | `73.3` | `n_schools / n_comparison`, one decimal |
| `uc_covers` | `true` | |
| `uc_courses` | `CS 2028C` | UC rows tagged with it, "; "-separated |
| `uc_first_semester` | `3` | Earliest normalized semester at UC; empty if not covered |
| `median_first_semester` | `3` | Median over comparison schools of each school's earliest semester |
| `schools` | `osu; uic; ...` | Comparison schools that cover it |
| `tag_status` | `approved` | Least-reviewed status among the tags counted |

- Coverage counts tags that are not rejected. While any counted tag is still
  `proposed`, the views label the numbers "includes proposed tags".
- The table stores counts only. "Common elsewhere but not at UC" and "distinctive to
  UC" are thresholds the reader sets in the view, not values written into the data.
- `data/processed/concepts.json`: a copy of `concepts.csv` for the web views.

## Step D: Views

- **Coverage chart**, a new page `web/concepts.html` + `concepts.js`: one row per concept,
  grouped by `group`, with a bar for `pct_schools` and a marker for UC (filled: covered,
  hollow: not). Sort by percentage or by group; filter by group. Two lists under the
  chart, driven by threshold sliders:
  - concepts that at least *X*% of comparison schools cover but UC doesn't (default 50%),
  - concepts UC covers that at most *Y*% of comparison schools cover (default 20%).
  Hover a concept to see which schools cover it, through which courses, with the
  evidence phrase highlighted in each description.
- **Timeline concept mode**: the timeline view (`07-timeline-view.md`) gains a toggle
  that draws one strip per concept instead of per canonical course.
- Both pages show the coverage caveat ("mentioned in a description") and list the rows
  that were not assessed (generic descriptions, slots).

## Out of scope (for now)

- Syllabi, learning outcomes, or course web pages as evidence.
- Concepts in non-CS courses.
- Weighting a concept by how much of a course it fills.

## Checks

- Step A: the user reviews `concepts.csv` (names, definitions, groups, granularity).
- Step B: `check_concepts.py` passes for every school; the user reviews the proposed
  tags on a review page (one school at a time, evidence highlighted), as with matches.
- Step C: spot-check a few coverage lines against the tags by hand.
- Step D: the user opens both views in a browser.
