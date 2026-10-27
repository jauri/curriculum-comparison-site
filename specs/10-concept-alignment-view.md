# 10 — Concept Alignment View

A second alignment view. Like `06-alignment-view.md`, it lines up UC against one other
school, semester by semester. The difference is in the links: instead of "these two rows
share a canonical course", a band says "this share of this course's concepts is
found in that course". Drafted with the user on 2026-10-18; built the same day at the user's
go-ahead ("try it even with the issues").

## Purpose

The Alignment tab says *whether* two courses correspond. This view says *how much*:
UC's Data Structures may match OSU's at the canonical level but share only some of
the concepts named in their descriptions, while a UC course with no canonical
counterpart may still share concepts with several of the other school's courses.

## Page

- New page `web/concept_compare.html` + `concept_compare.js`, nav label
  **"Concept alignment"**, placed right after "Alignment" in every page's nav.
- Same frame as the Alignment tab: UC on the left axis, one comparison school on the
  right (same picker), 8 semester bands lined up across both sides, the same subject-area
  checkboxes, and the same ordering heuristic (barycenter), with band weights in place
  of link counts.
- The text helpers both pages need (`fitSvgText`, `rowLabel`, `semText`) moved into
  `web/common.js`. Layout (semester bands, placement, ordering) stays per page: the
  ordering here weights each partner by its share, so it differs from compare.js.
- The same **"Show co-op terms"** toggle as the Alignment tab (`06-alignment-view.md`,
  "Co-op terms"). Co-op terms have no tags, so turning it on changes no share; their
  boxes are drawn in the co-op color, not as "not assessed".
- Each node has a narrow **share bar** on its inner edge (facing the bands) and its area
  stripe on the outer edge.

## Nodes

- **Height = credits**, the same scale as the Alignment tab (the user's choice). A
  course with more concepts is not drawn taller: the number of tags mostly shows how
  long the description is, not how big the course is.
- **Tagged rows** (CS, named, official description, at least one tag that is not
  rejected) are drawn in their subject color, with one segment per band (see below) and
  an **unshared** segment at the bottom (hatched, labeled "n% not found at <school>").
- **Untagged rows** (non-CS courses, slots, generic descriptions, and CS rows whose only
  line is "no concept") are drawn in gray with no bands and labeled "not assessed"
  (the user's choice), so the layout matches the Alignment tab. Non-CS areas are
  **off by default** here (the checkboxes can turn them on).

## Bands: what share of a course goes where

For a UC course *u* with concept set *C(u)*, and a course *v* at the comparison school *S*:

- Each concept is **1 / |C(u)|** of *u*.
- A concept of *u* found in *k* of *S*'s courses is split **evenly among those k
  courses** (the user's choice): each gets 1 / (|C(u)| · k).
- **share(u → v)** = sum over the concepts *u* and *v* share of 1 / (|C(u)| · k_S(c)).
- **unshared(u)** = 1 − sum over *v* of share(u → v) = the fraction of *u*'s concepts
  found in none of *S*'s courses.

The other school's side uses the same rule the other way round (with k counted
over UC's courses). The shares of one course always add up to 100% with its unshared
part, so no concept is counted twice.

Example: UC course with concepts {a, b, c, d}; OSU X has a and b, OSU Y has b.
a → X 25%; b → X 12.5% and Y 12.5%; c, d unshared 50%. So X gets 37.5%, Y 12.5%.

### Drawing

- **Tapered bands** (the user's choice): a band is a filled shape from a segment of
  *u*'s right edge to a segment of *v*'s left edge. The UC end is
  share(u → v) × height(u); the other end is share(v → u) × height(v). The two ends
  usually differ, and each one is honest about its own course.
- Within a node, band segments are stacked in the vertical order of their other ends
  (fewer crossings); the unshared segment sits last.
- Bands under 1.5 px are drawn at 1.5 px so they stay visible; the tooltip gives the
  real numbers.
- Color: one neutral band color with partial opacity, so overlapping bands stay
  readable. (All tagged rows are CS, so the subject color would make every band
  the same anyway.)

## Concept filters

- **Concept-group checkboxes** (the 16 groups in `concepts.csv`), all on by default.
  Turning a group off removes its concepts from every course before the shares are
  computed, so the percentages are always over the concepts shown. This matters
  because some groups (e.g. "Languages used", career and orientation concepts)
  link courses that are otherwise unrelated.
- A **minimum-share slider** (0–50%, default 0%) hides bands whose larger end is below a
  threshold, to cut clutter. The share bars keep their full split.

## Interaction

Same as the Alignment tab, with concept detail:

- **Hover a band:** a short tooltip with both percentages (e.g. "37.5% of the UC course ·
  20% of the OSU course"). The **side panel** shows the band in full (changed at the
  user's request, 2026-10-19, so the overlap is easier to read): both shares with "n of N
  concepts", the shared concepts numbered (name, group, and how each side's share was
  split), and both courses' titles and full descriptions with every evidence phrase of
  a shared concept highlighted and tagged with its number. A phrase nested in another
  highlight adds its number to that highlight. **Click a band** to pin it in the panel.
- **Hover or click a node:** a breakdown of every concept in the course: where it
  went (which partner courses, what share) or "not found at <school>".
- Untagged nodes say why they were not assessed (non-CS, generic description, slot).

## Data

- The page reads `data/processed/all_concept_tags.json` and `concepts.json`, which step
  18's `build_concepts.py` writes (`08-concepts.md`, step C). That part of step 18 is
  built first; the coverage table can follow later.
- Shares are computed in the browser from the tags using the written rule above, the way
  the Alignment tab joins on `canonical_id`. The accessible table under the view
  lists every band (UC row, other row, shared concepts, both shares) so any number
  can be checked against the tags by hand.
- Tags are still `proposed` (step 17's review is deferred), so the page says "includes
  proposed tags" until they are all approved, with the coverage caveat from
  `08-concepts.md` ("mentioned in a description", not "taught").

## Known problems with the idea

1. **Most of each course will be unshared.** On average only 26% of a UC course's
   concepts appear anywhere at OSU (UIC 42%, CMU 28%, Berkeley 24%, Georgia Tech 5%).
   The hatched "unshared" segments will dominate. That is a real finding, but it is
   about the descriptions as much as the courses.
2. **The data are sparse for some schools.** Georgia Tech has 5 tagged CS courses and
   Berkeley 2 (short or generic descriptions). A thin view there means little evidence,
   not little overlap. The picker shows each school's tagged-course count, and the
   page warns when it is low.
3. **Short descriptions give coarse percentages.** A course with 1 tag is 0% or 100%. A
   course with 9 tags moves in steps of 11%. The tooltip shows "2 of 9 concepts" next to
   every percentage.
4. **A band can be wide at one end and thin at the other.** That is intended (tapered
   ends), but readers may need the legend's one-line explanation.
5. **Weak concepts link unrelated courses.** Career preparation, orientation, or a
   language name can join two courses that share nothing else. The group filter is the
   remedy; reviewing the step 17 tags is the real fix.
6. **Unreviewed tags.** Everything here rests on proposed tags. Recommend doing the
   step 17 review before showing this view to the committee.

## Out of scope (for now)

- More than two schools at once.
- Weighting a concept by how much of a course it fills (`08-concepts.md`).
- Drawing canonical links (Alignment tab) and concept bands on the same view.

## Check

The user opens the page, compares UC with OSU, UIC, and Georgia Tech, checks a few band
percentages against the table and the tags, and tries hover, click, the group filter,
and the slider. Also: no horizontal page scroll at phone width, light and dark mode.
