#!/usr/bin/env python3
"""
esma_sync.py - normalise ESMA's interim MiCA CASP register into site data.

Source (Tier 1, official):
  https://www.esma.europa.eu/sites/default/files/2024-12/CASPS.csv
  Field definitions:
  https://www.esma.europa.eu/sites/default/files/2024-12/Description_of_the_fields_in_the_interim_MiCA_register.csv

The raw file is messy. Defects observed in the live file on 2026-07-24,
all handled below:
  * UTF-8 BOM on the header row
  * three list-separator styles: "|", " | ", and a literal " I " (capital i)
  * newlines inside quoted service-list fields
  * Greece appearing as both "EL" (Eurostat style) and "GR" (ISO 3166)
  * "SL" typo for Slovenia ("SI")
  * duplicate country codes within one list, duplicate whole rows
  * dates as dd/mm/yyyy and dd.mm.yyyy (sometimes with trailing dot)
  * trailing dots/whitespace in LEI fields; some LEIs absent
  * withdrawn authorisations flagged only by ac_authorisationEndDate

Usage:
  python3 scripts/esma_sync.py --input tests/fixtures/CASPS_sample_2026-07-24.csv
  python3 scripts/esma_sync.py --input /tmp/CASPS.csv   # live file, fetched by CI
"""

import argparse
import csv
import datetime as dt
import io
import json
import pathlib
import re
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# EEA member states reachable by MiCA passporting (EU27 + IS, LI, NO).
EEA = {
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR",
    "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU", "LV", "MT", "NL", "NO",
    "PL", "PT", "RO", "SE", "SI", "SK",
}

# Observed non-ISO codes in the live file -> ISO 3166-1 alpha-2.
COUNTRY_FIXES = {"EL": "GR", "SL": "SI", "UK": "GB"}

# MiCA Title V service letters (Art. 3(1)(16)). Keyword -> canonical code.
SERVICE_KEYWORDS = [
    ("custody and administration", "a"),
    ("operation of a trading platform", "b"),
    ("exchange of crypto-assets for funds", "c"),
    ("crypto-assets for other", "d"),  # covers AMF (FR) truncation ("...for other" with no suffix) and the "exchange for" vs "exchange of" typo
    ("execution of orders", "e"),
    ("placing of crypto-assets", "f"),
    ("reception and transmission", "g"),
    ("advice on crypto", "h"),
    ("portfolio management", "i"),
    ("transfer services", "j"),
]

SERVICE_NAMES = {
    "a": "Custody and administration of crypto-assets",
    "b": "Operation of a trading platform",
    "c": "Exchange of crypto-assets for funds",
    "d": "Exchange of crypto-assets for other crypto-assets",
    "e": "Execution of orders",
    "f": "Placing of crypto-assets",
    "g": "Reception and transmission of orders",
    "h": "Advice on crypto-assets",
    "i": "Portfolio management",
    "j": "Transfer services",
}

# Splits service/country lists on "|", newlines, and a bare " I " separator
# (observed in FMA Austria rows). The " I " pattern requires surrounding
# whitespace so words containing the letter are untouched.
LIST_SPLIT = re.compile(r"\s*\|\s*|\n+|\s+I\s+")


def clean(s: str) -> str:
    return (s or "").replace("\ufeff", "").strip().strip(".").strip()


def primary_alias(raw: str):
    """Some rows list multiple trading names in one field (e.g. "Amdax B.V.|Amdax
    Group|Novelist"). Take the first as the primary commercial name."""
    for tok in LIST_SPLIT.split(raw or ""):
        tok = clean(tok)
        if tok:
            return tok
    return None


def parse_date(raw: str):
    raw = clean(raw)
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%d.%m.%Y"):
        try:
            return dt.datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    print(f"  WARNING: unparseable date {raw!r} left as-is", file=sys.stderr)
    return raw


def parse_countries(raw: str):
    out = []
    for tok in LIST_SPLIT.split(raw or ""):
        tok = clean(tok).upper()
        if not tok:
            continue
        tok = COUNTRY_FIXES.get(tok, tok)
        if len(tok) != 2 or not tok.isalpha():
            print(f"  WARNING: dropping malformed country token {tok!r}", file=sys.stderr)
            continue
        if tok not in out:
            out.append(tok)
    return sorted(out)


def parse_services(raw: str):
    out = []
    for chunk in LIST_SPLIT.split(raw or ""):
        chunk = clean(chunk).lower()
        if not chunk:
            continue
        for kw, code in SERVICE_KEYWORDS:
            if kw in chunk:
                if code not in out:
                    out.append(code)
                break
        else:
            print(f"  WARNING: unmatched service text {chunk[:60]!r}", file=sys.stderr)
    return sorted(out)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def load_brand_map():
    path = DATA / "brand_map.yaml"
    if path.exists():
        return yaml.safe_load(path.read_text()) or {}
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to CASPS.csv (raw ESMA file)")
    ap.add_argument("--as-of", default=dt.date.today().isoformat())
    args = ap.parse_args()

    raw = pathlib.Path(args.input).read_text(encoding="utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    print(f"Read {len(rows)} raw rows")

    brand_map = load_brand_map()

    # Group rows into entities keyed by LEI (fallback: cleaned legal name).
    entities = {}
    seen_rows = set()
    for row in rows:
        lei = clean(row.get("ae_lei", ""))
        legal_name = clean(row.get("ae_lei_name", ""))
        if not legal_name:
            continue
        key = lei or f"NAME:{legal_name}"

        # Whole-row dedupe (duplicate records observed in live file).
        fingerprint = (key, clean(row.get("ac_serviceCode", "")),
                       clean(row.get("ac_authorisationNotificationDate", "")))
        if fingerprint in seen_rows:
            print(f"  note: dropping duplicate row for {legal_name}")
            continue
        seen_rows.add(fingerprint)

        ent = entities.setdefault(key, {
            "lei": lei or None,
            "legal_name": legal_name,
            "commercial_name": primary_alias(row.get("ae_commercial_name", "")),
            "home_state": clean(row.get("ae_homeMemberState", "")).upper() or None,
            "regulator": clean(row.get("ae_competentAuthority", "")) or None,
            "website": clean(row.get("ae_website", "")) or None,
            "records": [],
        })
        end_date = parse_date(row.get("ac_authorisationEndDate", ""))
        ent["records"].append({
            "authorised": parse_date(row.get("ac_authorisationNotificationDate", "")),
            "withdrawn": end_date,
            "status": "withdrawn" if end_date else "authorised",
            "services": parse_services(row.get("ac_serviceCode", "")),
            "passported_to": parse_countries(row.get("ac_serviceCode_cou", "")),
            "last_update": parse_date(row.get("ac_lastupdate", "")),
        })

    print(f"Grouped into {len(entities)} legal entities")

    # Merge entities into brands via the curated brand map; unmapped
    # entities become their own auto-slugged brand.
    brands = {}
    for key, ent in entities.items():
        mapping = brand_map.get(ent["lei"] or "", None)
        if mapping:
            bid, bname = mapping["id"], mapping["brand"]
        else:
            bname = ent["commercial_name"] or ent["legal_name"]
            bid = slugify(bname)
        b = brands.setdefault(bid, {"id": bid, "brand": bname, "entities": []})
        b["entities"].append(ent)

    # Derive the per-country view. A brand counts as "licensed" in an EEA
    # country if any ACTIVE record's home state or passport list covers it.
    for b in brands.values():
        countries = {}
        active = False
        for ent in b["entities"]:
            for rec in ent["records"]:
                if rec["status"] != "authorised":
                    continue
                active = True
                reach = set(rec["passported_to"]) | ({ent["home_state"]} if ent["home_state"] else set())
                for c in sorted(reach & EEA):
                    via = "home_state" if c == ent["home_state"] else "mica_passporting"
                    countries.setdefault(c, {
                        "status": "licensed",
                        "regime": "MiCA",
                        "via": via,
                        "entity": ent["legal_name"],
                    })
        b["eu_status"] = "authorised" if active else "withdrawn"
        b["countries"] = dict(sorted(countries.items()))

    out_dir = DATA / "exchanges"
    out_dir.mkdir(parents=True, exist_ok=True)
    current_ids = set(brands.keys())
    for stale in out_dir.glob("*.yaml"):
        if stale.stem not in current_ids:
            stale.unlink()
    for bid, b in sorted(brands.items()):
        countries = dict(b["countries"])
        other_sources = []
        # Non-EEA data (currently just GB, from fca_sync.py) lives outside
        # this script's own source of truth. Preserve it across
        # regenerations rather than silently dropping it.
        existing_path = out_dir / f"{bid}.yaml"
        if existing_path.exists():
            existing = yaml.safe_load(existing_path.read_text()) or {}
            for cc, entry in (existing.get("countries") or {}).items():
                if cc not in EEA:
                    countries[cc] = entry
            other_sources = [s for s in (existing.get("sources") or [])
                              if s.get("name") != "ESMA interim MiCA register (CASPS.csv)"]
        countries = dict(sorted(countries.items()))

        payload = {
            "id": b["id"],
            "brand": b["brand"],
            "eu_status": b["eu_status"],
            "sources": [{
                "name": "ESMA interim MiCA register (CASPS.csv)",
                "url": "https://www.esma.europa.eu/sites/default/files/2024-12/CASPS.csv",
                "retrieved": args.as_of,
            }, *other_sources],
            "entities": b["entities"],
            "countries": countries,
        }
        existing_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100)
        )

    registry = {
        "generated": args.as_of,
        "source": "https://www.esma.europa.eu/sites/default/files/2024-12/CASPS.csv",
        "brand_count": len(brands),
        "brands": sorted(brands.keys()),
    }
    (DATA / "registry" / "esma.json").write_text(json.dumps(registry, indent=2))
    print(f"Wrote {len(brands)} brand files to {out_dir}")


if __name__ == "__main__":
    main()
