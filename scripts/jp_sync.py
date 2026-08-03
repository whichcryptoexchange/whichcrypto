#!/usr/bin/env python3
"""
jp_sync.py - Japan FSA Crypto-asset Exchange Service Provider ingestion.

The FSA publishes its English-language "List of Registered Crypto-asset
Exchange Service Providers" as a structured .xlsx file at a fixed URL --
no HTML scraping, no bot protection, no session cookies (unlike Canada's
CSA/CIRO tools or Gibraltar's GFSC, which block scripted access outright).
This script fetches that file fresh and looks up each brand's pinned
registration number from data/jp_reg_map.yaml.

Registration under Japan's Payment Services Act (since 2017, post-Mt.Gox)
is a genuine crypto-specific licence -- same tier as Dubai VARA, Singapore
MAS, Hong Kong SFC, and Gibraltar GFSC, not an AML-only registration like
UK/Canada/US. We therefore emit
  regime: "Japan FSA Crypto-asset Exchange Service Provider registration"
  status: "licensed"

Each JP entry is written to that brand's countries.JP list (a list, same
shape as Canada/Dubai/Singapore/US/HK/GI).

The .xlsx is parsed directly via zipfile + stdlib xml.etree rather than a
third-party library (openpyxl etc.) -- the file is a plain OOXML sheet with
a shared-strings table, small enough that a few dozen lines of XML walking
covers it, and this avoids adding a new pip dependency for one script.

Usage:
  python3 scripts/jp_sync.py
"""
import datetime as dt
import pathlib
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
XLSX_URL = "https://www.fsa.go.jp/en/regulated/licensed/en_kasoutuka.xlsx"
PAGE_URL = "https://www.fsa.go.jp/en/regulated/licensed/index.html"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
BUREAU_RE = re.compile(r"(\w+) Financial Bureau", re.I)
NUMBER_RE = re.compile(r"No\.(\d+)")


def excel_date(serial):
    try:
        return (dt.date(1899, 12, 30) + dt.timedelta(days=int(float(serial)))).isoformat()
    except (TypeError, ValueError):
        return None


def fetch_registrations():
    req = urllib.request.Request(XLSX_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()

    z = zipfile.ZipFile(__import__("io").BytesIO(raw))
    sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
    strings = ["".join((t.text or "") for t in si.findall(".//a:t", NS))
               for si in sst.findall("a:si", NS)]
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))

    def row_vals(row):
        vals = {}
        for c in row.findall("a:c", NS):
            col = "".join(ch for ch in c.get("r") if ch.isalpha())
            v = c.find("a:v", NS)
            if v is None:
                continue
            vals[col] = strings[int(v.text)] if c.get("t") == "s" else v.text
        return vals

    registrations = {}
    bureau = None
    for row in sheet.findall(".//a:row", NS):
        d = row_vals(row)
        if d.get("A"):
            m = BUREAU_RE.search(d["A"])
            if m:
                bureau = m.group(1)
        name = d.get("D", "")
        regno = (d.get("B", "") or "").replace("\n", " ")
        num_m = NUMBER_RE.search(regno)
        if not (bureau and name and num_m):
            continue
        key = (bureau, num_m.group(1).zfill(5))
        registrations[key] = {
            "name": name.strip(),
            "since": excel_date(d.get("C")),
            "corporate_number": d.get("E", ""),
        }
    return registrations


def main():
    as_of = dt.date.today().isoformat()
    reg_map = yaml.safe_load((DATA / "jp_reg_map.yaml").read_text()) or []
    exch_dir = DATA / "exchanges"

    print("Fetching live FSA registered crypto-asset exchange list...", file=sys.stderr)
    registrations = fetch_registrations()
    print(f"Found {len(registrations)} registered providers", file=sys.stderr)

    by_brand = {}
    for item in reg_map:
        by_brand.setdefault(item["brand_id"], []).append(item)

    for brand_id, items in sorted(by_brand.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping (jp_reg_map.yaml id mismatch?)",
                  file=sys.stderr)
            continue

        entries = []
        for item in items:
            key = (item["bureau"], str(item["number"]).zfill(5))
            row = registrations.get(key)
            if not row:
                print(f"  WARNING: {item['bureau']} No.{item['number']} for {brand_id} not found in the "
                      f"current FSA register — may have been de-registered", file=sys.stderr)
                continue
            entries.append({
                "status": "licensed",
                "regime": "Japan FSA Crypto-asset Exchange Service Provider registration",
                "via": "jp_fsa_register",
                "entity": row["name"],
                "reference": f"{item['bureau']} No.{item['number']}",
                "since": row["since"],
            })

        if not entries:
            print(f"  {brand_id}: no valid JP entries, leaving file untouched")
            continue

        doc = yaml.safe_load(path.read_text())
        doc.setdefault("countries", {})["JP"] = entries
        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "Japan FSA Registered Crypto-asset Exchange Service Providers List" for s in sources):
            sources.append({
                "name": "Japan FSA Registered Crypto-asset Exchange Service Providers List",
                "url": PAGE_URL,
                "retrieved": as_of,
            })
        else:
            for s in sources:
                if s.get("name") == "Japan FSA Registered Crypto-asset Exchange Service Providers List":
                    s["retrieved"] = as_of
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} JP entr{'y' if len(entries) == 1 else 'ies'}")

    print("Done.")


if __name__ == "__main__":
    main()
