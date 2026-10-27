"""Turn the Claude Code session logs into the process timeline (step 21).

Reads the copies in data/raw/process/ (made by collect_process.py) and writes
data/processed/process/timeline.json for web/process.html, following
specs/09-process-view.md:

- "you" entries: every message the user typed, plus their answers to Claude's
  multiple-choice questions;
- "claude" entries: every reply Claude showed the user (its private reasoning is not
  included), including those questions;
- "actions" entries: all of Claude's tool calls between two "you" entries, grouped into
  one card with a one-line summary written by rule;
- dividers: a "session" divider per log file, a "step" marker per plan step (from the
  hand-reviewed data/reference/process/steps.csv), and a "commit" marker per git commit.

Entries the user chose to hide or annotate are listed in
data/reference/process/curation.csv. Text is verbatim except for the redactions in
clean() (home-directory paths and the email address).

Usage:
    python src/parse_transcripts.py
"""

import json
import re
import subprocess
from bisect import bisect_right
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from common import ROOT

RAW_DIR = ROOT / "data" / "raw" / "process"
REF_DIR = ROOT / "data" / "reference" / "process"
OUT_DIR = ROOT / "data" / "processed" / "process"

# Times on the page are shown in the user's time zone (Cincinnati), whatever the
# viewer's, so "10:42 PM" means the same moment for every committee member.
TZ = ZoneInfo("America/New_York")

# Tools whose calls are not shown as actions: AskUserQuestion becomes a Claude entry
# (the question) and a You entry (the answer).
QUESTION_TOOL = "AskUserQuestion"


# Make a piece of log text safe to publish, without changing its meaning.
#
# The logs record absolute paths (/Users/<name>/Dropbox/...), which add nothing for a
# reader and reveal the user's folder layout, so the project folder becomes "" (paths
# read as project-relative, the way they appear in the specs) and the home folder "~".
# Claude Code's temporary folders become "(temp)". The email address is removed by
# rule, as the spec requires. Order matters: the longest prefix is replaced first.
def clean(text):
    text = text.replace(str(ROOT) + "/", "").replace(str(ROOT), ".")
    text = re.sub(r"/Users/[^/\s]+", "~", text)
    # Claude Code's own folder for this project is named after the absolute path
    # ("-Users-<name>-Dropbox-..."), so it is shortened too.
    text = re.sub(r"~/\.claude/projects/[^/\s]+", "~/.claude/projects/(this project)", text)
    # Claude Code's per-session temp folders: /private/tmp/claude-501/... or /tmp/claude-501/...
    text = re.sub(r"(/private)?/tmp/claude-\d+/\S*", "(temp)", text)
    # Any email address (local@domain.tld).
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "(email removed)", text)
    # System notes Claude Code sometimes appends inside a message; not something the
    # user typed. The (?s) flag lets "." match newlines, and *? stops at the first close.
    text = re.sub(r"(?s)<system-reminder>.*?</system-reminder>", "", text)
    return text.strip()


# Convert a log timestamp ("2026-10-17T04:08:12.345Z", UTC) to an aware datetime.
def parse_time(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# The display label for a time: "10:42 PM" in Cincinnati time. %-I (hour without a
# leading zero) is a glibc/BSD strftime extension, available on macOS and Linux.
def time_label(dt):
    return dt.astimezone(TZ).strftime("%-I:%M %p")


# Read one session log into a list of records, keeping only user and assistant lines
# (the log also holds bookkeeping lines: titles, file snapshots, API metadata).
def read_log(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d.get("type") in ("user", "assistant"):
                records.append(d)
    return records


# Read a message's content as a list of blocks; a plain-string content (how typed
# messages are sometimes stored) becomes one text block.
def blocks(record):
    c = record["message"].get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return c or []


# Is this record a message the user typed (or accepted from a suggestion)?
#
# Claude Code marks human input with origin.kind == "human". Everything else that is
# stored with role "user" is not the user's own words: tool results, slash-command
# echoes (/clear), skill instructions, conversation summaries, and task notifications.
def is_human(record):
    return (record.get("origin") or {}).get("kind") == "human" and not record.get("isMeta")


# Turn a message's blocks into display text; images (pasted screenshots) become a
# placeholder, since the log stores them as large base64 blobs.
def message_text(record):
    parts = []
    for b in blocks(record):
        if b.get("type") == "text":
            parts.append(b["text"])
        elif b.get("type") == "image":
            parts.append("[image]")
    return clean("\n\n".join(parts))


# A one-line label for a tool call in an action card's expanded list, plus the file it
# wrote (if any) for the card's summary.
#
# Bash calls carry a short human-readable description that Claude writes for the user's
# permission prompt ("Copy them in"); that is the best label, and it avoids putting long
# shell commands (heredocs full of code) on the page.
def describe_call(name, inp):
    file = None
    if name == "Bash":
        label = inp.get("description") or inp.get("command", "").splitlines()[0][:100]
        kind = "command"
    elif name in ("Write", "Edit", "NotebookEdit"):
        file = clean(inp.get("file_path", ""))
        label = ("Wrote " if name == "Write" else "Edited ") + file
        kind = "write" if name == "Write" else "edit"
    elif name == "Read":
        label = "Read " + clean(inp.get("file_path", ""))
        kind = "read"
    elif name == "WebFetch":
        label = "Fetched " + inp.get("url", "")
        kind = "web"
    elif name == "WebSearch":
        label = "Searched the web: " + inp.get("query", "")
        kind = "web"
    elif name.startswith("mcp__claude-in-chrome__"):
        # Browser automation: name the action (navigate, computer, ...) and its target.
        action = name.removeprefix("mcp__claude-in-chrome__")
        target = inp.get("url") or inp.get("action") or ""
        label = f"Browser: {action} {target}".strip()
        kind = "browser"
    elif name == "Skill":
        label = "Loaded the " + inp.get("skill", "") + " skill"
        kind = "other"
    elif name == "Artifact":
        label = "Artifact: " + (inp.get("action") or "publish")
        kind = "other"
    else:
        label = name
        kind = "other"
    return clean(label), kind, file


# Write the card's one-line summary from its calls, by rule:
# "Ran 12 commands · wrote parse_uic.py, review.html · edited 2 files · 5 browser steps
#  · committed". Notable events (commits, publishing the site) come from the commands.
def summarize(calls):
    counts = Counter(c["kind"] for c in calls)
    parts = []
    if counts["command"]:
        parts.append(f"ran {counts['command']} command" + ("s" if counts["command"] > 1 else ""))
    # dict.fromkeys keeps first-seen order while dropping repeats (a file written twice).
    written = list(dict.fromkeys(c["file"].split("/")[-1] for c in calls if c["kind"] == "write"))
    if written:
        shown = ", ".join(written[:3]) + (f" and {len(written) - 3} more" if len(written) > 3 else "")
        parts.append("wrote " + shown)
    edited = {c["file"] for c in calls if c["kind"] == "edit"}
    if edited:
        parts.append(f"edited {len(edited)} file" + ("s" if len(edited) > 1 else ""))
    if counts["read"]:
        parts.append(f"read {counts['read']} file" + ("s" if counts["read"] > 1 else ""))
    if counts["web"]:
        parts.append(f"{counts['web']} web lookup" + ("s" if counts["web"] > 1 else ""))
    if counts["browser"]:
        parts.append(f"{counts['browser']} browser step" + ("s" if counts["browser"] > 1 else ""))
    if counts["other"]:
        parts.append(f"{counts['other']} other")
    if any(c.get("committed") for c in calls):
        parts.append("committed")
    if any(c.get("published") for c in calls):
        parts.append("published the site")
    if any(c.get("rejected") for c in calls):
        parts.append("(you stopped one)")
    text = " · ".join(parts)
    return text[:1].upper() + text[1:]


# Read the git history (hash, commit time, subject), oldest first, for the commit
# markers and for placing the step markers.
def git_commits():
    out = subprocess.run(
        ["git", "-C", str(ROOT), "log", "--reverse", "--all", "--format=%h%x09%cI%x09%s"],
        capture_output=True, text=True, check=True,
    ).stdout
    commits = []
    for line in out.splitlines():
        h, t, subject = line.split("\t", 2)  # %x09 is a tab, which subjects don't contain
        commits.append({"hash": h, "time": datetime.fromisoformat(t), "subject": subject})
    return commits


# Build the ordered list of timeline entries for one session.
#
# Walks the records in log order. A "you" entry closes the current action card; tool
# calls open or extend one. Each card is placed where its first call happened, so the
# Claude replies written while working ("Status: ...") appear after it in time order.
# Returns the entries and per-kind tallies for the consistency check in main().
def session_entries(records, tally):
    entries = []
    card = None           # the open action card, if any
    calls_by_id = {}      # tool_use id -> the call dict, to mark results (rejections)
    questions_by_id = {}  # tool_use id -> [(raw question text, its entry)], to place answers

    def close_card():
        nonlocal card
        if card:
            card["summary"] = summarize(card["calls"])
            card = None

    for r in records:
        t = parse_time(r["timestamp"])
        uid = r["uuid"][:12]
        if r["type"] == "user":
            if is_human(r):
                text = message_text(r)
                if text:
                    close_card()
                    entries.append({"kind": "you", "id": "u-" + uid, "time": t, "text": text})
                    tally["you"] += 1
                continue
            for b in blocks(r):
                if b.get("type") == "text" and b["text"].startswith("[Request interrupted"):
                    close_card()
                    entries.append({"kind": "you", "id": "u-" + uid, "time": t,
                                    "text": "[Interrupted Claude]", "sub": "interrupt"})
                    tally["interrupt"] += 1
                if b.get("type") != "tool_result":
                    continue
                tid = b.get("tool_use_id")
                result = r.get("toolUseResult")
                denied = r.get("toolDenialKind") == "user-rejected"
                if tid in questions_by_id:
                    close_card()
                    q = questions_by_id[tid]
                    if isinstance(result, dict) and "answers" in result:
                        # Interleave (the user's request): each answer goes right after
                        # its own question, so the timeline reads Q1, A1, Q2, A2. The
                        # answer takes its question's time for sorting (a stable sort
                        # then keeps the pair together) and shows its real time.
                        notes = result.get("annotations") or {}
                        for i, (raw, qentry) in reversed(list(enumerate(q))):
                            if raw not in result["answers"]:
                                continue  # unanswered (not expected, but harmless)
                            answer = {"question": qentry["questions"][0]["header"],
                                      "answer": clean(result["answers"][raw]),
                                      "notes": clean((notes.get(raw) or {}).get("notes") or "")}
                            answer["class"] = answer_class(answer["answer"], qentry["questions"][0]["options"])
                            pos = next(j for j, e in enumerate(entries) if e is qentry) + 1
                            entries.insert(pos, {"kind": "you", "id": f"u-{uid}-{i + 1}", "time": qentry["time"],
                                                 "shown_time": t, "sub": "answer", "answers": [answer], "text": ""})
                            tally["answers"] += 1
                    else:
                        # The user dismissed the question form to discuss instead.
                        entries.append({"kind": "you", "id": "u-" + uid, "time": t, "sub": "declined",
                                        "text": "[Chose to talk it through instead of answering]"})
                        tally["declined"] += 1
                elif tid in calls_by_id and denied:
                    calls_by_id[tid]["rejected"] = True
                    # When the user rejects a tool call they can type why; that is their
                    # own words, so it becomes a You entry. The text follows a fixed phrase.
                    content = b.get("content")
                    content = content if isinstance(content, str) else json.dumps(content)
                    m = re.search(r"the user said:\n(.*)", content, re.S)
                    if m:
                        close_card()
                        entries.append({"kind": "you", "id": "u-" + uid, "time": t,
                                        "text": clean(m.group(1))})
                        tally["you_rejection"] += 1
        else:  # assistant
            for b in blocks(r):
                if b.get("type") == "text" and b["text"].strip():
                    entries.append({"kind": "claude", "id": "c-" + uid, "time": t, "text": clean(b["text"])})
                    tally["claude"] += 1
                elif b.get("type") == "tool_use" and b["name"] == QUESTION_TOOL:
                    close_card()
                    qs = [{"question": clean(q["question"]), "header": q.get("header", ""),
                           "multi": q.get("multiSelect", False),
                           "options": [{"label": clean(o["label"]), "description": clean(o.get("description", "")),
                                        "preview": clean(o.get("preview", ""))} for o in q["options"]]}
                          for q in b["input"].get("questions", [])]
                    # One entry per question (not one per form), so each answer can sit
                    # directly under its own question. Answers are keyed by the
                    # question's raw text, so keep that alongside each entry.
                    questions_by_id[b["id"]] = []
                    for i, (raw, q) in enumerate(zip(b["input"].get("questions", []), qs)):
                        entry = {"kind": "claude", "id": f"q-{uid}-{i + 1}", "time": t, "sub": "question",
                                 "questions": [q], "text": "", "part": i + 1, "of": len(qs)}
                        questions_by_id[b["id"]].append((raw["question"], entry))
                        entries.append(entry)
                        tally["questions"] += 1
                elif b.get("type") == "tool_use":
                    label, kind, file = describe_call(b["name"], b.get("input", {}))
                    # "time" is kept only for the activity overview (each call is binned
                    # at its own moment, not its card's start) and dropped before output.
                    call = {"tool": b["name"], "label": label, "kind": kind, "file": file, "time": t}
                    cmd = b.get("input", {}).get("command", "") if b["name"] == "Bash" else ""
                    call["committed"] = bool(re.search(r"\bgit\b.*\bcommit\b", cmd))
                    call["published"] = "publish_site" in cmd
                    calls_by_id[b["id"]] = call
                    if card is None:
                        card = {"kind": "actions", "id": "a-" + uid, "time": t, "calls": []}
                        entries.append(card)
                    card["calls"].append(call)
                    card["end"] = t
                    tally["calls"] += 1
    close_card()
    return entries


# Classify an answer to one of Claude's questions, by rule (specs/09-process-view.md,
# "Kinds of input"): "recommended" when the author took the option Claude marked
# "(Recommended)", "other" for a different listed option, "own" for text the author
# typed in place of the options, and "no_rec" for a listed option where Claude
# recommended none. A multi-select answer arrives as "A, B"; it is listed options when
# every part is one, and counts as recommended when the recommended option is among them.
def answer_class(answer, options):
    labels = [o["label"] for o in options]
    parts = [answer] if answer in labels else [p.strip() for p in answer.split(", ")]
    if not all(p in labels for p in parts):
        return "own"
    # next() with a default: the recommended label, or None if Claude marked none.
    rec = next((l for l in labels if "(Recommended)" in l), None)
    if rec is None:
        return "no_rec"
    return "recommended" if rec in parts else "other"


# The categories for the author's typed messages, in their fixed display order (it is
# also the color order on the page, chosen to pass the palette's colorblind checks).
INPUT_KINDS = ["Specification", "Exploration", "Clarification", "Decision", "Correction",
               "Working style", "Workflow"]
ANSWER_CLASSES = ["recommended", "other", "own", "no_rec"]


# Attach the hand-reviewed categories (data/reference/process/input_kinds.csv) to the
# author's typed messages, and count them per plan step for the page's summary chart.
#
# "Typed messages" are the author's entries with no sub-kind: answers, declined forms,
# and interruptions are left out (answers are counted separately, by answer_class). A
# message added since the file was last reviewed has no row yet; it is reported and
# shown untagged rather than stopping the build, since every new session adds some.
def attach_input_kinds(items):
    kinds = pd.read_csv(REF_DIR / "input_kinds.csv", dtype=str).fillna("")
    bad = set(kinds["primary"]) - set(INPUT_KINDS) | set(kinds["secondary"]) - set(INPUT_KINDS) - {""}
    if bad:
        raise SystemExit(f"input_kinds.csv has unknown categories: {sorted(bad)}")
    by_id = kinds.set_index("entry_id")
    typed = [e for e in items if e["kind"] == "you" and not e.get("sub")]
    unknown = set(kinds["entry_id"]) - {e["id"] for e in typed}
    if unknown:
        raise SystemExit(f"input_kinds.csv names unknown entries: {sorted(unknown)}")
    missing = [e["id"] for e in typed if e["id"] not in by_id.index]
    if missing:
        print(f"Note: {len(missing)} messages have no category yet: {missing}")

    for e in typed:
        if e["id"] in by_id.index:
            row = by_id.loc[e["id"]]
            e["input"] = row["primary"]
            if row["secondary"]:
                e["input2"] = row["secondary"]

    # Walk the items in order, so each message counts toward the step marker above it.
    steps, current = [], None
    for e in items:
        if e["kind"] == "step":
            current = {"id": e["id"], "step": e["step"], "title": e["text"],
                       "kinds": dict.fromkeys(INPUT_KINDS, 0), "answers": dict.fromkeys(ANSWER_CLASSES, 0)}
            steps.append(current)
        elif current and e.get("input"):
            current["kinds"][e["input"]] += 1
        elif current and e.get("sub") == "answer":
            current["answers"][e["answers"][0]["class"]] += 1
    totals = {k: sum(s["kinds"][k] for s in steps) for k in INPUT_KINDS}
    answers = {k: sum(s["answers"][k] for s in steps) for k in ANSWER_CLASSES}
    # How many rows the author has reviewed, so the page can say whether the categories
    # are still Claude's proposal.
    reviewed = int((kinds["status"] != "proposed").sum())
    return {"kinds": INPUT_KINDS, "totals": totals, "answers": answers,
            "unclassified": len(missing), "reviewed": reviewed, "rows": len(kinds), "steps": steps}


# Count activity per half hour, for the overview grid at the top of the page (one row
# per day, two lanes: the author and Claude). Two measures, chosen by a toggle:
#
# - Counts: the author's lane counts their entries (messages, answers, declines,
#   interruptions); Claude's counts its replies and questions plus each individual tool
#   call, binned at the call's own time, so a long stretch of work shows as long as it ran.
# - Minutes (specs/09-process-view.md, "Activity overview"): time split into turns. The
#   gap between two consecutive events belongs to whoever produced the later one: a gap
#   ending in the author's message was the author reading, thinking, and typing; a gap
#   ending in a Claude event was Claude working. A gap counts in full up to IDLE_CAP,
#   as IDLE_CAP up to BREAK (reading a long proposal, a long command running), and
#   beyond BREAK as a break: the author gets RETURN_CREDIT (reading the reply and typing
#   after coming back), Claude nothing (it was waiting on an approval). The thresholds
#   were set by the user; no author gap fell between 16 and 23 minutes, so BREAK sits
#   in a natural gap. The counted minutes are the last ones before the later event,
#   spread over the half hours they span.
#
# Days are calendar days in Cincinnati time, and every day from the first to the last is
# listed, so days off show as empty rows. Each bin also names the first entry in it (or,
# for a bin only a gap passes through, the entry that ended the gap), so the page can
# jump to that point.
BIN_MINUTES = 30
IDLE_CAP = timedelta(minutes=5)
BREAK = timedelta(minutes=20)
RETURN_CREDIT = {"you": timedelta(minutes=2), "claude": timedelta(0)}


# The minutes a gap counts for, by the rule above.
def credited(gap, lane):
    if gap <= IDLE_CAP:
        return gap
    if gap <= BREAK:
        return IDLE_CAP
    return RETURN_CREDIT[lane]


def build_activity(items):
    # (date, bin index) -> {"you": n, "claude": n, "you_min": m, "claude_min": m, "first": id}
    bins = {}

    # The bin a moment falls in: its local date and its half hour within that day.
    def key_of(t):
        local = t.astimezone(TZ)
        return local.date(), (local.hour * 60 + local.minute) // BIN_MINUTES

    def bin_for(t, entry_id):
        return bins.setdefault(key_of(t), {"you": 0, "claude": 0, "you_min": 0.0, "claude_min": 0.0,
                                           "first": entry_id})

    # The event stream: (time, lane, entry id). An answer sorts at its question's time
    # but happened at shown_time, its real time, which is the one that matters here.
    events = []
    for e in items:
        if e["kind"] in ("you", "claude"):
            events.append((e.get("shown_time", e["time"]), e["kind"], e["id"]))
        elif e["kind"] == "actions":
            events.extend((c["time"], "claude", e["id"]) for c in e["calls"])
    events.sort(key=lambda ev: ev[0])  # sort on time only; ties keep their order

    for t, lane, entry_id in events:
        bin_for(t, entry_id)[lane] += 1

    # Minutes: walk consecutive pairs (zip with the list shifted by one). The gap is
    # credited by the rule above, then counted backward from the later event, cut at
    # half-hour boundaries.
    for (t0, _, _), (t1, lane, entry_id) in zip(events, events[1:]):
        start = t1 - credited(t1 - t0, lane)
        end = t1
        while end > start:
            local = end.astimezone(TZ)
            # The start of the half hour holding the instant just before `end`, so a gap
            # ending exactly on a boundary is counted in the bin before it.
            just_before = (end - timedelta(microseconds=1)).astimezone(TZ)
            bin_start = just_before.replace(minute=just_before.minute - just_before.minute % BIN_MINUTES,
                                            second=0, microsecond=0)
            piece_start = max(start, bin_start)
            b = bin_for(just_before, entry_id)
            b[lane + "_min"] += (end - piece_start).total_seconds() / 60
            end = piece_start

    dates = sorted({d for d, _ in bins})
    days = []
    d = dates[0]
    while d <= dates[-1]:
        cells = []
        for i in range(24 * 60 // BIN_MINUTES):
            if (d, i) in bins:
                b = bins[(d, i)]
                # {**b, ...} copies the bin, adds its index within the day, and replaces
                # the minutes with values rounded to one decimal (a smaller JSON).
                cells.append({"i": i, **b, "you_min": round(b["you_min"], 1),
                              "claude_min": round(b["claude_min"], 1)})
        days.append({"date": d.isoformat(), "label": d.strftime("%a %b %-d"), "cells": cells})
        d = d.fromordinal(d.toordinal() + 1)  # the next calendar day
    # The thresholds go to the page for its caption (timedelta.seconds // 60 = minutes).
    return {"bin_minutes": BIN_MINUTES, "idle_cap_minutes": IDLE_CAP.seconds // 60,
            "break_minutes": BREAK.seconds // 60, "return_minutes": RETURN_CREDIT["you"].seconds // 60,
            "days": days}


# Token usage per plan step (specs/09-process-view.md, "Token usage"), for the page's
# per-step bars.
#
# Every Claude reply in the logs carries the API's usage record: input_tokens (new,
# uncached prompt text), cache_creation_input_tokens (context written to the prompt
# cache), cache_read_input_tokens (earlier context re-read from the cache), and
# output_tokens (what Claude wrote: text, tool calls, and hidden reasoning). One API
# reply is stored as several log lines (one per content block) that repeat the same
# usage, so replies are counted once, by message id. Claude Code's own placeholder
# replies (model "<synthetic>", e.g. after an interruption) made no API call and are
# skipped.
#
# A reply counts toward the step whose marker comes last at or before its time; replies
# before the first marker count toward the first step. Step markers are in time order
# in `items`, since each takes the time of the entry it sits before.
TOKEN_KINDS = {"output": "output_tokens", "cache_write": "cache_creation_input_tokens",
               "input": "input_tokens", "cache_read": "cache_read_input_tokens"}


def build_tokens(sessions, items):
    markers = [e for e in items if e["kind"] == "step"]
    starts = [m["time"] for m in markers]
    steps = [{"id": m["id"], "step": m["step"], "title": m["text"], "replies": 0,
              **dict.fromkeys(TOKEN_KINDS, 0)} for m in markers]
    seen = set()
    for _, recs in sessions:
        for r in recs:
            m = r["message"]
            usage = m.get("usage")
            if r["type"] != "assistant" or not usage or m.get("model") == "<synthetic>" or m.get("id") in seen:
                continue
            seen.add(m.get("id"))
            # bisect_right finds how many step starts are <= this time; minus one is
            # the index of the step it falls in (max(0, ...) puts early replies in the first).
            s = steps[max(0, bisect_right(starts, parse_time(r["timestamp"])) - 1)]
            s["replies"] += 1
            for k, field in TOKEN_KINDS.items():
                s[k] += usage.get(field) or 0  # "or 0" guards a field stored as null
    totals = {k: sum(s[k] for s in steps) for k in ["replies", *TOKEN_KINDS]}
    return {"totals": totals, "steps": steps}


# Read the logs, merge in the dividers and the curation, check the counts, and write
# the timeline JSON.
def main():
    logs = sorted(RAW_DIR.glob("*.jsonl"))
    if not logs:
        raise SystemExit("No logs in data/raw/process/; run src/collect_process.py first.")
    sessions = [(p, read_log(p)) for p in logs]
    sessions = [(p, recs) for p, recs in sessions if recs]
    # Number sessions in the order they started, not by their random file names.
    sessions.sort(key=lambda s: s[1][0]["timestamp"])

    tally = Counter()
    items = []
    for n, (path, recs) in enumerate(sessions, start=1):
        # A session can sit idle for hours after /clear, so it is dated by its first
        # typed message (or its first record, if none).
        start = parse_time(next((r for r in recs if is_human(r)), recs[0])["timestamp"])
        items.append({"kind": "session", "id": f"s-{n}", "time": start, "n": n,
                      "label": start.astimezone(TZ).strftime("%a %b %-d") + f" · Session {n}"})
        items.extend(session_entries(recs, tally))

    # Commit markers, at their commit times. Later sessions start with a summary of
    # earlier work, not a replay, so no commit appears twice.
    commits = git_commits()
    by_hash = {c["hash"]: c for c in commits}
    first = items[0]["time"]
    for c in commits:
        items.append({"kind": "commit", "id": "g-" + c["hash"], "time": c["time"],
                      "hash": c["hash"], "text": c["subject"]})

    # Python's sort is stable, so entries with equal times keep their log order; the
    # rank puts a session divider before anything else at the same instant.
    rank = {"session": 0}
    items.sort(key=lambda e: (e["time"], rank.get(e["kind"], 1)))

    # Step markers (hand-reviewed): each goes just before the first "you" entry after
    # the commit that closed the previous step, or, where that rule lands in the wrong
    # place (a step that began before the previous commit, or a session of leftover
    # tweaks), just before the entry named in before_entry. Step 0 has neither, so it
    # goes before the first "you" entry.
    steps = pd.read_csv(REF_DIR / "steps.csv", dtype=str).fillna("")
    for _, s in steps.iterrows():
        marker = {"kind": "step", "id": "p-" + s["step"], "step": s["step"], "text": s["title"],
                  "status": s["status"]}
        if s["before_entry"]:
            pos = next((i for i, e in enumerate(items) if e["id"] == s["before_entry"]), None)
        else:
            after = by_hash[s["after_commit"]]["time"] if s["after_commit"] else first
            # next() with a default returns None when no "you" entry comes later.
            pos = next((i for i, e in enumerate(items) if e["kind"] == "you" and e["time"] >= after), None)
        if pos is None:
            raise SystemExit(f"Step {s['step']}: can't place the marker; check steps.csv")
        marker["time"] = items[pos]["time"]
        items.insert(pos, marker)

    # Curation (hand-reviewed): hide entries, or attach a note for the committee.
    cur = pd.read_csv(REF_DIR / "curation.csv", dtype=str).fillna("")
    ids = {e["id"] for e in items}
    unknown = set(cur["entry_id"]) - ids
    if unknown:
        raise SystemExit(f"curation.csv names unknown entries: {sorted(unknown)}")
    hidden = set(cur.loc[cur["action"] == "hide", "entry_id"])
    notes = dict(zip(cur.loc[cur["action"] == "note", "entry_id"], cur.loc[cur["action"] == "note", "text"]))

    # Consistency check (spec, "Done when"): every call is in exactly one card, and the
    # entry counts match the tallies taken while reading the logs.
    kinds = Counter(e["kind"] for e in items)
    in_cards = sum(len(e["calls"]) for e in items if e["kind"] == "actions")
    assert in_cards == tally["calls"], (in_cards, tally["calls"])
    assert kinds["claude"] == tally["claude"] + tally["questions"]
    assert kinds["you"] == tally["you"] + tally["answers"] + tally["declined"] + tally["interrupt"] + tally["you_rejection"]

    activity = build_activity([e for e in items if e["id"] not in hidden])
    inputs = attach_input_kinds([e for e in items if e["id"] not in hidden])
    tokens = build_tokens(sessions, items)

    out = []
    for e in items:
        if e["id"] in hidden:
            continue
        e = dict(e)
        e["iso"] = e["time"].isoformat()
        e["label"] = e.get("label") or time_label(e.pop("shown_time", e["time"]))
        if "end" in e:
            e["end_label"] = time_label(e.pop("end"))
        del e["time"]
        if e["id"] in notes:
            e["note"] = notes[e["id"]]
        # Drop the per-call helper fields the page doesn't use.
        for c in e.get("calls", []):
            for k in ("file", "committed", "published", "time"):
                c.pop(k, None)
            if not c.get("rejected"):
                c.pop("rejected", None)
        out.append(e)

    counts = {
        "sessions": len(sessions),
        "you": tally["you"] + tally["you_rejection"],
        "answers": tally["answers"],
        "claude": tally["claude"],
        "questions": tally["questions"],
        "actions": tally["calls"],
        "cards": kinds["actions"],
        "commits": kinds["commit"],
        "hidden": len(hidden),
        "first": first.astimezone(TZ).strftime("%b %-d, %Y"),
        "last": max(e["time"] for e in items).astimezone(TZ).strftime("%b %-d, %Y"),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "timeline.json", "w", encoding="utf-8") as f:
        json.dump({"counts": counts, "activity": activity, "inputs": inputs, "tokens": tokens, "items": out}, f, ensure_ascii=False, indent=1)
    print(json.dumps(counts, indent=1))


if __name__ == "__main__":  # run only when executed as a script, not when imported
    main()
