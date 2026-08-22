#!/usr/bin/env python3
"""
au_sync.py - AUSTRAC Virtual Asset Service Provider Register (VASPR)
ingestion (AU country data).

VASPR went public in mid-2026 and is a genuinely simple, unauthenticated
JSON API -- no API key, no bot wall, unlike several other sources on this
site (Gibraltar, ADGM, NZ, BVI):
  GET https://online.apps.austrac.gov.au/vaspr/remitters/
      ?searchTerm=<name or ABN>&page=0&orderBy=legalName&pageSize=20
      &direction=1&vasprSearch=true

Registration under the AML/CTF Act is anti-money-laundering supervision
only, not a business licence -- Australia's first dedicated crypto-specific
regime (ASIC AFSL cover for "Digital Asset Platform" / "Tokenised Custody
Platform", under the Corporations Amendment (Digital Assets Framework) Act
2026) is still phasing in and not yet tracked here. We therefore emit
  regime: "AUSTRAC VASP registration"
  status: "registered"
same tier as UK/Canada/US/Korea/New Zealand.

Matching against data/au_reg_map.yaml is by ABN, not name -- AUSTRAC's own
legal names routinely have nothing to do with the consumer brand (Kraken's
AU entity is "Bit Trade Pty Limited"; Binance's is "InvestByBit Pty Ltd").
The search endpoint returns zero results for an unregistered ABN rather
than erroring, and totalCount lets us catch the rarer case of an ABN now
matching more than one record.

VASPR's search response has no registration date field (unlike the FCA's
"Status Effective Date") -- `since` is therefore always null for AU
entries, the same convention already used elsewhere on this site when a
primary source doesn't expose one.

Usage:
  python3 scripts/au_sync.py
"""
import datetime as dt
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

import yaml

BASE = "https://online.apps.austrac.gov.au/vaspr/remitters/"
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def search(term):
    qs = urllib.parse.urlencode({
        "searchTerm": term, "page": 0, "orderBy": "legalName",
        "pageSize": 20, "direction": 1, "vasprSearch": "true",
    })
    req = urllib.request.Request(f"{BASE}?{qs}", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        import json
        return json.load(r)


def to_gb_entry(record, abn):
    entity = record.get("legalName") or ""
    return {
        "status": "registered",
        "regime": "AUSTRAC VASP registration",
        "via": "au_register",
        "entity": entity,
        "abn": abn,
        "since": None,
    }


def main():
    as_of = dt.date.today().isoformat()
    reg_map = yaml.safe_load((DATA / "au_reg_map.yaml").read_text()) or {}
    exch_dir = DATA / "exchanges"
    notable = []

    for brand_id, items in sorted(reg_map.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping (au_reg_map.yaml id mismatch?)",
                  file=sys.stderr)
            continue

        existing_doc = yaml.safe_load(path.read_text()) or {}
        # A hand-added caveat (e.g. explaining a legal name that has
        # nothing to do with the consumer brand) would otherwise be wiped
        # every run, since this script fully replaces countries.AU each
        # time -- carry it forward by ABN rather than losing it silently.
        caveats_by_abn = {
            e.get("abn"): e["caveat"]
            for e in (existing_doc.get("countries", {}).get("AU") or [])
            if e.get("caveat")
        }

        entries = []
        for item in items:
            abn = str(item["abn"])
            try:
                result = search(abn)
            except urllib.error.HTTPError as e:
                print(f"  ERROR searching ABN {abn} for {brand_id}: {e}", file=sys.stderr)
                continue
            data = (result.get("content") or {}).get("data") or []
            total = (result.get("content") or {}).get("totalCount", len(data))
            if not data:
                print(f"  WARNING: ABN {abn} for {brand_id} not found on VASPR — lapsed or deregistered?",
                      file=sys.stderr)
                continue
            if total > 1:
                print(f"  WARNING: ABN {abn} for {brand_id} matched {total} records — expected 1, skipping",
                      file=sys.stderr)
                continue
            record = data[0]
            if record.get("abn") != abn:
                print(f"  WARNING: ABN {abn} for {brand_id} — response ABN {record.get('abn')!r} doesn't match, skipping",
                      file=sys.stderr)
                continue
            entry = to_gb_entry(record, abn)
            if abn in caveats_by_abn:
                entry["caveat"] = caveats_by_abn[abn]
            entries.append(entry)

        if not entries:
            print(f"  {brand_id}: no valid AU entries, leaving file untouched")
            continue

        doc = existing_doc
        old_statuses = {e.get("status") for e in (doc.get("countries", {}).get("AU") or [])}
        new_statuses = {e["status"] for e in entries}
        if old_statuses and old_statuses != new_statuses:
            notable.append(
                f"**{doc.get('brand', brand_id)}**: AUSTRAC VASP status changed "
                f"`{'/'.join(sorted(old_statuses))}` → `{'/'.join(sorted(new_statuses))}`."
            )
        doc.setdefault("countries", {})["AU"] = entries
        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "AUSTRAC VASP Register (VASPR)" for s in sources):
            sources.append({
                "name": "AUSTRAC VASP Register (VASPR)",
                "url": "https://online.apps.austrac.gov.au/vaspr",
                "retrieved": as_of,
            })
        else:
            for s in sources:
                if s.get("name") == "AUSTRAC VASP Register (VASPR)":
                    s["retrieved"] = as_of
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} AU entr{'y' if len(entries) == 1 else 'ies'}")

    print("Done.")
    write_pr_body(notable)


# Read by .github/workflows/au-sync.yml as the PR body (body-path).
def write_pr_body(notable):
    if notable:
        header = f"## 🔴 {len(notable)} notable change{'s' if len(notable) != 1 else ''}\n\n" + \
            "\n".join(f"- {line}" for line in notable) + "\n\n---\n\n"
    else:
        header = "No notable changes this run — routine `retrieved` date refresh only.\n\n---\n\n"
    body = header + (
        "Automated refresh of data/au_reg_map.yaml's pinned ABNs against\n"
        "the live AUSTRAC VASPR. This does NOT discover new brands -- only\n"
        "re-fetches status for entities already curated in au_reg_map.yaml.\n"
        "Review for:\n"
        "  - an ABN that stopped resolving (lapsed/deregistered -- may need\n"
        "    dropping from the map, or check AUSTRAC's registration-actions\n"
        "    page for a cancellation/suspension)\n"
        "  - an ABN now matching more than one record\n"
    )
    (ROOT / ".pr-body.md").write_text(body)


if __name__ == "__main__":
    main()
