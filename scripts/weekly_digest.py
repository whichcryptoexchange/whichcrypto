#!/usr/bin/env python3
"""
weekly_digest.py - builds the weekly regulatory roundup email content by
diffing data/exchanges/*.yaml against the state N days ago in git history.

Only eu_status and countries are compared -- the two fields that actually
drive what's shown on exchange pages and the country stamps -- not sources[]
or entities[].records[], which get rewritten on every sync run even when
nothing regulatory actually changed (just a re-confirmed retrieved date).

Usage:
  python3 scripts/weekly_digest.py [--since-days 7]

Prints {"subject": ..., "text": ..., "count": N} as JSON on stdout. count is
the number of brands with at least one detected change; the caller (the
weekly-digest GitHub Actions workflow) skips sending when count is 0.
"""
import argparse
import json
import pathlib
import subprocess

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXCHANGES_DIR = ROOT / "data" / "exchanges"


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout


def old_ref(since_days):
    out = run(["git", "rev-list", "-1", f"--before={since_days} days ago", "HEAD"]).strip()
    return out or None


def load_current():
    state = {}
    for f in sorted(EXCHANGES_DIR.glob("*.yaml")):
        data = yaml.safe_load(f.read_text())
        if data and data.get("id"):
            state[data["id"]] = data
    return state


def load_at_ref(ref):
    state = {}
    if not ref:
        return state
    listing = run(["git", "ls-tree", "-r", "--name-only", ref, "--", "data/exchanges/"])
    for path in listing.splitlines():
        if not path.endswith(".yaml"):
            continue
        try:
            raw = run(["git", "show", f"{ref}:{path}"])
        except subprocess.CalledProcessError:
            continue
        data = yaml.safe_load(raw)
        if data and data.get("id"):
            state[data["id"]] = data
    return state


def as_list(entry):
    if entry is None:
        return []
    return entry if isinstance(entry, list) else [entry]


def country_signature(entries):
    return {(e.get("status"), e.get("regime"), e.get("entity")) for e in entries}


def diff_brand(old, new):
    changes = []
    old_eu = old.get("eu_status") if old else None
    new_eu = new.get("eu_status")
    if old is not None and old_eu != new_eu:
        changes.append(f"EU MiCA status changed: {old_eu or 'none'} -> {new_eu or 'none'}")

    old_countries = (old or {}).get("countries") or {}
    new_countries = new.get("countries") or {}
    for cc in sorted(set(old_countries) | set(new_countries)):
        old_sig = country_signature(as_list(old_countries.get(cc)))
        new_sig = country_signature(as_list(new_countries.get(cc)))
        if old_sig == new_sig:
            continue
        if cc not in old_countries:
            for status, regime, _entity in sorted(new_sig, key=lambda t: t[1] or ""):
                changes.append(f"new {cc} entry -- {status} under {regime}")
        elif cc not in new_countries:
            changes.append(f"{cc} entry removed")
        else:
            changes.append(f"{cc} entry updated")
    return changes


def genuine_licence_summary(new):
    out = []
    for cc, entry in (new.get("countries") or {}).items():
        for e in as_list(entry):
            if e.get("status") in ("licensed", "authorised"):
                out.append(f"{cc} ({e.get('regime')})")
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-days", type=int, default=7)
    args = ap.parse_args()

    ref = old_ref(args.since_days)
    old_state = load_at_ref(ref)
    new_state = load_current()

    brand_lines = []
    for bid, new in sorted(new_state.items(), key=lambda kv: kv[1].get("brand", kv[0])):
        old = old_state.get(bid)
        if old is None:
            summary = f"New entry: {new.get('brand', bid)}"
            genuine = genuine_licence_summary(new)
            if genuine:
                summary += " -- " + ", ".join(genuine)
            brand_lines.append(summary)
            continue
        changes = diff_brand(old, new)
        if changes:
            brand_lines.append(f"{new.get('brand', bid)}: " + "; ".join(changes))

    for bid in sorted(set(old_state) - set(new_state)):
        brand_lines.append(f"{old_state[bid].get('brand', bid)}: removed from the register")

    count = len(brand_lines)
    if count == 0:
        text = "No regulatory changes to report this week."
    else:
        lines = [
            f"{count} change{'s' if count != 1 else ''} on whichcryptoexchange.com this week:",
            "",
        ] + [f"- {line}" for line in brand_lines] + [
            "",
            "Full register: https://whichcryptoexchange.com/exchanges/",
            "Changelog: https://whichcryptoexchange.com/changelog/",
        ]
        text = "\n".join(lines)

    subject = (
        f"Weekly regulatory roundup: {count} change{'s' if count != 1 else ''}"
        if count else "Weekly regulatory roundup: no changes this week"
    )
    print(json.dumps({"subject": subject, "text": text, "count": count}))


if __name__ == "__main__":
    main()
