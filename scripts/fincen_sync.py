#!/usr/bin/env python3
"""
fincen_sync.py - US FinCEN MSB Registrant Search ingestion (US country data).

Unlike FINTRAC, FinCEN has no bulk registry export -- registrants are only
searchable one at a time via https://msb.fincen.gov/ (MSB Registrant
Search). This script looks up each brand's pinned BSA ID(s) from
data/fincen_reg_map.yaml live, one request per ID, and re-derives current
status from the result.

The US regime nuance this script encodes: MSB registration under the Bank
Secrecy Act is anti-money-laundering supervision, not a licence -- same
framing as Canada FINTRAC. We therefore emit
  regime: "US FinCEN MSB registration"
  status: "registered"
and site copy must not describe these as "licensed". State-level money
transmitter licensing (up to 50 separate regimes) is a real second layer
that exists in the US but has no single national register, so it is out of
scope here -- same reasoning that already excludes Canada's provincial
securities-dealer layer and the UK's pre-2026 cryptoasset regime.

FinCEN's own MSB Registrant Search prominently warns that fraudsters
register shell companies using recognisable brand names to appear
"FinCEN approved" -- data/fincen_reg_map.yaml's header documents the shell
cluster we found and excluded during curation. This script only ever
touches BSA IDs that are explicitly pinned there; it never adds brands or
IDs on its own.

Each US entry is appended to that brand's countries.US list (a list, same
shape as Canada/Dubai/Singapore) -- a brand can have more than one US MSB
registration (e.g. a domestic subsidiary plus its foreign parent).
scripts/esma_sync.py preserves this key when it regenerates the same files
from the EEA/ESMA source.

Usage:
  python3 scripts/fincen_sync.py
"""
import datetime as dt
import html as htmlmod
import http.cookiejar
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FORM_URL = "https://msb.fincen.gov/msbstateselector.php"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

ROW_RE = re.compile(r'<tr class="tr(?:Gray|White)">(.*?)</tr>', re.S)
CELL_RE = re.compile(r'<td[^>]*>(.*?)</td>', re.S)
BSA_ID_RE = re.compile(r"ID=(\d+)")


def make_opener():
    # The search only returns rows for a request carrying session cookies
    # from a prior GET of the same page -- a bare POST (no cookie jar)
    # silently just re-renders the empty search form. Discovered by
    # comparing a cookie-less request (0 result rows) against one primed
    # with a GET first (real rows) against the same query.
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.open(urllib.request.Request(FORM_URL, headers={"User-Agent": UA}), timeout=30).read()
    return opener


def clean_cell(c):
    c = re.sub(r"<[^>]+>", "", c)
    return htmlmod.unescape(c).replace("\xa0", " ").strip()


def parse_rows(html_):
    rows = []
    for row_html in ROW_RE.findall(html_):
        cells = CELL_RE.findall(row_html)
        if len(cells) < 13:
            continue
        bsa_m = BSA_ID_RE.search(cells[0])
        rows.append({
            "bsa_id": bsa_m.group(1) if bsa_m else None,
            "legal_name": clean_cell(cells[0]),
            "dba_name": clean_cell(cells[1]),
            "city": clean_cell(cells[3]),
            "state": clean_cell(cells[4]),
            "activities": clean_cell(cells[6]),
            "auth_sign_date": clean_cell(cells[11]),
        })
    return rows


def search_by_name(opener, name):
    # FinCEN's own search requires a business name (or alias/address/etc) --
    # a BSA ID alone isn't a valid standalone query, it only narrows a
    # name-based search. We search by the brand's display name (the same
    # term data/fincen_reg_map.yaml's pins were originally discovered
    # under) and then pick out the pinned BSA ID from the results.
    data = urllib.parse.urlencode({
        "SrchBSAID": "", "SrchBusinessName": name, "SrchAlias": "",
        "SrchMSBAddress": "", "SrchMSBCity": "", "SrchMSBState": "",
        "SrchMSBZipCode": "", "SrchSrvOffered": "", "SrchSrvState": "",
        "SrchForeignCode": "",
    }).encode()
    req = urllib.request.Request(FORM_URL, data=data, headers={
        "User-Agent": UA, "Content-Type": "application/x-www-form-urlencoded",
        "Referer": FORM_URL,
    })
    html_ = opener.open(req, timeout=30).read().decode("utf-8", errors="replace")
    return parse_rows(html_)


def find_bsa_id(opener, name, bsa_id):
    for row in search_by_name(opener, name):
        if row["bsa_id"] == str(bsa_id):
            return row
    return None


def iso_date(mmddyyyy):
    if not mmddyyyy:
        return None
    try:
        return dt.datetime.strptime(mmddyyyy, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def to_us_entry(row, bsa_id):
    if "409" not in row["activities"].split():
        print(f"  WARNING: BSA ID {bsa_id} ({row['legal_name']}) no longer lists "
              f"Money Transmitter (409) among activities {row['activities']!r} -- skipping",
              file=sys.stderr)
        return None
    entity = row["dba_name"] or row["legal_name"]
    return {
        "status": "registered",
        "regime": "US FinCEN MSB registration",
        "via": "msb_register",
        "entity": entity,
        "reg_number": bsa_id,
        "since": iso_date(row["auth_sign_date"]),
    }


def main():
    as_of = dt.date.today().isoformat()
    reg_map = yaml.safe_load((DATA / "fincen_reg_map.yaml").read_text()) or {}
    exch_dir = DATA / "exchanges"
    opener = make_opener()

    for brand_id, regs in sorted(reg_map.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping (brand_map.yaml id mismatch?)",
                  file=sys.stderr)
            continue
        brand_name = (yaml.safe_load(path.read_text()) or {}).get("brand", brand_id)

        entries = []
        for item in regs:
            bsa_id = str(item["bsa_id"])
            row = find_bsa_id(opener, brand_name, bsa_id)
            time.sleep(0.3)
            if not row:
                print(f"  WARNING: BSA ID {bsa_id} for {brand_id} not found in current live search",
                      file=sys.stderr)
                continue
            entry = to_us_entry(row, bsa_id)
            if entry:
                entries.append(entry)

        if not entries:
            print(f"  {brand_id}: no valid US entries, leaving file untouched")
            continue

        doc = yaml.safe_load(path.read_text())
        doc.setdefault("countries", {})["US"] = entries
        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "US FinCEN MSB Registrant Search" for s in sources):
            sources.append({
                "name": "US FinCEN MSB Registrant Search",
                "url": "https://msb.fincen.gov/",
                "retrieved": as_of,
            })
        else:
            for s in sources:
                if s.get("name") == "US FinCEN MSB Registrant Search":
                    s["retrieved"] = as_of
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} US entr{'y' if len(entries) == 1 else 'ies'}")

    print("Done.")


if __name__ == "__main__":
    main()
