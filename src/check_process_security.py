"""Security check for the process timeline before it is published (step 21).

The process page shows the working conversations, so its data file
(data/processed/process/timeline.json) is the one place in the project where a pasted
secret or a private detail could reach the public site. parse_transcripts.py already
redacts by rule; this script is an independent second check that publish_site.sh runs
before copying the process page (PUBLISH_PROCESS=1), and it stops the publish if
anything is flagged. The user asked for this on 2026-11-14: keep publishing the chat
history, but check it for security problems first.

It looks for:
- credentials: the same token patterns parse_transcripts.py redacts (CREDENTIALS);
- long random-looking strings (likely keys the patterns don't know), by entropy;
- email addresses, absolute home-folder paths, and private network addresses;
- private keys (PEM blocks).

Every string in the JSON is scanned, wherever it sits, so a field added later is
covered too. Exit status 0 means clean; 1 means findings (printed with their location).

Usage:
    python src/check_process_security.py [path/to/timeline.json]
"""

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

# Reuse the redaction patterns, so the check and the redaction can't drift apart.
# parse_transcripts.py sits in this folder; Python puts the script's own folder on
# sys.path, so a plain import works when this is run as `python src/...`.
from parse_transcripts import CREDENTIALS

ROOT = Path(__file__).resolve().parent.parent
DEFAULT = ROOT / "data" / "processed" / "process" / "timeline.json"

# Other patterns, each with a short name for the report. Paths under "~" are fine (the
# home folder is already shortened); "/Users/<name>" or "/home/<name>" would reveal the
# account name. Private addresses (10.x, 192.168.x, 172.16-31.x) reveal the home network.
OTHER = {
    "email address": r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}",
    "home-folder path": r"/(?:Users|home)/[A-Za-z0-9._-]+",
    "private network address": r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b",
    "private key": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    # macOS per-user temp folders (/var/folders/xx/<random>/T/...): the random part is
    # tied to the account, so parse_transcripts.py shortens these to "(temp)".
    "macOS temp path": r"/var/folders/\S+",
}

# A "word" of 32+ characters drawn from letters, digits, and a few symbols is a token
# candidate. Ordinary text rarely has words that long; keys and hashes do. "/" is left
# out on purpose: it splits URLs and file paths into their parts, which are short, so a
# long catalog URL isn't flagged as one random-looking string.
CANDIDATE = re.compile(r"[A-Za-z0-9+_=-]{32,}")
# Shannon entropy in bits per character. Random base64 is near 6, random hex near 4;
# English-like identifiers (long file names, snake_case words) sit lower. 4.5 flags
# random keys while letting through hex hashes and long readable names; it was checked
# against the current timeline (no false positives).
ENTROPY_MIN = 4.5


# Shannon entropy of a string: -sum(p * log2 p) over its characters' frequencies.
# A high value means the characters are spread evenly, as in a random key.
def entropy(s):
    counts = Counter(s)
    return -sum(c / len(s) * math.log2(c / len(s)) for c in counts.values())


# Walk any JSON value and yield (location, string) for every string in it, including
# dictionary keys. The location ("items[12].text") tells the reader where to look.
def strings(value, where="$"):
    if isinstance(value, str):
        yield where, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield f"{where}.{k} (key)", str(k)
            yield from strings(v, f"{where}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from strings(v, f"{where}[{i}]")


# Return a list of (location, kind, matched text) for everything suspicious.
def scan(data):
    patterns = [("credential", p) for p in CREDENTIALS] + [(k, p) for k, p in OTHER.items()]
    found = []
    for where, text in strings(data):
        for kind, pat in patterns:
            for m in re.finditer(pat, text):
                found.append((where, kind, m.group(0)))
        for m in CANDIDATE.finditer(text):
            word = m.group(0)
            # Hex-only strings are git hashes or checksums, not secrets, and their
            # entropy tops out at 4 bits, so they never pass the threshold anyway.
            if entropy(word) >= ENTROPY_MIN:
                found.append((where, "random-looking string", word))
    return found


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    data = json.loads(path.read_text(encoding="utf-8"))
    found = scan(data)
    if not found:
        print(f"Security check passed: {path.name} has no credentials or private details.")
        return 0
    print(f"Security check FAILED: {len(found)} finding(s) in {path}:")
    for where, kind, text in found:
        # Show only the start of the match, so the report itself doesn't repeat a secret.
        print(f"  {kind}: {text[:6]}... at {where}")
    print("Fix the source (curation.csv 'hide', or a redaction rule in parse_transcripts.py),"
          " rerun parse_transcripts.py, then publish again.")
    return 1


# Run main() only when this file is executed as a script, not when it is imported.
if __name__ == "__main__":
    sys.exit(main())
