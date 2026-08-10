#!/usr/bin/env python3
"""
appstore_sync.py - Apple App Store rating ingestion, via the public,
unauthenticated iTunes Lookup API (no signup, no API key).

This is third-party sentiment data, not a regulatory fact -- kept in its
own countries-sibling key, `third_party_reviews`, never mixed into
`countries`/`sources` which are reserved for regulator-sourced facts.
Each entry is explicitly attributed (source name, rating, review count,
retrieved date, link to the original) so a reader can verify it
themselves, same discipline as everywhere else on this site -- this is
NOT a site-computed "sentiment score".

data/appstore_id_map.yaml pins brand_id -> numeric App Store track ID
(verified by hand -- the App Store's own search is not reliable name
matching, see that file's header). This script only re-fetches the
live rating/count for already-verified IDs.

Merge-safe: `third_party_reviews` can also hold Trustpilot entries (see
trustpilot_sync.py) -- this only ever replaces its own "App Store"
slice, same pattern as vara_sync.py/adgm_manual_apply.py sharing "AE".

Usage:
  python3 scripts/appstore_sync.py
"""
import datetime as dt
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOOKUP_URL = "https://itunes.apple.com/lookup"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def fetch(app_id, country):
    url = f"{LOOKUP_URL}?id={app_id}&country={country}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def main():
    id_map = yaml.safe_load((DATA / "appstore_id_map.yaml").read_text()) or {}
    exch_dir = DATA / "exchanges"
    as_of = dt.date.today().isoformat()

    for brand_id, item in sorted(id_map.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping", file=sys.stderr)
            continue

        app_id, country = item["app_id"], item["country"]
        try:
            data = fetch(app_id, country)
        except urllib.error.HTTPError as e:
            print(f"  ERROR fetching App Store id {app_id} for {brand_id}: {e}", file=sys.stderr)
            continue

        results = data.get("results") or []
        if not results:
            print(f"  WARNING: App Store id {app_id} for {brand_id} returned no result — "
                  f"app may have been pulled from the {country} store", file=sys.stderr)
            continue
        app = results[0]
        rating = app.get("averageUserRating")
        count = app.get("userRatingCount")
        if not rating or not count:
            print(f"  {brand_id}: no rating data yet, leaving file untouched")
            continue

        doc = yaml.safe_load(path.read_text())
        reviews = doc.setdefault("third_party_reviews", [])
        other = [e for e in reviews if e.get("source") != "App Store"]
        doc["third_party_reviews"] = other + [{
            "source": "App Store",
            "rating": round(rating, 2),
            "count": count,
            "url": app.get("trackViewUrl"),
            "retrieved": as_of,
        }]
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: {rating:.2f} ({count} ratings)")
        time.sleep(0.3)

    print("Done.")


if __name__ == "__main__":
    main()
