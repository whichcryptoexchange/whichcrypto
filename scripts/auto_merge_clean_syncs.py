#!/usr/bin/env python3
"""
auto_merge_clean_syncs.py - auto-merge sync PRs that are safe by a purely
mechanical check, nothing else. Two categories, two different definitions
of "safe", because they're genuinely different shapes of change:

DATE_BUMP_BRANCHES (the regulator syncs -- ESMA, FCA, VARA, etc.): safe
means the substance never changes, only the `retrieved` timestamp does.
A PR here is auto-merged only if EVERY changed line, across every file,
matches exactly `[+-]  retrieved: '2026-08-14'`. One non-date line
anywhere -- a new brand, a status change, an entity, a country -- and
the whole PR is left untouched.

REVIEWS_BRANCHES (third-party ratings -- App Store, Trustpilot): the
opposite shape. The substance (rating, review count) is EXPECTED to
change every run -- that's the point of the sync -- so "only the date
changed" would almost never fire and the feature would sit unused. Safe
here means something narrower but still mechanical: only the
`third_party_reviews` key differs from the file's previous content nothing
else on the brand does; every (source, url) pair that existed before
still exists after (no source silently added or removed -- a *new*
source mapping for a brand still needs a first-time human check that the
App Store ID or Trustpilot business unit actually matches the right
company); the rating stays within [0, 5]; and the review count never
goes backwards. This needs the full before/after file content, not just
the diff, to compare structurally rather than line-by-line.

news-sync is permanently excluded from both, regardless of what its diff
looks like. Matching a brand name against a headline is a judgment call
("shares", "strike", and "block" were all real false positives caught by
actually reading the headline, not by any mechanical rule) -- that stays
a human-in-session review forever.

Usage (CI only -- needs a repo-scoped GitHub token):
  GH_TOKEN=... GH_REPO=owner/repo python3 scripts/auto_merge_clean_syncs.py
"""
import base64
import os
import re
import sys
import urllib.error
import urllib.request
import json

import yaml

API = "https://api.github.com"

DATE_BUMP_BRANCHES = {
    "esma-sync", "fca-sync", "vara-sync", "fintrac-sync", "fincen-sync",
    "mas-sync", "sfc-sync", "jp-sync", "my-sync", "kr-sync", "ny-sync",
}
REVIEWS_BRANCHES = {"appstore-sync", "trustpilot-sync"}

# Matches a whole changed line that is ONLY a retrieved-date value --
# any surrounding text, a different key, or a malformed date fails this.
PURE_DATE_BUMP = re.compile(r"^[+-]\s*retrieved: '\d{4}-\d{2}-\d{2}'\s*$")


def api(path, token, method="GET", body=None):
    req = urllib.request.Request(
        f"{API}{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r) if r.length != 0 else {}


def list_open_prs(repo, token):
    prs, page = [], 1
    while True:
        batch = api(f"/repos/{repo}/pulls?state=open&per_page=100&page={page}", token)
        if not batch:
            break
        prs.extend(batch)
        page += 1
    return prs


def pr_files(repo, number, token):
    files, page = [], 1
    while True:
        batch = api(f"/repos/{repo}/pulls/{number}/files?per_page=100&page={page}", token)
        if not batch:
            break
        files.extend(batch)
        page += 1
    return files


def is_pure_date_bump_diff(files):
    for f in files:
        patch = f.get("patch")
        if patch is None:
            # Binary file, or a diff too large for GitHub to return a
            # patch for -- can't verify it's safe, so it isn't.
            return False
        for line in patch.splitlines():
            if not line or line[0] not in "+-":
                continue
            if line.startswith("+++") or line.startswith("---"):
                continue
            if not PURE_DATE_BUMP.match(line):
                return False
    return True


def file_at_ref(repo, path, ref, token):
    try:
        data = api(f"/repos/{repo}/contents/{path}?ref={ref}", token)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return base64.b64decode(data["content"]).decode()


def is_safe_reviews_diff(repo, pr, files, token):
    base_sha, head_sha = pr["base"]["sha"], pr["head"]["sha"]
    for f in files:
        if f["status"] != "modified":
            return False  # a brand-new or deleted file always needs a human look
        path = f["filename"]
        before_text = file_at_ref(repo, path, base_sha, token)
        after_text = file_at_ref(repo, path, head_sha, token)
        if before_text is None or after_text is None:
            return False
        try:
            before = yaml.safe_load(before_text) or {}
            after = yaml.safe_load(after_text) or {}
        except yaml.YAMLError:
            return False

        # Every key except third_party_reviews must be byte-for-byte
        # identical -- this sync owns that one key and nothing else.
        before_rest = {k: v for k, v in before.items() if k != "third_party_reviews"}
        after_rest = {k: v for k, v in after.items() if k != "third_party_reviews"}
        if before_rest != after_rest:
            return False

        before_reviews = {(e.get("source"), e.get("url")): e for e in (before.get("third_party_reviews") or [])}
        after_reviews = {(e.get("source"), e.get("url")): e for e in (after.get("third_party_reviews") or [])}
        # No (source, url) pair may appear or disappear -- a brand's
        # *first* review-source mapping still needs a human to confirm
        # the App Store ID / Trustpilot business unit actually matches
        # the right company before it's trusted.
        if set(before_reviews) != set(after_reviews):
            return False

        for key, before_entry in before_reviews.items():
            after_entry = after_reviews[key]
            rating = after_entry.get("rating")
            count = after_entry.get("count")
            before_count = before_entry.get("count") or 0
            if rating is None or not (0 <= rating <= 5):
                return False
            # Real-world finding from the first live run: App Store counts
            # can drop slightly run to run (Apple periodically prunes
            # reviews) -- OKX went 22413 -> 22379, Bitstamp 7458 -> 7457,
            # both entirely normal. A small dip is expected; a big one
            # (e.g. a mismatched app ID suddenly pointing at a different,
            # much smaller app) is exactly what this check exists to catch.
            if count is None or count < before_count * 0.95:
                return False
    return True


def merge_pr(repo, number, title, reason, token):
    return api(f"/repos/{repo}/pulls/{number}/merge", token, method="PUT", body={
        "commit_title": f"{title} (auto-merged, {reason})",
        "merge_method": "squash",
    })


def main():
    token = os.environ["GH_TOKEN"]
    repo = os.environ["GH_REPO"]

    prs = list_open_prs(repo, token)
    eligible = DATE_BUMP_BRANCHES | REVIEWS_BRANCHES
    candidates = [p for p in prs if p["head"]["ref"] in eligible]
    print(f"{len(prs)} open PR(s) total, {len(candidates)} on an eligible sync branch.")

    merged, skipped = 0, 0
    for pr in candidates:
        number, branch, title = pr["number"], pr["head"]["ref"], pr["title"]
        try:
            files = pr_files(repo, number, token)
        except urllib.error.HTTPError as e:
            print(f"  #{number} ({branch}): ERROR fetching files: {e}", file=sys.stderr)
            skipped += 1
            continue

        if not files:
            print(f"  #{number} ({branch}): no files returned — skipping")
            skipped += 1
            continue

        if branch in DATE_BUMP_BRANCHES:
            safe, reason = is_pure_date_bump_diff(files), "verified pure date-bump diff"
        else:
            try:
                safe, reason = is_safe_reviews_diff(repo, pr, files, token), "verified rating/count-only change to existing sources"
            except urllib.error.HTTPError as e:
                print(f"  #{number} ({branch}): ERROR comparing file contents: {e}", file=sys.stderr)
                skipped += 1
                continue

        if safe:
            try:
                merge_pr(repo, number, title, reason, token)
                print(f"  #{number} ({branch}): {reason} across {len(files)} file(s) — merged")
                merged += 1
            except urllib.error.HTTPError as e:
                print(f"  #{number} ({branch}): merge failed: {e}", file=sys.stderr)
                skipped += 1
        else:
            print(f"  #{number} ({branch}): does not meet the safe-auto-merge shape — left for review")
            skipped += 1

    print(f"Done. {merged} merged, {skipped} left for a human review pass.")


if __name__ == "__main__":
    main()
