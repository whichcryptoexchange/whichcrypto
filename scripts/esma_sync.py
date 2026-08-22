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

    # Notable changes -- a status actually flipping, a brand appearing or
    # disappearing -- versus routine `retrieved` date bumps, which are the
    # vast majority of every run and never worth a second look. Surfaced
    # in the PR body (see write_pr_body below) so a real change is visible
    # the moment the PR opens, not just discoverable by reading the diff.
    notable = []

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
        if stale.stem in current_ids:
            continue
        # Brands bootstrapped by scripts/bootstrap_brand.py (no EU entity at
        # all) are never in current_ids since they never appear in ESMA
        # data — that's not staleness, don't delete them.
        try:
            existing = yaml.safe_load(stale.read_text()) or {}
        except yaml.YAMLError:
            existing = {}
        if existing.get("eu_status") == "no_eu_entity":
            continue
        # A brand can drop out of CASPS.csv entirely (authorisation
        # lapsed, brand delisted) while still carrying data this script
        # doesn't own: non-EEA countries, or fields owned entirely by
        # other scripts (company_facts, notable_incidents, audits,
        # third_party_reviews, news_mentions). Deleting the whole file
        # would silently take all of that down with it too -- caught via
        # a real case (Altlift s.r.o, GLEIF company_facts) before this
        # ever reached main. Only actually delete when there's nothing
        # else worth keeping; otherwise demote to no_eu_entity so the
        # brand survives with everything ESMA doesn't own.
        non_eea_countries = {cc: v for cc, v in (existing.get("countries") or {}).items() if cc not in EEA}
        other_owned_fields = {
            k: existing[k] for k in
            ("third_party_reviews", "news_mentions", "company_facts", "notable_incidents", "audits",
             "scam_clones", "risk_summary_url")
            if k in existing
        }
        if not non_eea_countries and not other_owned_fields:
            stale.unlink()
            continue
        demoted = {
            "id": existing.get("id", stale.stem),
            "brand": existing.get("brand", stale.stem),
            "eu_status": "no_eu_entity",
            "sources": [s for s in (existing.get("sources") or [])
                        if s.get("name") != "ESMA interim MiCA register (CASPS.csv)"],
            "entities": [],
            "countries": non_eea_countries,
            **other_owned_fields,
        }
        stale.write_text(yaml.safe_dump(demoted, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {stale.stem}: dropped from ESMA source, demoted to no_eu_entity "
              f"(preserved {', '.join(other_owned_fields) or 'non-EEA countries'})", file=sys.stderr)
        notable.append(
            f"**{demoted['brand']}** dropped out of the ESMA MiCA register entirely "
            f"(was `{existing.get('eu_status')}`) — its EU authorisation record is gone, not just withdrawn."
        )
    for bid, b in sorted(brands.items()):
        countries = dict(b["countries"])
        other_sources = []
        # Non-EEA data (currently just GB, from fca_sync.py) lives outside
        # this script's own source of truth. Preserve it across
        # regenerations rather than silently dropping it.
        existing_path = out_dir / f"{bid}.yaml"
        third_party_reviews = None
        news_mentions = None
        company_facts = None
        notable_incidents = None
        audits = None
        scam_clones = None
        risk_summary_url = None
        old_eu_status = None
        is_new_file = not existing_path.exists()
        if existing_path.exists():
            existing = yaml.safe_load(existing_path.read_text()) or {}
            old_eu_status = existing.get("eu_status")
            for cc, entry in (existing.get("countries") or {}).items():
                if cc not in EEA:
                    countries[cc] = entry
            other_sources = [s for s in (existing.get("sources") or [])
                              if s.get("name") != "ESMA interim MiCA register (CASPS.csv)"]
            # Fields owned by other sync scripts (appstore_sync.py,
            # news_sync.py, gleif_sync.py, notable_incidents_manual_apply.py,
            # audits_manual_apply.py) or hand-curated directly (risk_summary_url,
            # verified brand-by-brand -- see the CoinJar example) -- this
            # script doesn't know how to produce any of these, so preserve
            # whatever's already on disk rather than dropping it.
            third_party_reviews = existing.get("third_party_reviews")
            news_mentions = existing.get("news_mentions")
            company_facts = existing.get("company_facts")
            notable_incidents = existing.get("notable_incidents")
            audits = existing.get("audits")
            scam_clones = existing.get("scam_clones")
            risk_summary_url = existing.get("risk_summary_url")
        countries = dict(sorted(countries.items()))

        payload = {
            "id": b["id"],
            "brand": b["brand"],
            "eu_status": b["eu_status"],
            **({"risk_summary_url": risk_summary_url} if risk_summary_url is not None else {}),
            "sources": [{
                "name": "ESMA interim MiCA register (CASPS.csv)",
                "url": "https://www.esma.europa.eu/sites/default/files/2024-12/CASPS.csv",
                "retrieved": args.as_of,
            }, *other_sources],
            "entities": b["entities"],
            "countries": countries,
        }
        if third_party_reviews is not None:
            payload["third_party_reviews"] = third_party_reviews
        if news_mentions is not None:
            payload["news_mentions"] = news_mentions
        if company_facts is not None:
            payload["company_facts"] = company_facts
        if notable_incidents is not None:
            payload["notable_incidents"] = notable_incidents
        if audits is not None:
            payload["audits"] = audits
        if scam_clones is not None:
            payload["scam_clones"] = scam_clones
        existing_path.write_text(
            yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100)
        )

        # New brand files are excluded here on purpose -- ESMA's CSV has
        # hundreds of tiny regional banks that dip in and out, and a
        # never-before-seen ID is almost always one of those, not a
        # recognisable brand worth a post. A real status change on a
        # brand we already track is a much stronger signal either way.
        new_eu_status = b["eu_status"]
        if not is_new_file and old_eu_status != new_eu_status:
            if new_eu_status == "authorised":
                notable.append(f"**{b['brand']}** gained EU MiCA authorisation (was `{old_eu_status}`).")
            elif old_eu_status == "authorised" and new_eu_status == "withdrawn":
                notable.append(f"**{b['brand']}**'s EU MiCA authorisation was withdrawn.")
            else:
                notable.append(f"**{b['brand']}**: EU MiCA status changed `{old_eu_status}` → `{new_eu_status}`.")

    registry = {
        "generated": args.as_of,
        "source": "https://www.esma.europa.eu/sites/default/files/2024-12/CASPS.csv",
        "brand_count": len(brands),
        "brands": sorted(brands.keys()),
    }
    (DATA / "registry" / "esma.json").write_text(json.dumps(registry, indent=2))
    print(f"Wrote {len(brands)} brand files to {out_dir}")

    write_pr_body(notable)


# Read by .github/workflows/esma-sync.yml as the PR body (body-path) --
# notable changes surface at the very top, above the routine boilerplate,
# so they're visible in the GitHub notification/PR list without opening
# the diff. Kept out of git (see .gitignore); each run overwrites it.
def write_pr_body(notable):
    if notable:
        header = f"## 🔴 {len(notable)} notable change{'s' if len(notable) != 1 else ''}\n\n" + \
            "\n".join(f"- {line}" for line in notable) + "\n\n---\n\n"
    else:
        header = "No notable changes this run — routine `retrieved` date refresh only.\n\n---\n\n"
    body = header + (
        "Automated diff against the ESMA interim MiCA register.\n"
        "Review before merging: new brands may need entries in\n"
        "data/brand_map.yaml, and status changes are news-worthy --\n"
        "consider a changelog entry.\n"
    )
    (ROOT / ".pr-body.md").write_text(body)


if __name__ == "__main__":
    main()
