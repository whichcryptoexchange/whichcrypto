#!/usr/bin/env python3
"""
audits_manual_apply.py - apply the hand-curated, hand-verified audit /
proof-of-reserves history (data/audits_manual.yaml) to data/exchanges/.

Same rationale and pattern as notable_incidents_manual_apply.py: there is
no live source for this -- no regulator publishes a structured "who got
audited" feed, and "audit" is used loosely enough in crypto to be actively
misleading, so this is researched and cross-checked by hand, with a
tier + status distinction baked into the schema itself so a proof-of-
reserves attestation can never accidentally render the same as a full
financial audit. Re-run this after editing data/audits_manual.yaml; there
is no schedule.

Writes an `audits` top-level key per brand file (only for brands with an
entry). scripts/esma_sync.py must preserve this key when it regenerates a
file from CASPS.csv, same as third_party_reviews/news_mentions/
company_facts/notable_incidents -- it has no way to reproduce this data
itself.

Usage:
  python3 scripts/audits_manual_apply.py
"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    snapshot = yaml.safe_load((DATA / "audits_manual.yaml").read_text())
    retrieved = snapshot["retrieved"]
    exch_dir = DATA / "exchanges"

    by_brand = {}
    for item in snapshot["audits"]:
        by_brand.setdefault(item["brand_id"], []).append(item)

    for brand_id, items in sorted(by_brand.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping", file=sys.stderr)
            continue

        entries = [
            {
                "tier": item["tier"],
                "status": item["status"],
                "auditor": item.get("auditor"),
                "frequency": item.get("frequency"),
                "last_date": item.get("last_date"),
                "summary": item["summary"].strip(),
                "sources": item["sources"],
                "retrieved": retrieved,
            }
            for item in items
        ]

        doc = yaml.safe_load(path.read_text())
        doc["audits"] = entries
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} audit entr{'y' if len(entries) == 1 else 'ies'}")

    print("Done. Remember: this only reflects data/audits_manual.yaml --")
    print("edit that file by hand (with sources) and re-run to add or update entries.")


if __name__ == "__main__":
    main()
