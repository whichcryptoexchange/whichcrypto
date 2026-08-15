#!/usr/bin/env python3
"""
auto_merge_clean_syncs.py - auto-merge sync PRs whose entire diff is
`retrieved:` date bumps, nothing else.

This is deliberately narrow. It exists because every routine sync PR
this session has been triaged the same way: pull the diff, confirm every
changed line is a source's `retrieved` date moving forward and nothing
else, then squash-merge. That check is a pure mechanical pattern match --
no judgment involved -- so it's safe to automate. Anything that touches
entities, countries, statuses, or any other field gets left alone for a
real review pass, same as it always has.

news-sync is explicitly excluded, always. Matching a brand name against
a news headline is a judgment call ("shares", "strike", and "block" were
all real false positives caught by actually reading the headline, not by
any mechanical rule) -- that stays a human-in-session review forever.

A PR is auto-merged only if EVERY changed line, across every file, in
every hunk, matches exactly:
    [+-]  retrieved: '2026-08-14'
Anything else on any changed line -- a new brand, a status change, an
entity, a country, a services list, a service call -- and the whole PR
is left untouched. This intentionally has no partial-credit path: one
non-date line anywhere disqualifies the entire PR.

Usage (CI only -- needs a repo-scoped GitHub token):
  GH_TOKEN=... GH_REPO=owner/repo python3 scripts/auto_merge_clean_syncs.py
"""
import os
import re
import sys
import urllib.error
import urllib.request
import json

API = "https://api.github.com"

# news-sync is never eligible, regardless of what its diff looks like --
# see the module docstring. Every other sync workflow's branch name.
ELIGIBLE_BRANCHES = {
    "esma-sync", "fca-sync", "vara-sync", "fintrac-sync", "fincen-sync",
    "mas-sync", "sfc-sync", "jp-sync", "my-sync", "kr-sync", "ny-sync",
}

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


def merge_pr(repo, number, title, token):
    return api(f"/repos/{repo}/pulls/{number}/merge", token, method="PUT", body={
        "commit_title": f"{title} (auto-merged, verified pure date-bump diff)",
        "merge_method": "squash",
    })


def main():
    token = os.environ["GH_TOKEN"]
    repo = os.environ["GH_REPO"]

    prs = list_open_prs(repo, token)
    candidates = [p for p in prs if p["head"]["ref"] in ELIGIBLE_BRANCHES]
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

        if is_pure_date_bump_diff(files):
            try:
                merge_pr(repo, number, title, token)
                print(f"  #{number} ({branch}): pure date-bump diff across {len(files)} file(s) — merged")
                merged += 1
            except urllib.error.HTTPError as e:
                print(f"  #{number} ({branch}): merge failed: {e}", file=sys.stderr)
                skipped += 1
        else:
            print(f"  #{number} ({branch}): touches more than retrieved dates — left for review")
            skipped += 1

    print(f"Done. {merged} merged, {skipped} left for a human review pass.")


if __name__ == "__main__":
    main()
