#!/usr/bin/env python3
"""
scam_clones_manual_apply.py - apply the hand-curated clone/scam-firm
warning list (data/scam_clones_manual.yaml) to data/exchanges/.

Same pattern as notable_incidents_manual_apply.py: there is no API/feed
for this (the FCA's public V0.1 REST API used by fca_sync.py does not
expose "Clones of this firm" notices -- only the live register web page
does), so each entry is read by hand off the regulator's own page and
added to the manual source file, then applied here. Re-run this after
editing data/scam_clones_manual.yaml; there is no schedule.

Writes a `scam_clones` top-level key per brand file (only for brands
with an entry). scripts/esma_sync.py must preserve this key when it
regenerates a file from CASPS.csv, same as third_party_reviews/
news_mentions/company_facts/notable_incidents/audits -- it has no way
to reproduce this data itself.

Usage:
  python3 scripts/scam_clones_manual_apply.py
"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    snapshot = yaml.safe_load((DATA / "scam_clones_manual.yaml").read_text())
    retrieved = snapshot["retrieved"]
    exch_dir = DATA / "exchanges"

    by_brand = {}
    for item in snapshot["clones"]:
        by_brand.setdefault(item["brand_id"], []).append(item)

    for brand_id, items in sorted(by_brand.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping", file=sys.stderr)
            continue

        entries = [
            {
                "clone_name": item["clone_name"],
                "regulator": item["regulator"],
                "notice": item["notice"],
                "added_to_register": item.get("added_to_register"),
                "source_url": item["source_url"],
                "retrieved": retrieved,
            }
            for item in sorted(items, key=lambda i: i["clone_name"])
        ]

        doc = yaml.safe_load(path.read_text())
        doc["scam_clones"] = entries
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} clone warning{'s' if len(entries) != 1 else ''}")

    print("Done. Remember: this only reflects data/scam_clones_manual.yaml --")
    print("edit that file by hand (with a source_url) and re-run to add or update warnings.")


if __name__ == "__main__":
    main()
