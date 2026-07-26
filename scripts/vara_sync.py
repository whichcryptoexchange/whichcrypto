#!/usr/bin/env python3
"""
vara_sync.py - Dubai VARA public VASP register ingestion (AE country data).

CRITICAL SCOPE CAVEAT: VARA (the Virtual Assets Regulatory Authority) only
licenses businesses for the Emirate of Dubai's mainland. It has NO authority
over Abu Dhabi (regulated separately by the ADGM's FSRA), Dubai's own DIFC
financial free zone (regulated separately by the DFSA), or the rest of the
UAE (federal SCA). There is no single UAE-wide crypto regulator. Filing
this under the "AE" country code is already a simplification (VARA isn't a
national regulator) — every entry emitted here MUST say "Dubai" explicitly
in its regime string, never just "UAE" or "AE", so the scope can't get lost
in a page that only shows the ISO code. Site copy on /ae/ must state
prominently that this reflects Dubai/VARA licensing only.

Unlike the UK FCA and Canada FINTRAC registrations, a VARA VASP Licence is
a genuine, crypto-specific licence (Dubai built a dedicated regulatory
regime for virtual assets from scratch) — not just AML/CTF registration.
We therefore emit:
  regime: "Dubai VARA VASP Licence"
  status: "licensed"

The public register (https://www.vara.ae/en/licenses-and-register/public-register/)
is server-rendered HTML (data-label table cells) with no API or bulk
export — this script re-fetches and re-parses that page fresh each run.

Each AE entry is appended to that brand's countries.AE list (a list, unlike
EEA country entries in data/exchanges/*.yaml, which are single objects — a
brand can have more than one Dubai VASP licence, e.g. Bitpanda's separate
custody and broker-dealer entities). scripts/esma_sync.py preserves this
key when it regenerates the same files from the EEA/ESMA source.

Usage:
  python3 scripts/vara_sync.py
"""
import datetime as dt
import pathlib
import re
import sys
import urllib.request

import yaml

REGISTER_URL = "https://www.vara.ae/en/licenses-and-register/public-register/"
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fetch_register():
    req = urllib.request.Request(REGISTER_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", errors="replace")

    cells = re.findall(r'<td data-label="([^"]+)"[^>]*>(.*?)</td>', html, re.S)
    rows, row = [], {}
    for label, val in cells:
        val = clean(val)
        if label in row:
            rows.append(row)
            row = {}
        row[label] = val
    if row:
        rows.append(row)
    return {row.get("Reference"): row for row in rows if row.get("Reference")}


def parse_date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return dt.datetime.strptime(raw, "%Y/%m/%d").date().isoformat()
    except ValueError:
        return raw


def to_ae_entry(row, reference):
    return {
        "status": "licensed",
        "regime": "Dubai VARA VASP Licence",
        "via": "dubai_vara",
        "entity": row.get("VASP Name") or "",
        "reference": reference,
        "licensed_activities": row.get("Licensed Activities") or None,
        "since": parse_date(row.get("Licence Issued")),
    }


def main():
    as_of = dt.date.today().isoformat()
    reg_map = yaml.safe_load((DATA / "vara_reg_map.yaml").read_text()) or {}
    exch_dir = DATA / "exchanges"

    print("Fetching VARA public register...", file=sys.stderr)
    register = fetch_register()
    print(f"Loaded {len(register)} licensed VASP records", file=sys.stderr)

    for brand_id, refs in sorted(reg_map.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping (brand_map.yaml id mismatch?)",
                  file=sys.stderr)
            continue

        entries = []
        for item in refs:
            reference = str(item["reference"])
            row = register.get(reference)
            if not row:
                print(f"  WARNING: {reference} for {brand_id} not found in current register — "
                      f"licence may have lapsed or reference changed", file=sys.stderr)
                continue
            entries.append(to_ae_entry(row, reference))

        if not entries:
            print(f"  {brand_id}: no valid AE entries, leaving file untouched")
            continue

        doc = yaml.safe_load(path.read_text())
        doc.setdefault("countries", {})["AE"] = entries
        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "Dubai VARA Public Register" for s in sources):
            sources.append({
                "name": "Dubai VARA Public Register",
                "url": REGISTER_URL,
                "retrieved": as_of,
            })
        else:
            for s in sources:
                if s.get("name") == "Dubai VARA Public Register":
                    s["retrieved"] = as_of
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} AE entr{'y' if len(entries) == 1 else 'ies'}")

    print("Done.")


if __name__ == "__main__":
    main()
