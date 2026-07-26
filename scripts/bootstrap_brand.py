#!/usr/bin/env python3
"""
bootstrap_brand.py - create a minimal exchange file for a brand with no EU
entity in the ESMA data at all, so non-EU sync scripts (fca_sync.py,
fintrac_sync.py, vara_sync.py, mas_sync.py, ...) have a file to attach
country data to.

eu_status: "no_eu_entity" is a sentinel distinct from "authorised"/
"withdrawn" (both of which imply the brand HAS or HAD an EU entity).
scripts/esma_sync.py's stale-file cleanup skips any file with this
sentinel, since such files never appear in its own ESMA-derived brand set
and would otherwise look stale and get deleted. src/pages/exchange/[id].astro
must not render an EU stamp at all for this status (no false claim either
way).

Usage:
  python3 scripts/bootstrap_brand.py <id> "<Brand Name>"
"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    if len(sys.argv) != 3:
        sys.exit('Usage: bootstrap_brand.py <id> "<Brand Name>"')
    bid, brand = sys.argv[1], sys.argv[2]
    path = DATA / "exchanges" / f"{bid}.yaml"
    if path.exists():
        sys.exit(f"{path} already exists — not overwriting")

    doc = {
        "id": bid,
        "brand": brand,
        "eu_status": "no_eu_entity",
        "sources": [],
        "entities": [],
        "countries": {},
    }
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
    print(f"Created {path}")


if __name__ == "__main__":
    main()
