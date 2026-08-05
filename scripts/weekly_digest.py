#!/usr/bin/env python3
"""
weekly_digest.py - builds the weekly regulatory roundup email content by
diffing data/exchanges/*.yaml against the state N days ago in git history.

Only eu_status and countries are compared -- the two fields that actually
drive what's shown on exchange pages and the country stamps -- not sources[]
or entities[].records[], which get rewritten on every sync run even when
nothing regulatory actually changed (just a re-confirmed retrieved date).

EU/EEA country codes are deliberately excluded from the per-country diff:
MiCA passporting means a single EU authorisation change adds/removes ~30
country keys at once, so eu_status alone is the correct single signal for
that -- diffing each passported country individually would flood the email
with up to 30 near-duplicate lines for one real change.

Changes are grouped by jurisdiction in the rendered email (New entries,
EU/EEA, then one section per non-EEA source) so a reader who only cares
about one place can jump straight to it, rather than a flat brand-sorted
list.

Usage:
  python3 scripts/weekly_digest.py [--since-days 7]

Prints {"subject": ..., "text": ..., "count": N} as JSON on stdout. count is
the number of individual changes detected; the caller (the weekly-digest
GitHub Actions workflow) skips sending when count is 0.
"""
import argparse
import json
import pathlib
import subprocess

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXCHANGES_DIR = ROOT / "data" / "exchanges"

EEA_CODES = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR",
    "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU", "LV", "MT", "NL", "NO",
    "PL", "PT", "RO", "SE", "SI", "SK",
}

NEW_ENTRIES = "New entries"
EEA_GROUP = "EU/EEA (MiCA)"
REMOVED = "Removed from the register"
# Display order for sections that have any content -- anything not listed
# here (a future jurisdiction not yet added below) still renders, just
# after these, sorted alphabetically by code.
GROUP_ORDER = [NEW_ENTRIES, EEA_GROUP, "GB", "CA", "AE", "SG", "US", "HK", "GI", "JP", "MY", REMOVED]
GROUP_LABELS = {
    "GB": "United Kingdom (FCA)", "CA": "Canada (FINTRAC)", "AE": "Dubai (VARA)",
    "SG": "Singapore (MAS)", "US": "United States (FinCEN)", "HK": "Hong Kong (SFC)",
    "GI": "Gibraltar (GFSC)", "JP": "Japan (FSA)", "MY": "Malaysia (SC)",
}


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
    """Returns a list of (group_key, description) tuples."""
    changes = []
    old_eu = old.get("eu_status") if old else None
    new_eu = new.get("eu_status")
    if old is not None and old_eu != new_eu:
        changes.append((EEA_GROUP, f"EU MiCA status changed: {old_eu or 'none'} -> {new_eu or 'none'}"))

    old_countries = (old or {}).get("countries") or {}
    new_countries = new.get("countries") or {}
    non_eea_cc = (set(old_countries) | set(new_countries)) - EEA_CODES
    for cc in sorted(non_eea_cc):
        old_sig = country_signature(as_list(old_countries.get(cc)))
        new_sig = country_signature(as_list(new_countries.get(cc)))
        if old_sig == new_sig:
            continue
        if cc not in old_countries:
            for status, regime, _entity in sorted(new_sig, key=lambda t: t[1] or ""):
                changes.append((cc, f"new entry -- {status} under {regime}"))
        elif cc not in new_countries:
            changes.append((cc, "entry removed"))
        else:
            changes.append((cc, "entry updated"))
    return changes


def genuine_licence_summary(new):
    out = []
    for cc, entry in (new.get("countries") or {}).items():
        for e in as_list(entry):
            if e.get("status") in ("licensed", "authorised"):
                out.append(f"{cc} ({e.get('regime')})")
    return sorted(set(out))


def group_label(key):
    return GROUP_LABELS.get(key, key)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-days", type=int, default=7)
    args = ap.parse_args()

    ref = old_ref(args.since_days)
    old_state = load_at_ref(ref)
    new_state = load_current()

    sections = {}

    def add(group, line):
        sections.setdefault(group, []).append(line)

    for bid, new in sorted(new_state.items(), key=lambda kv: kv[1].get("brand", kv[0])):
        old = old_state.get(bid)
        brand = new.get("brand", bid)
        if old is None:
            summary = f"New entry: {brand}"
            genuine = genuine_licence_summary(new)
            if genuine:
                summary += " -- " + ", ".join(genuine)
            add(NEW_ENTRIES, summary)
            continue
        for group, desc in diff_brand(old, new):
            add(group, f"{brand}: {desc}")

    for bid in sorted(set(old_state) - set(new_state)):
        add(REMOVED, old_state[bid].get("brand", bid))

    count = sum(len(v) for v in sections.values())
    if count == 0:
        text = "No regulatory changes to report this week."
    else:
        ordered_keys = GROUP_ORDER + sorted(k for k in sections if k not in GROUP_ORDER)
        lines = [
            f"{count} change{'s' if count != 1 else ''} on whichcryptoexchange.com this week:",
        ]
        for key in ordered_keys:
            items = sections.get(key)
            if not items:
                continue
            lines.append("")
            lines.append(f"-- {group_label(key)} --")
            lines += [f"- {item}" for item in items]
        lines += [
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
