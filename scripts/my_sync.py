#!/usr/bin/env python3
"""
my_sync.py - Malaysia Securities Commission Digital Asset Exchange (DAX)
ingestion.

The SC publishes the "List of Registered Digital Asset Exchanges" as a
plain HTML page with four tables: (A) currently registered DAX operators,
and (B)/(C)/(D) historical not-permitted-to-continue / transitional lists.
Only table A is current -- same "don't touch the withdrawn/historical
tables" discipline as sfc_sync.py. No bot protection, no session cookies.

A Recognized Market Operator - Digital Asset Exchange registration under
the Capital Markets and Services Act is a genuine crypto-specific licence
(minimum RM5,000,000 paid-up capital, fit-and-proper key personnel,
AML/CFT compliance) -- same tier as VARA/MAS/SFC/GFSC/FSA, not an AML-only
registration. We therefore emit
  regime: "Malaysia SC Recognized Market Operator - Digital Asset Exchange"
  status: "licensed"

The page has no reference/registration number column, only entity name and
address, so matching against data/my_reg_map.yaml is by legal entity name.

Usage:
  python3 scripts/my_sync.py
"""
import datetime as dt
import html as htmlmod
import pathlib
import re
import sys
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PAGE_URL = "https://www.sc.com.my/regulation/guidelines/recognizedmarkets/list-of-registered-digital-asset-exchanges"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def clean(cell):
    cell = re.sub(r"<[^>]+>", " ", cell)
    cell = htmlmod.unescape(cell).replace("\xa0", " ")
    return re.sub(r"\s+", " ", cell).strip()


def fetch_registered_table():
    req = urllib.request.Request(PAGE_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        html_ = r.read().decode("utf-8", errors="replace")

    marker = html_.find("Registered Recognized Market Operators")
    if marker == -1:
        raise RuntimeError("'Registered Recognized Market Operators' marker not found -- page structure changed")
    table_start = html_.find("<table", marker)
    table_end = html_.find("</table>", table_start)
    table_html = html_[table_start:table_end]

    names = set()
    for row_html in re.findall(r"<tr.*?</tr>", table_html, re.S):
        cells = [clean(c) for c in re.findall(r"<t[dh].*?</t[dh]>", row_html, re.S)]
        if len(cells) < 2 or not cells[1] or cells[1] == "Name":
            continue
        names.add(cells[1])
    return names


def main():
    as_of = dt.date.today().isoformat()
    reg_map = yaml.safe_load((DATA / "my_reg_map.yaml").read_text()) or []
    exch_dir = DATA / "exchanges"

    print("Fetching live Malaysia SC registered DAX table...", file=sys.stderr)
    registered = fetch_registered_table()
    print(f"Found {len(registered)} registered DAX operators", file=sys.stderr)

    for item in reg_map:
        brand_id, entity = item["brand_id"], item["entity"]
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping (my_reg_map.yaml id mismatch?)",
                  file=sys.stderr)
            continue
        if entity not in registered:
            print(f"  WARNING: {entity} for {brand_id} not found in the current registered DAX table — "
                  f"may have been de-registered", file=sys.stderr)
            continue

        doc = yaml.safe_load(path.read_text())
        doc.setdefault("countries", {})["MY"] = [{
            "status": "licensed",
            "regime": "Malaysia SC Recognized Market Operator - Digital Asset Exchange",
            "via": "my_sc_register",
            "entity": entity,
            "since": None,
        }]
        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "Malaysia SC List of Registered Digital Asset Exchanges" for s in sources):
            sources.append({
                "name": "Malaysia SC List of Registered Digital Asset Exchanges",
                "url": PAGE_URL,
                "retrieved": as_of,
            })
        else:
            for s in sources:
                if s.get("name") == "Malaysia SC List of Registered Digital Asset Exchanges":
                    s["retrieved"] = as_of
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote MY entry")

    print("Done.")


if __name__ == "__main__":
    main()
