#!/usr/bin/env python3
"""
fintrac_sync.py - Canada FINTRAC MSB Registry ingestion (CA country data).

Unlike the FCA Register, FINTRAC publishes its full Money Services Business
registry as a bulk CSV — no API key, no per-firm lookups. This script
downloads it fresh and looks up each tracked brand's registration number(s)
from data/fintrac_reg_map.yaml.

The Canada regime nuance this script encodes: MSB registration is
anti-money-laundering supervision, not a licence — FINTRAC's own registry
page states registration "does not indicate that FINTRAC endorses or
licenses the business." We therefore emit
  regime: "Canada MSB registration"
  status: "registered"
and site copy must not describe these as "licensed". Crypto trading
platforms may also need separate provincial securities-dealer registration
(CSA/OSC/BCSC etc.) — there's no single national register for that, so it
isn't covered here (same reasoning that ruled out a US country page).

Each CA entry is appended to that brand's countries.CA list (a list, unlike
EEA country entries in data/exchanges/*.yaml, which are single objects — a
brand can have more than one Canadian MSB registration, e.g. a domestic
subsidiary plus its foreign parent). scripts/esma_sync.py preserves this
key when it regenerates the same files from the EEA/ESMA source.

Usage:
  python3 scripts/fintrac_sync.py
"""
import csv
import datetime as dt
import io
import pathlib
import re
import sys
import urllib.request

import yaml

CSV_URL = "https://fintrac-canafe.canada.ca/msb-esm/reg-eng.csv"
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def fetch_registry():
    req = urllib.request.Request(CSV_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    return {row["MSB Registration Number"].strip(): row for row in rows}


def legal_name(org_field):
    m = re.search(r"Legal Name:\s*([^,\n]+)", org_field or "")
    return m.group(1).strip() if m else (org_field or "").strip()


def to_ca_entry(row, reg_number):
    status_raw = (row.get("MSB Registration Status") or "").strip()
    entity = legal_name(row.get("Organization Names (Legal and Operating)"))
    if status_raw != "Registered":
        print(f"  WARNING: {reg_number} ({entity}) is {status_raw!r}, not Registered — skipping",
              file=sys.stderr)
        return None
    return {
        "status": "registered",
        "regime": "Canada MSB registration",
        "via": "msb_register",
        "entity": entity,
        "reg_number": reg_number,
        "since": (row.get("Date Initial MSB Registration Approval") or "").strip() or None,
        "expires": (row.get("MSB Registration Expiry Date") or "").strip() or None,
    }


def main():
    as_of = dt.date.today().isoformat()
    reg_map = yaml.safe_load((DATA / "fintrac_reg_map.yaml").read_text()) or {}
    exch_dir = DATA / "exchanges"

    print("Downloading FINTRAC MSB registry CSV...", file=sys.stderr)
    registry = fetch_registry()
    print(f"Loaded {len(registry)} MSB records", file=sys.stderr)

    for brand_id, regs in sorted(reg_map.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping (brand_map.yaml id mismatch?)",
                  file=sys.stderr)
            continue

        entries = []
        for item in regs:
            reg_number = str(item["reg_number"])
            row = registry.get(reg_number)
            if not row:
                print(f"  WARNING: {reg_number} for {brand_id} not found in current registry export",
                      file=sys.stderr)
                continue
            entry = to_ca_entry(row, reg_number)
            if entry:
                entries.append(entry)

        if not entries:
            print(f"  {brand_id}: no valid CA entries, leaving file untouched")
            continue

        doc = yaml.safe_load(path.read_text())
        doc.setdefault("countries", {})["CA"] = entries
        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "Canada FINTRAC MSB Registry" for s in sources):
            sources.append({
                "name": "Canada FINTRAC MSB Registry",
                "url": "https://fintrac-canafe.canada.ca/msb-esm/reg-eng",
                "retrieved": as_of,
            })
        else:
            for s in sources:
                if s.get("name") == "Canada FINTRAC MSB Registry":
                    s["retrieved"] = as_of
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} CA entr{'y' if len(entries) == 1 else 'ies'}")

    print("Done.")


if __name__ == "__main__":
    main()
