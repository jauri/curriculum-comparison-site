# 05 — Comparison Set

## Audience and purpose

- **UC curriculum committee:** evidence for how UC's required CS courses compare with
  in-state peers and top programs.
- **The user's own understanding** of where UC's curriculum is typical, ahead, or behind.

## Selection rules

- **Semester-system schools only**, so the 4-year / 8-semester normalization applies
  directly. No quarter-system schools.
- **Two groups:** Ohio public peers and aspirational top programs.
- **No co-op peer group.** (A school with *optional* co-op is fine; we use its standard
  4-year plan.)
- **Start with 15 schools** and expand once the pipeline works.
- **Prefer CS degrees in engineering.** Where a school offers more than one CS degree, use
  the one housed in the engineering college. Where a school has only one CS BS, include it
  whatever college it is in, and record the college in the table.
- Use the same catalog year as UC (2026–27) where available.
- **Start from no programming experience** (added 2026-11-14): the views show the plan
  for a student entering with no prior programming, who starts from an intro course. A
  school whose only plan assumes an intro programming course before the first semester
  is kept in the data but hidden from the views (`displayed = false` in schools.csv).
  Hidden so far: CMU (assumes 15-112) and Pitt (assumes intro programming before CMPINF
  0401). Where a school offers several plans, use the one for no prior experience (USC:
  "Begin with CSCI 102").

## Initial set (15)

College placements below are from memory and **must be verified** during collection.

| Group | School | Degree to use | College (to verify) | Engineering? |
|---|---|---|---|---|
| Ohio public | Ohio State University | BS in Computer Science & Engineering | College of Engineering | Yes |
| Aspirational | University of Illinois Urbana-Champaign | BS in Computer Science | Grainger College of Engineering | Yes |
| Aspirational | University of Illinois Chicago | BS in Computer Science | College of Engineering | Yes |
| Aspirational | University of Michigan | BSE in Computer Science | College of Engineering | Yes |
| Aspirational | University of Minnesota | BS in Computer Science | College of Science & Engineering | Yes |
| Aspirational | University of Wisconsin–Madison | BS in Computer Sciences | College of Letters & Science | **No?** |
| Aspirational | Carnegie Mellon University | BS in Computer Science | School of Computer Science | **No?** |
| Aspirational | Purdue University | BS in Computer Science | College of Science | **No?** |
| Aspirational | Georgia Tech | BS in Computer Science | College of Computing | **No?** |
| Aspirational | Virginia Tech | BS in Computer Science | College of Engineering | Yes |
| Aspirational | Penn State (University Park) | BS in Computer Science | College of Engineering | Yes |
| Aspirational | Texas A&M University | BS in Computer Science | College of Engineering | Yes |
| Aspirational | Northeastern University | BS in Computer Science (BSCS) | Khoury College of Computer Sciences | **No?** |
| Aspirational | UC Berkeley | BS in Electrical Engineering and Computer Sciences (EECS) | College of Engineering | Yes |
| Aspirational | University of Texas at Austin | BS in Computer Science | College of Natural Sciences | **No?** |

**Alternates** for expansion or swaps: University of Toledo, Bowling Green State,
University of Akron, Cleveland State (Ohio); Ohio University, Miami University (Ohio, swapped out); Kent State, Wright State (Ohio, swapped out); Maryland (swapped out, no semester plan); University of Kentucky (regional public).

## Programs with tracks or concentrations

Some programs (Purdue tracks, Georgia Tech Threads) don't have one fixed list of required
courses. **Decided:** record the **common core** as `required`, and record everything
else (track or thread requirements) as `elective_slot` rows that describe the choice.

## Changes to the set

- **2026-10-17 (step 13):** Ohio University and Miami University were swapped out for
  Maryland and UT Austin, at the user's request. Neither publishes a semester-by-semester
  plan for its CS BS (Ohio U's 2026-27 catalog lists requirements only; Miami's sample
  plans are for the BA). The Ohio public group is now OSU, Kent State, and Wright State.
- **2026-10-17 (step 13):** Maryland was then swapped for Texas A&M. Maryland's CS
  department publishes only requirement tracking sheets, no semester plan; Texas A&M's
  2026-27 catalog has a plan-of-study grid and the degree is in Engineering.
- **2026-10-17 (step 13):** Kent State and Wright State were swapped out for Northeastern
  and UC Berkeley, at the user's request. The Ohio public
  group is now OSU only. Northeastern is a co-op school, an exception to the "no co-op
  peer" rule made by the user. Its 2026-27 catalog has no plan of study, so the archived
  2025-26 "Four Years, Two Co-ops" sample is used and normalized to 8 semesters like UC's.
  UC San Diego was considered and rejected because it is on quarters. Berkeley has two CS
  degrees, so the engineering rule picks the EECS BS over the L&S CS BA.

- **2026-11-13 (batch 4, expansion beyond 15):** the user chose 10 more **top public
  universities with CS in a college of engineering**, all in the Aspirational group: UVA,
  Florida, Colorado Boulder, Utah, Stony Brook, Buffalo, UT Dallas, UConn, Tennessee
  (Knoxville), and Kentucky. NC State, Michigan State, and Arizona State were proposed and
  dropped by the user; Clemson, Delaware, and George Mason are backups. Strong publics left
  out: quarter calendars (Washington, UCLA, UC San Diego, UC Irvine, UC Davis, UC Santa
  Barbara) and CS outside engineering (Maryland, UMass Amherst, UNC, Rutgers, Pitt,
  Indiana, Arizona). Utah was first thought to have no 2026-27 semester plan, and its
  2024-25 plan was chosen; the 2026-27 catalog's "Computer Science Sample 4 Year Plan"
  was then found and the user switched to it.
  UVA's 2026-27 Record lists requirements only, so the CS advising site's 2024-25 example
  semester outline is used, also at the user's request.
  Florida was then removed by the user: its plan places courses in two required summer
  terms (10 terms, not 8). The batch is now 9 schools, all built by 2026-11-14 (matches
  proposed, concept tags not yet written).

- **2026-11-14 (batch 5):** from a top-100 list (U.S. News bands, approximate), the user
  chose ten: UNC, Indiana, Arizona, Case Western, USC, NYU, UMass Amherst, Boston
  University, Vanderbilt, and Pitt (all semester calendars, Aspirational group; the
  group is no longer only publics or engineering colleges). Plan check: **Indiana, UMass
  Amherst, and BU publish no semester-by-semester CS plan** (requirements only), and
  **Arizona's only plan is from Fall 2021**; the user dropped all four (Maryland's rule).
  Batch 5 is six schools: UNC (BS, College of Arts & Sciences), Case Western (BS, Case
  School of Engineering), USC (BS, Viterbi), NYU (Tandon BS, chosen over the CAS BA by the
  engineering rule), Vanderbilt (BS, School of Engineering; 2025-26 roadmap, no 2026-27
  version posted), and Pitt (BS, School of Computing and Information).

## Open questions

- [x] Track/thread handling: common core = required, rest = electives.
- [x] Engineering rule: prefer the engineering degree; if a school has only one CS BS,
      keep it and record its college (rows marked **No?** stay in the set).
