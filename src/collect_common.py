"""Shared download-and-log helpers for the per-school collect scripts.

Every school's collector follows the same rules as collect_uc.py (specs/02-data.md):

- Files are saved unchanged in data/raw/<id>/ with the retrieval date as a filename
  prefix (e.g. 2026-10-17_bs-cs-catalog.html).
- Existing files are never overwritten; a rerun on a later date adds a new snapshot.
- Every saved file gets a row in data/raw/<id>/sources.csv (URL, file, date, method,
  HTTP status, size, SHA-256), so any parsed value can be traced to its source.

collect_uc.py predates this module and keeps its own copy of the same logic. Later
collectors (collect_osu.py, collect_uic.py, ...) import from here instead.
"""

import csv
import hashlib
from pathlib import Path

import requests

# Same column order as UC's manifest, so every school's sources.csv has one schema.
MANIFEST_COLUMNS = [
    "retrieved_date", "file", "url", "description", "method",
    "http_status", "bytes", "sha256",
]

# Identify the script honestly to the schools' servers instead of the default
# "python-requests/x.y" User-Agent, so site admins can see what is making the requests.
HEADERS = {"User-Agent": "curriculum-comparison research script (python-requests)"}


# Add one record to a school's manifest. Append mode ("a") never rewrites earlier rows,
# so the manifest is a log of every snapshot ever taken. The header row is written only
# when the file is new.
def append_manifest(raw_dir: Path, row: dict) -> None:
    """Append one row to raw_dir/sources.csv, writing the header if the file is new."""
    manifest = raw_dir / "sources.csv"
    is_new = not manifest.exists()  # check before open(): opening in "a" mode creates the file
    # newline="" lets the csv module control line endings itself.
    with manifest.open("a", newline="", encoding="utf-8") as f:
        # DictWriter matches keys to columns by name and raises on missing/extra keys.
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)


# Save already-downloaded bytes as raw_dir/<name> and log them. Split out from fetch()
# so collectors that build their own requests (e.g. an API query with parameters) use
# the same never-overwrite and manifest rules. `name` is relative to raw_dir and may
# include a subfolder, e.g. "courses/2026-10-17_osu-api_CSE2221.json".
def save(raw_dir: Path, name: str, url: str, description: str, method: str,
         resp: requests.Response, today: str) -> None:
    """Write resp.content to raw_dir/name (if new) and append a manifest row."""
    save_bytes(raw_dir, name, url, description, method, resp.content, resp.status_code, today)


# The never-overwrite-and-log core of save(), for bytes that didn't come from a
# requests call: a page saved through the user's browser because the site refuses
# scripts (Berkeley Engineering returns 403), imported by collect_ucb.py. The caller
# passes the HTTP status it observed.
def save_bytes(raw_dir: Path, name: str, url: str, description: str, method: str,
               content: bytes, status: int, today: str) -> None:
    """Write content to raw_dir/name (if new) and append a manifest row."""
    path = raw_dir / name
    if path.exists():
        print(f"skip   {name} (already saved today)")
        return
    path.parent.mkdir(parents=True, exist_ok=True)  # creates courses/ on the first course
    # content is the raw bytes, so the file is exactly what the server sent and the
    # SHA-256 below can be recomputed later to show the file hasn't been edited.
    path.write_bytes(content)
    append_manifest(raw_dir, {
        "retrieved_date": today,
        "file": name,
        "url": url,
        "description": description,
        "method": method,
        "http_status": status,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    })
    print(f"saved  {name} ({len(content):,} bytes)")  # :, adds thousands separators


# Import a "bundle" saved through the user's Chrome: one JSON file holding several pages,
# each fetched same-origin in an open page of the site and stored as base64 of the
# unchanged response bytes. Added in step 13 batch 3, because Chrome blocks a site's
# second and later automatic downloads (Michigan, batch 2): one download per bundle
# avoids that. The bundle looks like
#     {"saved_at": "...", "method": "...", "pages": [{"url", "status", "bytes", "base64"}, ...]}
# `name_for(page)` returns the raw-folder name (without the date prefix) for a page, or
# None to skip it. Each page is decoded, its length checked against the "bytes" the
# browser recorded, and saved with save_bytes() (method "browser"), so its SHA-256 is
# the hash of exactly what the server sent.
def import_bundle(raw_dir: Path, bundle: Path, name_for, describe, today: str) -> None:
    """Save every page of a Chrome-saved JSON bundle into raw_dir and log it."""
    import base64
    import json
    data = json.loads(bundle.read_text(encoding="utf-8"))
    for page in data["pages"]:
        name = name_for(page)
        if name is None:
            continue
        content = base64.b64decode(page["base64"])  # back to the server's exact bytes
        if len(content) != page["bytes"] or page["status"] != 200:
            raise SystemExit(f"{bundle.name}: {page['url']} has status {page['status']} or a size mismatch.")
        # The date goes on the file name, after any subfolder: "courses/CS18000.html"
        # -> "courses/2026-10-17_CS18000.html" (Berkeley's layout). rpartition splits at
        # the last "/", leaving folder "" for a top-level name.
        folder, slash, file = name.rpartition("/")
        save_bytes(raw_dir, f"{folder}{slash}{today}_{file}", page["url"],
                   describe(page) + f" Saved through Chrome (same-origin fetch, unchanged bytes, bundle "
                   f"{bundle.name} saved {data['saved_at'][:10]}).",
                   "browser", content, page["status"], today)


# Download one URL and save it as raw_dir/<today>_<slug><ext>. Skips the request
# entirely when today's file already exists, so reruns don't contact the server.
def fetch(raw_dir: Path, slug: str, url: str, description: str, today: str, ext: str = ".html") -> None:
    """Download url into raw_dir with a dated filename and log it in sources.csv."""
    name = f"{today}_{slug}{ext}"
    if (raw_dir / name).exists():
        print(f"skip   {name} (already saved today)")
        return
    resp = requests.get(url, headers=HEADERS, timeout=30)  # timeout: never hang on a dead server
    resp.raise_for_status()  # 4xx/5xx raise, so an error page is never saved as a source
    save(raw_dir, name, url, description, "script", resp, today)
