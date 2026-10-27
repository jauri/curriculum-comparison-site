# 09 — Process View

A web page that shows, for a committee of other faculty, **how this project was made**:
the user's requests and decisions, Claude's responses, and the work Claude did in
between, as one timeline read from top to bottom. Decisions below were made with the
user on 2026-10-18 (step 21). Approved by the user on 2026-10-18; built the same day.

## Purpose

Let a faculty reader see:

- what the user asked for and decided, and when,
- how Claude responded (proposals, questions, results),
- what Claude actually did between messages (fetching catalogs, writing scripts,
  running checks, committing),
- how the work moved through the plan's steps, including the review checks where the
  user approved or changed Claude's work.

## Source

- Claude Code's session logs for this project (JSON Lines, one file per session, in
  `~/.claude/projects/<project>/`). They hold every message and action with a timestamp.
  14 sessions, 2026-10-16 to 2026-10-18, at the time of writing.
- `src/collect_process.py` copies them to `data/raw/process/` (never edited, as with
  other raw sources). The copies are git-ignored: they hold full tool outputs, so they
  stay on the Mac; only the processed timeline is ever published.
- `src/parse_transcripts.py` reads them and writes
  `data/processed/process/timeline.json`.

## What is extracted

Three kinds of entries, each with a timestamp, a session number, and its text:

- **You** (the user): every message typed to Claude. Left out: slash commands such as
  `/clear`, system-inserted text (reminders, file contents attached by the tool), and
  tool results.
- **Claude**: every text reply shown to the user. Claude's private reasoning is not
  shown. A multiple-choice question (Claude's question tool) appears as a Claude entry
  listing the question and options, and the user's choice appears as a **You** entry.
  A form with several questions is split and interleaved (the user's request, after the
  first build): one Claude card per question ("Claude asks (2 of 4)"), each followed
  directly by the user's answer to it.
- **Actions**: all of Claude's tool calls between two of the user's messages, grouped
  into **one summary card per turn** (the user's choice). The card shows a count and a
  one-line summary written by rule from the calls (e.g. "Read 4 files, edited
  parse_michigan.py, ran validate.py"), and expands to the full list of calls (tool,
  file or command, short description). Tool outputs are not shown.

Text is kept **verbatim**. Absolute paths under the home directory are shortened to
project-relative paths. The email address and any credentials are removed by rule.

## Curation

- `data/reference/process/curation.csv` (hand-reviewed, never overwritten silently):
  one row per entry the user wants to change, with `entry_id`, `action`
  (`hide`, `note`), and `text` (a note shown beside the entry, e.g. explaining a
  decision to the committee).
- **Step markers** come from `data/reference/process/steps.csv`: a row per plan step.
  By rule a marker goes before the user's first message after the commit that closed
  the previous step (`after_commit`); where that lands wrong, `before_entry` names the
  entry to put it before. Claude proposes them (`status = proposed`); the user reviews.
- **Commit markers** are added for every git commit, at its commit time.
- Before the page is published, the user reads through it and hides anything not to be
  shared (the user's choice: public only after review). Until then `publish_site.sh`
  leaves the page and its data off the public site unless `PUBLISH_PROCESS=1` is set.

## Layout

- New page `web/process.html` + `web/process.js`, with a **"Process"** tab added to the
  nav on every page.
- **A vertical line down the center.** The user's entries sit on the left, and Claude's
  responses and action cards on the right, each joined to the line by a short connector
  with a dot.
- **Ordered spacing** (the user's choice): entries are evenly spaced in time order, not
  scaled to clock time. Each entry shows its time (e.g. "10:42").
- **Dividers** across the full width: a session divider ("Oct 17 · Session 6") at each
  new session, and a step marker ("Step 13: Remaining schools") where a plan step
  begins.
- **Collapsed by default, expandable** (the user's choice): each message shows its first
  few lines, with a control to expand to the full text and collapse it again. Action
  cards show the summary line and expand to the list of calls.
- The user is labeled **Author** on the page (the committee reads it in the third
  person).
- **Three colors**, one per kind (Author, Claude, Actions), with a legend at the top. Action
  cards are visually lighter than messages, since they are the supporting detail.
- A short introduction at the top explains how the project was done and how to read
  the page, with counts (sessions, messages, actions).
- At phone width the two sides collapse into one column, with the kind shown by color
  and a label on each entry.

## Minimizing sections (added 2026-10-20)

At the user's request, each section (Who did what, When the work happened, What the
author's messages did, How many tokens Claude used, Complete interaction log) can be
minimized to its heading and maximized again: click the heading (a button with a
chevron and "Minimize" / "Maximize"). "Minimize all sections" and "Maximize all
sections" sit under the subtitle. Which sections are minimized is remembered in the
viewer's browser *(default)*. Links and bar clicks that scroll into the log open it first.

## Who did what (added 2026-10-20)

At the user's request, a section directly under the page title states each side's role,
as a course project's contribution statement would: **the author** (the question and
scope, ground rules, the comparison set, method decisions, proposing views and choosing
among designs, reviews and approvals, corrections, directing the work) and **Claude**
(specs and plan, finding and collecting sources, all code, drafted judgment calls for
review, smaller choices logged for review, checks, the record). Two cards side by side in
the Author and Claude colors, one column on phones. The text is hand-written from
`PROGRESS.md` and the specs and says so; a count line under each card comes from
`timeline.json` (the author's messages and answer classes; Claude's replies, questions,
actions, and commits).

## Activity overview

Added at the user's request (2026-10-18): a high-level picture of when and how much the
work happened, directly under the page title.

- **One block per day** (every calendar day from the first session to the last, U.S.
  Eastern, so days off show as empty rows), **two lanes** per day: Author (orange) and
  Claude (blue). Hours run left to right in **half-hour cells** (the user's choice over
  a single continuous strip, dots per message, or mirrored bars).
- **Activity** (the user's choice): the Author lane counts the author's entries
  (messages, answers, declined questions, interruptions); the Claude lane counts its
  replies and questions plus **each tool call, at the call's own time**.
- Shading: four steps of the lane's color, level = ceil(4 × sqrt(n / lane max)). Each
  lane has its own scale, since tool calls far outnumber messages; the caption says so.
- **Toggle: amount vs. minutes** (the user's request). "Minutes of activity" splits time
  into turns: the gap between two consecutive events belongs to whoever produced the
  later one (a gap ending in the author's message or answer was the author reading,
  thinking, and typing; one ending in a Claude reply or tool call was Claude working).
  Each gap counts in full up to **5 minutes**, as 5 from 5 to **20 minutes**, and
  beyond 20 as a break: **2 minutes** for the author (reading the reply and typing after
  coming back; about their typical reply time) and **0** for Claude (a long Claude gap
  is a permission prompt waiting on the author). The user's choice, after a 10- and then
  a plain 5-minute cap. Of the author's 111 message gaps, 92 were ≤ 5 min, 14 were
  5–20, and 9 were over 20; none fell between 16 and 23, so 20 is a natural cut.
  Minutes are spread over the half hours a gap spans. Answers use their real time, not
  their question's. Both lanes share one scale, level = ceil(4 × minutes / 30). Known
  limits: thinking past the cap and reviewing away from the keyboard aren't seen.
- Hovering a cell with activity shows a **tooltip** with its time and both lanes'
  values (the user's request, replacing a line under the grid). A click or tap pins it
  and adds a link that jumps to the first entry in that half hour; clicking elsewhere or
  Escape closes it. The caption ends with the project total for the current measure
  (half hours with any activity, or each side's hours), and the color key sits on its
  own line below the caption. A rule separates the overview from the content below.
- The bins are computed in `parse_transcripts.py` (`activity` in `timeline.json`); the
  page only shades them.

## Kinds of input (proposed, 2026-10-18)

What each of the author's messages does, shown as a **per-step summary** on the process
page. First proposed as a 1-5 scale from "open" to "exact"; the user replaced it with
categories, since a scale implies precise is better and would mark down clarifying
questions and exploration, which are a normal part of the work.

**Typed messages** get a hand-reviewed category in
`data/reference/process/input_kinds.csv` (`entry_id`, `primary`, `secondary`, `status`,
and `excerpt`, the message's first words, for reading the file),
`secondary` optional, for a message that does two things (only `primary` is counted):

| Category | What it is | Example |
|---|---|---|
| Specification | What to build or change, and how | "on hover… show the school and the course… in a tooltip" |
| Correction | Something Claude did is wrong or should be undone (asking to refine work that is right is Specification) | "something is wrong with the matching approach"; "put the line back" |
| Clarification | Asking for a fact or an explanation | "is pandas installed" |
| Exploration | Asking for options or Claude's suggestion | "how would you measure my minutes of activity?" |
| Decision | Approving or choosing at a review point | "i approve"; "we can have one parser for each school" |
| Workflow | Moving the process along | "commit", "what's next", "prepare for clear" |
| Working style | How Claude should work with the author | "ask questions using AskUser" |

Claude proposes every row (`status = proposed`); the user reviews and corrects. A
message is classified by what it mainly asks for; asking for suggestions is the
primary category only when that is the main request ("add 2 more schools… any
suggestions?" is Exploration; "differentiate each year… maybe font size or a better
divider?" is Specification, with Exploration as its secondary).

**Answers to Claude's questions** are all Decisions, classified further by rule from the
logs: took Claude's recommended option, chose another option, wrote their own answer,
or chose where Claude made no recommendation (at the time of writing: 75, 8, 4, 14).

**Display** (the user's choices: totals plus per step, and tags on the cards), a
section "What the author's messages did" under the activity overview:

- **Totals:** a horizontal bar per category, longest first, with its count; a sentence
  below gives the answers to Claude's questions by class.
- **By plan step:** one stacked bar per step marker, segments in the fixed category
  order, all on one scale (the busiest step is full width), so steps compare by volume
  and mix. Hover shows a tooltip with the count.
- **Colors** (revised at the user's request: the first set had two greens): blue
  Specification, yellow Exploration, magenta Clarification, green Decision, red
  Correction, and two grays for the process kinds, dark Working style and light
  Workflow. Blue is also Claude's color in the overview; the user asked for it, and
  labels keep them apart. Violet was dropped (nearly indistinguishable from blue under
  color blindness). The hues pass the colorblind validator's neighbor checks in both
  modes; red and magenta are the weakest pair and still meet in two steps' bars, where
  the 2px gaps and tooltips tell them apart.
- **Tags:** each author card's head shows its main kind as a chip, and a fainter chip
  for a second kind; answers show "Decision · took Claude's recommendation" etc.
- **Filter:** a "Show" menu in the controls (also set by clicking a bar) shows only the
  author's messages of one kind, or only the answers, keeping the step markers above
  them and hiding steps with none.
- The note under the chart says whether the categories are still Claude's proposal
  (from the `status` column) and how many recent messages are unclassified.

The parser adds the categories, answer classes, and per-step counts to `timeline.json`
(`inputs`); the page only lays them out.

## Token usage (added 2026-10-18)

The user asked how many tokens the project used, over time. A section "How many tokens
Claude used" under the kinds of input, with **one stacked bar per plan step** (the
user's choice over a cumulative line by date or a count on each card).

- **Source:** the `usage` record on each Claude reply in the session logs. One reply is
  stored as several log lines that repeat it, so replies are counted once, by message
  id; Claude Code's `<synthetic>` placeholder replies are skipped. A reply counts toward
  the last step marker at or before its time.
- **Parts:** *Written by Claude* (output tokens: text, tool calls, private reasoning),
  *Context added* (uncached input plus cache writes), and *Context re-read* (cache
  reads). Colors: Claude's blue, a light mix of it, and neutral gray.
- **Toggle:** re-read context is over 95% of all tokens, so it is left out by default
  and added by "Including re-read context". Bars share one scale per mode.
- A tooltip gives every part and the step's reply count; a note gives the totals.
- No cost estimate: the logs hold counts, not prices.
- The parser writes `tokens` in `timeline.json`; the page only lays it out.

## Out of scope

- Claude's private reasoning and tool outputs.
- Sessions in other projects.
- Scaling the timeline to real elapsed time (considered and declined).

## Done when

- The extracted entry counts match the session logs (checked by `src/validate_process.py`
  or a check in the parser: every user message and Claude reply accounted for, every
  tool call in exactly one action card).
- The user has reviewed the page in a browser, set the curation rows, and approved
  publishing it.
