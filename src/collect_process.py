"""Copy this project's Claude Code session logs into data/raw/process/ (step 21).

The process view (specs/09-process-view.md) is built from the session logs Claude Code
writes for this project: one JSON Lines file per session, holding every message, tool
call, and timestamp. Claude Code keeps them outside the project, in
~/.claude/projects/<project folder name>/, so this script copies them in, the way the
collect_<school>.py scripts download catalog pages: parse_transcripts.py then reads only
the copies, and every entry on the page traces back to a file in data/raw/.

The copies are git-ignored (see .gitignore): they hold the full conversations, including
tool outputs, and only the reviewed, processed timeline is meant to leave this machine.

Usage:
    python src/collect_process.py
"""

import shutil
from pathlib import Path

from common import ROOT

# Claude Code names a project's log folder after its absolute path, with every "/"
# (and other non-alphanumeric characters such as "_" or ".") replaced by "-".
LOG_DIR = Path.home() / ".claude" / "projects" / ("-" + "-".join(ROOT.parts[1:]).replace("_", "-"))
RAW_DIR = ROOT / "data" / "raw" / "process"


# Copy every session log whose source is newer or larger than our copy.
#
# Session logs are append-only while a session runs, so a log copied mid-session (this
# one, for instance) is a prefix of the final file; re-running the script refreshes it.
# Files are copied byte for byte (shutil.copy2 also keeps the modification time), so the
# copy is exactly what Claude Code wrote.
def collect():
    if not LOG_DIR.is_dir():
        raise SystemExit(f"No Claude Code log folder at {LOG_DIR}")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    copied = 0
    for src in sorted(LOG_DIR.glob("*.jsonl")):
        dst = RAW_DIR / src.name
        s = src.stat()
        # Skip unchanged logs: same size and not newer than the copy.
        if dst.exists() and dst.stat().st_size == s.st_size and dst.stat().st_mtime >= s.st_mtime:
            continue
        shutil.copy2(src, dst)
        copied += 1
    total = len(list(RAW_DIR.glob("*.jsonl")))
    print(f"Copied {copied} new or updated logs; {total} session logs in {RAW_DIR.relative_to(ROOT)}")


if __name__ == "__main__":  # run only when executed as a script, not when imported
    collect()
