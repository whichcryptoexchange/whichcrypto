#!/usr/bin/env python3
"""
gleif_sync.py - GLEIF LEI registry enrichment (company_facts).

Every EEA entity in data/exchanges/*.yaml already carries an LEI (from the
ESMA CASPS.csv). The GLEIF API (api.gleif.org, free, public, no auth) turns
that LEI into a handful of verifiable facts about the legal entity itself:
registered office, whether the LEI record is currently active, and, when
it isn't, the successor LEI it was retired into.

Two important accuracy notes baked into how this data is labelled, not just
here but on the page that renders it:

1. GLEIF's `creationDate` is when the LEGAL ENTITY was created at its
   national registrar -- not when the consumer brand was founded. A
   subsidiary can be created years after the brand itself started trading
   (or re-created after a restructuring). We store it as
   entity_creation_date and the page must label it "Entity registered"
   or similar, never "Founded".

2. `registration.status` (ISSUED/LAPSED/RETIRED/MERGED/...) describes the
   LEI record's own lifecycle, not the company's solvency or trading
   status. A RETIRED/MERGED LEI usually just means the entity re-registered
   under a new LEI (routine), not necessarily a business event -- render
   the successor pointer as a fact, not an alarm.

This writes a new top-level `company_facts` key (list, one entry per LEI
seen in that brand's entities), independent of the `entities` key itself.
scripts/esma_sync.py must preserve this key when it regenerates a file from
CASPS.csv, the same way it already preserves third_party_reviews and
news_mentions -- it has no way to reproduce this data itself.

Usage:
  python3 scripts/gleif_sync.py
"""
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

import yaml

API = "https://api.gleif.org/api/v1/lei-records"
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def fetch_lei(lei):
    req = urllib.request.Request(f"{API}/{lei}", headers={"Accept": "application/vnd.api+json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def to_company_fact(lei, record):
    attrs = record["data"]["attributes"]
    entity = attrs["entity"]
    reg = attrs["registration"]
    address = entity.get("headquartersAddress") or entity.get("legalAddress") or {}
    # GLEIF stores whatever script the registrant submitted the address in --
    # a Cyprus or Bulgaria registration is often Greek/Cyrillic. Rather than
    # add a transliteration dependency, drop the city (keep the country,
    # which we can always render in English via COUNTRY_NAMES) when it's
    # not plain ASCII, rather than show a name most readers can't read.
    city = address.get("city")
    if city and not city.isascii():
        city = None
    fact = {
        "lei": lei,
        "registered_office": {"city": city, "country": address.get("country")},
        "entity_status": (entity.get("status") or "").lower() or None,
        "registration_status": (reg.get("status") or "").lower() or None,
    }
    if entity.get("creationDate"):
        fact["entity_creation_date"] = entity["creationDate"][:10]
    successor_lei = (entity.get("successorEntity") or {}).get("lei")
    if successor_lei:
        fact["successor_lei"] = successor_lei
    return fact


def main():
    as_of = dt.date.today().isoformat()
    exch_dir = DATA / "exchanges"
    cache = {}

    for path in sorted(exch_dir.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text()) or {}
        leis = [e["lei"] for e in (doc.get("entities") or []) if e.get("lei")]
        if not leis:
            continue

        facts = []
        for lei in leis:
            if lei not in cache:
                try:
                    cache[lei] = to_company_fact(lei, fetch_lei(lei))
                except urllib.error.HTTPError as e:
                    print(f"  WARNING: GLEIF lookup failed for LEI {lei} ({path.stem}): {e}", file=sys.stderr)
                    cache[lei] = None
                time.sleep(0.15)
            if cache[lei]:
                facts.append({**cache[lei], "retrieved": as_of})

        if not facts:
            print(f"  {path.stem}: no GLEIF facts resolved, leaving file untouched")
            continue

        doc["company_facts"] = facts
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {path.stem}: wrote {len(facts)} company fact{'s' if len(facts) != 1 else ''}")

    print("Done.")


if __name__ == "__main__":
    main()
