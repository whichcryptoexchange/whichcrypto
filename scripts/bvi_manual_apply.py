#!/usr/bin/env python3
"""
bvi_manual_apply.py - apply a manually-verified British Virgin Islands
(BVI) Financial Services Commission (FSC) Virtual Assets Service
Providers register snapshot (data/bvi_manual.yaml) to data/exchanges/.

Like Gibraltar and ADGM, the BVI has NO scripted live sync: the FSC's
register page (bvifsc.vg/regulated-entities-vasp) returns a hard 403 to
scripted requests even with a realistic browser User-Agent and referer
header -- confirmed directly, not assumed. See data/bvi_manual.yaml's
header for how the snapshot itself is compiled and what it deliberately
excludes.

A BVI VASP registration is a genuine crypto-specific licence -- same
framing as VARA/MAS/SFC/Gibraltar/ADGM, not an AML-only registration.

BVI's "VG" country key isn't shared with any other sync script, so this
replaces the whole countries.VG list each run (no merge-safety filter
needed, same as gi_manual_apply.py).

Usage:
  python3 scripts/bvi_manual_apply.py
"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    snapshot = yaml.safe_load((DATA / "bvi_manual.yaml").read_text())
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
                "status": "licensed",
                "regime": "BVI VASP registration",
                "via": "bvi_manual",
                "entity": item["entity"],
                "licensed_activities": item.get("regulated_activities"),
                "since": None,
            }
            for item in items
        ]

        doc = yaml.safe_load(path.read_text())
        doc.setdefault("countries", {})["VG"] = entries

        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "BVI FSC VASP Register" for s in sources):
            sources.append({
                "name": "BVI FSC VASP Register",
                "url": source_url,
                "retrieved": retrieved,
            })
        else:
            for s in sources:
                if s.get("name") == "BVI FSC VASP Register":
                    s["retrieved"] = retrieved
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} VG entr{'y' if len(entries) == 1 else 'ies'}")

    print("Done. Remember: this only reflects the manual snapshot in data/bvi_manual.yaml --")
    print("re-check the live FSC register pages and update that file before re-running.")


if __name__ == "__main__":
    main()
