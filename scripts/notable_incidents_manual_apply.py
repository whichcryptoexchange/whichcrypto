#!/usr/bin/env python3
"""
notable_incidents_manual_apply.py - apply the hand-curated, hand-verified
incident list (data/notable_incidents_manual.yaml) to data/exchanges/.

Unlike every other field on this site, there is no live source to sync
against here -- no regulator publishes a structured "exchange incident"
feed, so this is researched and cross-checked by hand against multiple
independent, reputable sources, same discipline as the BVI/Gibraltar/ADGM
manual-verification pattern (see bvi_manual_apply.py). Re-run this after
editing data/notable_incidents_manual.yaml; there is no schedule.

Writes a `notable_incidents` top-level key per brand file (only for
brands with an entry). scripts/esma_sync.py must preserve this key when
it regenerates a file from CASPS.csv, the same way it already preserves
third_party_reviews/news_mentions/company_facts -- it has no way to
reproduce this data itself.

Usage:
  python3 scripts/notable_incidents_manual_apply.py
"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    snapshot = yaml.safe_load((DATA / "notable_incidents_manual.yaml").read_text())
    retrieved = snapshot["retrieved"]
    exch_dir = DATA / "exchanges"

    by_brand = {}
    for item in snapshot["incidents"]:
        by_brand.setdefault(item["brand_id"], []).append(item)

    for brand_id, items in sorted(by_brand.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping", file=sys.stderr)
            continue

        entries = [
            {
                "type": item["type"],
                "date": item["date"],
                "headline": item["headline"],
                "summary": item["summary"].strip(),
                "sources": item["sources"],
                "retrieved": retrieved,
            }
            for item in sorted(items, key=lambda i: i["date"], reverse=True)
        ]

        doc = yaml.safe_load(path.read_text())
        doc["notable_incidents"] = entries
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} incident{'s' if len(entries) != 1 else ''}")

    print("Done. Remember: this only reflects data/notable_incidents_manual.yaml --")
    print("edit that file by hand (with sources) and re-run to add or update incidents.")


if __name__ == "__main__":
    main()
