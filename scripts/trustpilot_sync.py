#!/usr/bin/env python3
"""
trustpilot_sync.py - Trustpilot rating ingestion, via Trustpilot's public
Business Units API (GET /v1/business-units/find?name=<domain>).

Third-party sentiment data, not a regulatory fact -- see
appstore_sync.py's docstring for the third_party_reviews discipline this
follows (explicit attribution, never a site-computed score).

Unlike App Store IDs, no curated per-brand map is needed: this looks up
each brand's Trustpilot business unit directly by domain, derived from
the same `website` field brandWebsite() validates in src/lib/data.js --
Trustpilot's domain lookup is precise enough not to need the
name-search workaround appstore_id_map.yaml exists for. A brand with no
verified website, or whose domain has no Trustpilot business unit / no
reviews, is left untouched rather than guessed at.

Requires TRUSTPILOT_API_KEY (sign up for a free Trustpilot Business
Account, generate a key in the Developer Portal: developers.trustpilot.com).

NOTE: the exact response field names below (numberOfReviews.total,
score.trustScore) are best-effort from Trustpilot's docs, not yet
confirmed against a live response -- check the first real run's output
against the actual JSON shape and adjust before trusting it at scale.

Usage:
  TRUSTPILOT_API_KEY=xxx python3 scripts/trustpilot_sync.py
"""
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
FIND_URL = "https://api.trustpilot.com/v1/business-units/find"


def normalize_domain(raw):
    if not raw:
        return None
    candidate = raw.split("|")[0].split("\n")[0].strip()
    if not re.match(r"^https?://", candidate, re.I):
        candidate = f"https://{candidate}"
    try:
        host = urllib.parse.urlparse(candidate).hostname
    except ValueError:
        return None
    if not host:
        return None
    return host.lower()[4:] if host.lower().startswith("www.") else host.lower()


def website_for(doc):
    candidates = [doc.get("website")] + [e.get("website") for e in doc.get("entities", [])]
    for c in candidates:
        d = normalize_domain(c)
        if d:
            return d
    return None


def fetch(domain, api_key):
    url = f"{FIND_URL}?name={urllib.parse.quote(domain)}"
    req = urllib.request.Request(url, headers={"apikey": api_key})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main():
    api_key = os.environ.get("TRUSTPILOT_API_KEY")
    if not api_key:
        sys.exit("Set TRUSTPILOT_API_KEY (sign up at developers.trustpilot.com)")
    as_of = dt.date.today().isoformat()
    exch_dir = DATA / "exchanges"

    for path in sorted(exch_dir.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        domain = website_for(doc)
        if not domain:
            continue

        try:
            data = fetch(domain, api_key)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue  # no Trustpilot business unit for this domain
            print(f"  ERROR fetching Trustpilot for {doc['id']} ({domain}): {e}", file=sys.stderr)
            continue

        count = (data.get("numberOfReviews") or {}).get("total")
        score = (data.get("score") or {}).get("trustScore")
        if not count or not score:
            continue

        reviews = doc.setdefault("third_party_reviews", [])
        other = [e for e in reviews if e.get("source") != "Trustpilot"]
        doc["third_party_reviews"] = other + [{
            "source": "Trustpilot",
            "rating": score,
            "count": count,
            "url": f"https://www.trustpilot.com/review/{domain}",
            "retrieved": as_of,
        }]
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {doc['id']}: {score} ({count} reviews)")
        time.sleep(0.2)

    print("Done.")


if __name__ == "__main__":
    main()
