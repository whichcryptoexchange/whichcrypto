#!/usr/bin/env python3
"""
nz_manual_apply.py - apply a manually-verified New Zealand Financial
Service Providers Register (FSPR) snapshot (data/nz_manual.yaml) to
data/exchanges/.

Like Gibraltar and ADGM, New Zealand has NO scripted live sync: the
FSPR's public search tool is a stateful JS application with no fetchable
query-string search, and its bulk-data export requires a manual access
request to the Companies Office. See data/nz_manual.yaml's header for how
the snapshot itself is compiled (individually verified via the live
search tool, not a register export).

Unlike Gibraltar/ADGM, this is an AML-only registration tier -- same
framing as UK MLR/Canada FINTRAC/US FinCEN/Korea FIU, not a genuine
crypto-specific licence -- so we emit
  regime: "New Zealand FSPR registration"
  status: "registered"

NZ is not shared with any other sync script, so this replaces the whole
countries.NZ list each run (no merge-safety filtering needed, unlike
AE/US which share their key with a second regime).

Usage:
  python3 scripts/nz_manual_apply.py
"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    snapshot = yaml.safe_load((DATA / "nz_manual.yaml").read_text())
    retrieved = snapshot["retrieved"]
    source_url = snapshot["source_url"]
    exch_dir = DATA / "exchanges"

    by_brand = {}
    for p in snapshot["providers"]:
        by_brand.setdefault(p["brand_id"], []).append(p)

    for brand_id, items in sorted(by_brand.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping", file=sys.stderr)
            continue

        entries = [
            {
                "status": "registered",
                "regime": "New Zealand FSPR registration",
                "via": "nz_manual",
                "entity": item["entity"],
                "reference": item.get("reference"),
                "since": item.get("since"),
            }
            for item in items
        ]

        doc = yaml.safe_load(path.read_text())
        doc.setdefault("countries", {})["NZ"] = entries

        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "New Zealand FSPR" for s in sources):
            sources.append({
                "name": "New Zealand FSPR",
                "url": source_url,
                "retrieved": retrieved,
            })
        else:
            for s in sources:
                if s.get("name") == "New Zealand FSPR":
                    s["retrieved"] = retrieved
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} NZ entr{'y' if len(entries) == 1 else 'ies'}")

    print("Done. Remember: this only reflects the manual snapshot in data/nz_manual.yaml --")
    print("re-check the live FSPR search tool and update that file before re-running.")


if __name__ == "__main__":
    main()
