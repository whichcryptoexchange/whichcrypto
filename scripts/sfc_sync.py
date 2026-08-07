#!/usr/bin/env python3
"""
sfc_sync.py - Hong Kong SFC Virtual Asset Trading Platform (VATP) ingestion.

The SFC publishes the "List of licensed virtual asset trading platforms" as
a plain HTML table on a single page -- no bulk export, no bot protection,
no session cookies required (unlike Canada's CSA/CIRO tools, which block
scripted access outright). This script fetches that page fresh, extracts
the licensed-VATP table specifically (identified by the "table-vatp-licensed"
marker div that precedes it -- the page also has separate tables for
applicants, returned/refused/withdrawn applicants, and closing-down
platforms, which are NOT licensed and must not be included), and looks up
each brand's pinned CE Reference from data/sfc_reg_map.yaml.

The Hong Kong regime nuance this script encodes: a VATP licence under the
Securities and Futures Ordinance is a genuine crypto-specific licence
(mandatory since 2023) -- same tier as Dubai VARA and Singapore MAS, not an
AML-only registration like UK/Canada/US. We therefore emit
  regime: "Hong Kong SFC VATP licence"
  status: "licensed"

Each HK entry is appended to that brand's countries.HK list (a list, same
shape as Canada/Dubai/Singapore/US) -- a brand could in principle have more
than one HK-licensed entity.

Usage:
  python3 scripts/sfc_sync.py
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
PAGE_URL = "https://www.sfc.hk/en/Welcome-to-the-Fintech-Contact-Point/Virtual-assets/Virtual-asset-trading-platforms-operators/Lists-of-virtual-asset-trading-platforms"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

CE_REF_RE = re.compile(r"^([A-Z]{3}\d{3})")


def clean(cell):
    cell = re.sub(r"<[^>]+>", " ", cell)
    cell = htmlmod.unescape(cell).replace("\xa0", " ")
    return re.sub(r"\s+", " ", cell).strip()


def fetch_licensed_table():
    req = urllib.request.Request(PAGE_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        html_ = r.read().decode("utf-8", errors="replace")

    marker = html_.find("table-vatp-licensed")
    if marker == -1:
        raise RuntimeError("table-vatp-licensed marker not found -- page structure changed")
    table_start = html_.find("<table", marker)
    table_end = html_.find("</table>", table_start)
    table_html = html_[table_start:table_end]

    rows = {}
    for row_html in re.findall(r"<tr>(.*?)</tr>", table_html, re.S):
        cells = [clean(c) for c in re.findall(r"<td.*?</td>", row_html, re.S)]
        if len(cells) < 5:
            continue
        # The CE Reference cell sometimes contains a second, empty <a> tag
        # pointing at an unrelated/stale reference alongside the real one --
        # stripping all tags first and reading the cleaned visible text
        # (rather than pattern-matching raw hrefs) sidesteps that entirely.
        m = CE_REF_RE.match(cells[0])
        if not m:
            continue
        rows[m.group(1)] = {
            "ce_reference": m.group(1),
            "legal_name": cells[1],
            "platform_name": cells[3],
            "date_of_licence": cells[4],
        }
    return rows


def iso_date(ddmmyyyy):
    ddmmyyyy = ddmmyyyy.strip().rstrip("\xa0 ")
    try:
        return dt.datetime.strptime(ddmmyyyy, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def main():
    as_of = dt.date.today().isoformat()
    reg_map = yaml.safe_load((DATA / "sfc_reg_map.yaml").read_text()) or {}
    exch_dir = DATA / "exchanges"

    print("Fetching live SFC licensed-VATP table...", file=sys.stderr)
    licensed = fetch_licensed_table()
    print(f"Found {len(licensed)} licensed VATPs", file=sys.stderr)

    for brand_id, regs in sorted(reg_map.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping (brand_map.yaml id mismatch?)",
                  file=sys.stderr)
            continue

        entries = []
        for item in regs:
            ce_ref = str(item["ce_reference"])
            row = licensed.get(ce_ref)
            if not row:
                print(f"  WARNING: CE Reference {ce_ref} for {brand_id} not found in the current "
                      f"licensed-VATP table — may have been removed or delisted", file=sys.stderr)
                continue
            entries.append({
                "status": "licensed",
                "regime": "Hong Kong SFC VATP licence",
                "via": "sfc_register",
                "entity": row["platform_name"] or row["legal_name"],
                "reference": ce_ref,
                "since": iso_date(row["date_of_licence"]),
            })

        if not entries:
            print(f"  {brand_id}: no valid HK entries, leaving file untouched")
            continue

        doc = yaml.safe_load(path.read_text())
        doc.setdefault("countries", {})["HK"] = entries
        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "Hong Kong SFC VATP List" for s in sources):
            sources.append({
                "name": "Hong Kong SFC VATP List",
                "url": PAGE_URL,
                "retrieved": as_of,
            })
        else:
            for s in sources:
                if s.get("name") == "Hong Kong SFC VATP List":
                    s["retrieved"] = as_of
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} HK entr{'y' if len(entries) == 1 else 'ies'}")

    print("Done.")


if __name__ == "__main__":
    main()
