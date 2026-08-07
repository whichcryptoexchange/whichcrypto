#!/usr/bin/env python3
"""
adgm_manual_apply.py - apply a manually-verified Abu Dhabi Global Market
(ADGM) FSRA virtual-asset licensee snapshot (data/adgm_manual.yaml) to
data/exchanges/.

Like Gibraltar, ADGM has NO scripted live sync: its register/search
portal (accessrp.adgm.com) returns a hard 403 from an Akamai bot wall --
unlike NY DFS's Cloudflare TLS-fingerprint check, this one didn't yield
to a UA-string fix, so there's no scripted path to the live data. See
data/adgm_manual.yaml's header for how the snapshot itself is compiled
(individually-verified FSP press releases, not a register export) and
why it isn't necessarily exhaustive.

ADGM shares the "AE" country key with Dubai VARA (two different
emirates, two different regulators, neither covering "the wider UAE" --
see [country].astro's isAE branch) so this only ever replaces its own
slice of that array, matched by the "via" field, the same merge-safety
pattern used where NY DFS and FinCEN share "US" (see ny_sync.py).

Usage:
  python3 scripts/adgm_manual_apply.py
"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    snapshot = yaml.safe_load((DATA / "adgm_manual.yaml").read_text())
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
                "regime": "Abu Dhabi ADGM FSRA licence",
                "via": "adgm_manual",
                "entity": item["entity"],
                "licensed_activities": item.get("regulated_activities"),
                "reference": item.get("reference"),
                "since": item.get("since"),
            }
            for item in items
        ]

        doc = yaml.safe_load(path.read_text())
        countries = doc.setdefault("countries", {})
        other = [e for e in countries.get("AE", []) if e.get("via") != "adgm_manual"]
        countries["AE"] = other + entries

        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "ADGM FSRA Public Register" for s in sources):
            sources.append({
                "name": "ADGM FSRA Public Register",
                "url": source_url,
                "retrieved": retrieved,
            })
        else:
            for s in sources:
                if s.get("name") == "ADGM FSRA Public Register":
                    s["retrieved"] = retrieved
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} AE (ADGM) entr{'y' if len(entries) == 1 else 'ies'}")

    print("Done. Remember: this only reflects the manual snapshot in data/adgm_manual.yaml --")
    print("individually verify any new grant against its own press release before adding it there.")


if __name__ == "__main__":
    main()
