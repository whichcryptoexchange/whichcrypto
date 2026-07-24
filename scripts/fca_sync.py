#!/usr/bin/env python3
"""
fca_sync.py - UK FCA Register ingestion (GB country data).

The UK regime nuance this script encodes: crypto firms currently hold an
MLR *registration* (AML/CTF), not a full licence. Full FSMA authorisation
opens for applications 30 Sep 2026 with the regime expected to start
25 Oct 2027 (source: fca.org.uk, retrieved 2026-07-24). We therefore emit
  regime: "UK MLR registration"
  status: "registered"
for FCA Status "Registered" firms, and site copy must not describe these
as "licensed".

A handful of tracked brands also have a UK entity that holds full FCA
*authorisation* (a fuller regime overall, but not crypto-specific — it may
cover a different regulated activity, e.g. derivatives or general
investment business, for the same corporate group). These render as a
second, clearly distinct tier:
  regime: "UK FCA authorisation"
  status: "authorised"
data/fca_frn_map.yaml can list more than one FRN per brand to capture both.

Each GB entry is appended to that brand's countries.GB list (a list,
unlike EEA country entries in data/exchanges/*.yaml, which are single
objects — GB can genuinely need two simultaneous entries; other countries
never do today). scripts/esma_sync.py preserves this key when it
regenerates the same files from the EEA/ESMA source.

Usage:
  FCA_API_EMAIL=you@example.com FCA_API_KEY=xxx python3 scripts/fca_sync.py
"""
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

import yaml

BASE = "https://register.fca.org.uk/services/V0.1"
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# The FCA Register sits behind Cloudflare bot protection that blocks
# urllib's default User-Agent string.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def api_get(path, email, key):
    req = urllib.request.Request(BASE + path, headers={
        "X-Auth-Email": email, "X-Auth-Key": key,
        "Content-Type": "application/json", "User-Agent": UA,
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def firm_detail(frn, email, key):
    d = api_get(f"/Firm/{frn}", email, key)
    data = d.get("Data") or []
    return data[0] if data else None


def parse_date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return dt.datetime.strptime(raw, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return raw


def to_gb_entry(detail, frn):
    status_raw = (detail.get("Status") or "").strip()
    entity = detail.get("Organisation Name") or ""
    if status_raw == "Registered":
        status, regime = "registered", "UK MLR registration"
    elif status_raw == "Authorised":
        status, regime = "authorised", "UK FCA authorisation"
    else:
        print(f"  WARNING: unrecognised FCA status {status_raw!r} for FRN {frn} ({entity}) — skipping",
              file=sys.stderr)
        return None
    since = parse_date(detail.get("MLRs Status Effective Date")) or parse_date(detail.get("Status Effective Date"))
    return {
        "status": status,
        "regime": regime,
        "via": "uk_register",
        "entity": entity,
        "frn": frn,
        "since": since,
    }


def main():
    email, key = os.environ.get("FCA_API_EMAIL"), os.environ.get("FCA_API_KEY")
    if not (email and key):
        sys.exit("Set FCA_API_EMAIL and FCA_API_KEY (sign up at register.fca.org.uk/Developer/)")
    as_of = dt.date.today().isoformat()

    frn_map = yaml.safe_load((DATA / "fca_frn_map.yaml").read_text()) or {}
    exch_dir = DATA / "exchanges"

    for brand_id, frns in sorted(frn_map.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping (brand_map.yaml id mismatch?)",
                  file=sys.stderr)
            continue

        entries = []
        for item in frns:
            frn = str(item["frn"])
            try:
                detail = firm_detail(frn, email, key)
            except urllib.error.HTTPError as e:
                print(f"  ERROR fetching FRN {frn} for {brand_id}: {e}", file=sys.stderr)
                continue
            if not detail:
                print(f"  WARNING: FRN {frn} for {brand_id} not found", file=sys.stderr)
                continue
            entry = to_gb_entry(detail, frn)
            if entry:
                entries.append(entry)
            time.sleep(0.2)

        if not entries:
            print(f"  {brand_id}: no valid GB entries, leaving file untouched")
            continue

        doc = yaml.safe_load(path.read_text())
        doc.setdefault("countries", {})["GB"] = entries
        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "UK FCA Register" for s in sources):
            sources.append({
                "name": "UK FCA Register",
                "url": "https://register.fca.org.uk/",
                "retrieved": as_of,
            })
        else:
            for s in sources:
                if s.get("name") == "UK FCA Register":
                    s["retrieved"] = as_of
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} GB entr{'y' if len(entries) == 1 else 'ies'}")

    print("Done.")


if __name__ == "__main__":
    main()
