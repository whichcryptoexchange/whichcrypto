#!/usr/bin/env python3
"""
gi_manual_apply.py - apply a manually-refreshed Gibraltar GFSC DLT
Providers snapshot (data/gi_manual.yaml) to data/exchanges/.

Unlike every other jurisdiction on this site, Gibraltar has NO scripted
live sync: the GFSC's own register page sits behind a Cloudflare managed
JS challenge that blocks scripted requests outright, the same wall
Canada's CSA/CIRO sit behind (see fintrac_sync.py's docstring). There is
no automated GitHub Actions workflow for this one -- data/gi_manual.yaml
must be updated by hand (someone opens the live page in a real browser,
copies the current list, updates the "providers" list and "retrieved"
date), then this script is run manually to push that snapshot into
data/exchanges/.

A Gibraltar DLT licence is a genuine crypto-specific licence -- same
framing as VARA/MAS/SFC, not an AML-only registration.

Usage:
  python3 scripts/gi_manual_apply.py
"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    snapshot = yaml.safe_load((DATA / "gi_manual.yaml").read_text())
    retrieved = snapshot["retrieved"]
    source_url = snapshot["source_url"]
    exch_dir = DATA / "exchanges"

    by_brand = {}
    for p in snapshot["providers"]:
        by_brand.setdefault(p["brand_id"], []).append(p["entity"])

    for brand_id, entities in sorted(by_brand.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping", file=sys.stderr)
            continue

        doc = yaml.safe_load(path.read_text())
        doc.setdefault("countries", {})["GI"] = [
            {
                "status": "licensed",
                "regime": "Gibraltar DLT licence",
                "via": "gfsc_manual",
                "entity": entity,
                "since": None,
            }
            for entity in entities
        ]
        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "Gibraltar GFSC DLT Providers List" for s in sources):
            sources.append({
                "name": "Gibraltar GFSC DLT Providers List",
                "url": source_url,
                "retrieved": retrieved,
            })
        else:
            for s in sources:
                if s.get("name") == "Gibraltar GFSC DLT Providers List":
                    s["retrieved"] = retrieved
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entities)} GI entr{'y' if len(entities) == 1 else 'ies'}")

    print("Done. Remember: this only reflects the manual snapshot in data/gi_manual.yaml --")
    print("re-check the live GFSC page in a browser and update that file before re-running.")


if __name__ == "__main__":
    main()
