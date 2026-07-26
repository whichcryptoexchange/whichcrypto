#!/usr/bin/env python3
"""
mas_sync.py - Singapore MAS Financial Institutions Directory ingestion
(SG country data).

Scope: Major Payment Institution licensees authorised for the Digital
Payment Token Service activity under the Payment Services Act 2019. Like
the Dubai VARA licence, this is a genuine crypto-specific licence (not an
AML-only registration like the UK/Canada tiers), so we emit:
  regime: "Singapore MAS MPI Licence (DPT)"
  status: "licensed"

The directory (https://eservices.mas.gov.sg/fid/institution?...) is a
client-side app, but its results are fetched from a server-rendered HTML
partial endpoint (/fid/custom/resultpartial) with plain query params — no
API key, no JS execution needed. This script re-fetches and re-parses
that endpoint fresh each run, paging through however many pages the
directory currently reports (data-total on the first page).

No licence-issue date is exposed anywhere in this directory, unlike the
UK/Canada/Dubai sources — "since" is always null here.

Each SG entry is appended to that brand's countries.SG list (a list, unlike
EEA country entries in data/exchanges/*.yaml, which are single objects --
Paxos alone has two separate MAS-licensed entities). scripts/esma_sync.py
preserves this key (and the whole file, for brands bootstrapped via
scripts/bootstrap_brand.py with no EU entity at all) when it regenerates
files from the EEA/ESMA source.

Usage:
  python3 scripts/mas_sync.py
"""
import datetime as dt
import html as htmlmod
import pathlib
import re
import sys
import urllib.parse
import urllib.request

import yaml

LIST_URL = "https://eservices.mas.gov.sg/fid/institution"
PARTIAL_URL = "https://eservices.mas.gov.sg/fid/custom/resultpartial"
QUERY = {
    "sector": "Payments",
    "category": "Major Payment Institution",
    "activity": "Digital Payment Token Service",
}
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def fetch(url, params):
    qs = "&".join(f"{k}={urllib.parse.quote(v)}" for k, v in params.items())
    req = urllib.request.Request(f"{url}?{qs}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_directory():
    first = fetch(LIST_URL, QUERY)
    m = re.search(r'data-total="(\d+)"', first)
    total_pages = int(m.group(1)) if m else 1

    entries = {}
    for page in range(1, total_pages + 1):
        html_ = fetch(PARTIAL_URL, {**QUERY, "term": "", "subactivity": "", "page": str(page)})
        for match in re.finditer(
            r'<a href="/fid/institution/detail/([^"]+)">\s*<h3 class="header-inner-2">([^<]+)</h3>',
            html_,
        ):
            ref, name = match.groups()
            entries[ref] = htmlmod.unescape(name)
    return entries


def main():
    as_of = dt.date.today().isoformat()
    reg_map = yaml.safe_load((DATA / "mas_reg_map.yaml").read_text()) or {}
    exch_dir = DATA / "exchanges"

    print("Fetching MAS Financial Institutions Directory...", file=sys.stderr)
    directory = fetch_directory()
    print(f"Loaded {len(directory)} DPT-licensed institution records", file=sys.stderr)

    for brand_id, refs in sorted(reg_map.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping "
                  f"(brand_map.yaml id mismatch, or needs scripts/bootstrap_brand.py first?)",
                  file=sys.stderr)
            continue

        entries = []
        for item in refs:
            reference = str(item["reference"])
            name = directory.get(reference)
            if not name:
                print(f"  WARNING: {reference} for {brand_id} not found in current directory — "
                      f"licence may have lapsed or reference changed", file=sys.stderr)
                continue
            entries.append({
                "status": "licensed",
                "regime": "Singapore MAS MPI Licence (DPT)",
                "via": "mas_register",
                "entity": name,
                "reference": reference,
                "since": None,
            })

        if not entries:
            print(f"  {brand_id}: no valid SG entries, leaving file untouched")
            continue

        doc = yaml.safe_load(path.read_text())
        doc.setdefault("countries", {})["SG"] = entries
        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "Singapore MAS Financial Institutions Directory" for s in sources):
            sources.append({
                "name": "Singapore MAS Financial Institutions Directory",
                "url": LIST_URL,
                "retrieved": as_of,
            })
        else:
            for s in sources:
                if s.get("name") == "Singapore MAS Financial Institutions Directory":
                    s["retrieved"] = as_of
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} SG entr{'y' if len(entries) == 1 else 'ies'}")

    print("Done.")


if __name__ == "__main__":
    main()
