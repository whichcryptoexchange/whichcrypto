#!/usr/bin/env python3
"""
ny_sync.py - New York State Department of Financial Services (NYDFS)
virtual currency licensee ingestion.

NYDFS publishes its "List of Licensed Virtual Currency Entities" as a
plain HTML table (a single <table summary="List of Licensed Virtual
Currency Entities">) on its virtual currency businesses page -- no bot
protection, no session cookies.

Two distinct grants appear on that list, both of which we treat as a
genuine, state-chartered licence (status: "licensed"), not an AML-only
registration:
  - a "Virtual Currency License" (the BitLicense) under 23 NYCRR Part 200,
    sometimes granted alongside a separate money transmitter licence
  - a "Limited Purpose Trust Charter" under the NY Banking Law

This is a STATE-level regime, covering New York only -- it does not
replace or duplicate the federal FinCEN MSB registration tracked by
fincen_sync.py under the same "US" country key. Because two independent
scripts now write into countries.US, each only ever replaces its OWN
entries (matched by the "via" field) and leaves the other's alone -- see
the merge logic below and the equivalent fix in fincen_sync.py.

The page has no reference/registration number column, only entity name
and licence type, so matching against data/ny_reg_map.yaml is by legal
entity name.

Usage:
  python3 scripts/ny_sync.py
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
PAGE_URL = "https://www.dfs.ny.gov/virtual_currency_businesses"

# NYDFS's Cloudflare WAF challenges a full modern-Chrome UA string (its TLS
# fingerprint doesn't match what it claims to be) but passes a bare
# "Mozilla/5.0" -- verified against the live site before relying on this.
UA = "Mozilla/5.0"

REGIME_LABELS = {
    "virtual_currency": "NY DFS Virtual Currency License (BitLicense)",
    "vc_and_mt": "NY DFS Virtual Currency & Money Transmitter Licenses (BitLicense)",
    "trust_charter": "NY DFS Limited Purpose Trust Charter",
}

# Substring match against the page's own "Licensure" column text -> our
# licence_type key, so a live-table format drift is caught (KeyError) rather
# than silently mis-tagged.
LICENSURE_TEXT_TO_TYPE = [
    ("Virtual Currency and Money Transmitter", "vc_and_mt"),
    ("Virtual Currency License", "virtual_currency"),
    ("Limited Purpose Trust Charter", "trust_charter"),
]


def clean(cell):
    cell = re.sub(r"<[^>]+>", " ", cell)
    cell = htmlmod.unescape(cell).replace("\xa0", " ")
    return re.sub(r"\s+", " ", cell).strip()


def licensure_to_type(text):
    for needle, key in LICENSURE_TEXT_TO_TYPE:
        if needle in text:
            return key
    raise RuntimeError(f"unrecognised licensure text on live page: {text!r} -- page format may have changed")


def fetch_licensee_table():
    req = urllib.request.Request(PAGE_URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        html_ = r.read().decode("utf-8", errors="replace")

    marker = html_.find('summary="List of Licensed Virtual Currency Entities"')
    if marker == -1:
        raise RuntimeError('table with summary="List of Licensed Virtual Currency Entities" not found -- '
                            'page structure changed')
    table_start = html_.rfind("<table", 0, marker)
    table_end = html_.find("</table>", marker)
    table_html = html_[table_start:table_end]

    licensees = {}
    for row_html in re.findall(r"<tr.*?</tr>", table_html, re.S):
        cells = [clean(c) for c in re.findall(r"<t[dh].*?</t[dh]>", row_html, re.S)]
        if len(cells) < 2 or not cells[0] or cells[0] == "Entity":
            continue
        licensees[cells[0]] = licensure_to_type(cells[1])
    return licensees


def main():
    as_of = dt.date.today().isoformat()
    reg_map = yaml.safe_load((DATA / "ny_reg_map.yaml").read_text()) or []
    exch_dir = DATA / "exchanges"

    print("Fetching live NYDFS licensed virtual currency entities table...", file=sys.stderr)
    licensees = fetch_licensee_table()
    print(f"Found {len(licensees)} licensed entities", file=sys.stderr)

    by_brand = {}
    for item in reg_map:
        by_brand.setdefault(item["brand_id"], []).append(item)

    # Surfaced in the PR body so a dropped entity is visible without opening
    # the Action run's logs. A real, live example of exactly why this
    # matters: NYDFS quietly changed Circle's trust-charter display name
    # from "Circle Internet Trust Company, LLC" to "Circle Internet Trust
    # Company, LLC. d/b/a Circle New York Trust" (an added period AND a
    # d/b/a suffix) -- the entity never left the register, but the exact-
    # string match against ny_reg_map.yaml silently failed and the entry
    # was dropped from the brand's file with only a stderr warning, easy to
    # miss in a routine date-bump-looking PR.
    notable = []

    for brand_id, items in sorted(by_brand.items()):
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping (ny_reg_map.yaml id mismatch?)",
                  file=sys.stderr)
            continue

        entries = []
        for item in items:
            entity = item["entity"]
            live_type = licensees.get(entity)
            if live_type is None:
                print(f"  WARNING: {entity} for {brand_id} not found in the current NYDFS licensee "
                      f"table — may have surrendered its licence", file=sys.stderr)
                notable.append(
                    f"**{brand_id}**: `{entity}` no longer found on the live NYDFS licensee table — "
                    f"either it genuinely surrendered its licence, or NYDFS changed its display name "
                    f"(check for a close-but-not-exact match on the live page before assuming the former)."
                )
                continue
            if live_type != item["licence_type"]:
                print(f"  WARNING: {entity} for {brand_id} now shows licence_type={live_type!r} on the "
                      f"live page, but ny_reg_map.yaml says {item['licence_type']!r} — update the map",
                      file=sys.stderr)
                notable.append(
                    f"**{brand_id}**: `{entity}` now shows licence_type `{live_type}` on the live page, "
                    f"but ny_reg_map.yaml says `{item['licence_type']}` — update the map."
                )
            entry = {
                "status": "licensed",
                "regime": REGIME_LABELS[item["licence_type"]],
                "via": "ny_dfs_register",
                "entity": entity,
                "since": item.get("since"),
            }
            if item.get("caveat"):
                entry["caveat"] = item["caveat"]
            entries.append(entry)

        if not entries:
            print(f"  {brand_id}: no valid NY entries, leaving file untouched")
            continue

        doc = yaml.safe_load(path.read_text())
        countries = doc.setdefault("countries", {})
        # US already carries federal FinCEN entries (via: msb_register) written
        # by fincen_sync.py -- only replace our own slice, matching the fix
        # made there when this script was added.
        other = [e for e in countries.get("US", []) if e.get("via") != "ny_dfs_register"]
        countries["US"] = other + entries

        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "NY DFS List of Licensed Virtual Currency Entities" for s in sources):
            sources.append({
                "name": "NY DFS List of Licensed Virtual Currency Entities",
                "url": PAGE_URL,
                "retrieved": as_of,
            })
        else:
            for s in sources:
                if s.get("name") == "NY DFS List of Licensed Virtual Currency Entities":
                    s["retrieved"] = as_of
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote {len(entries)} NY entr{'y' if len(entries) == 1 else 'ies'}")

    print("Done.")
    write_pr_body(notable)


# Read by .github/workflows/ny-sync.yml as the PR body (body-path).
def write_pr_body(notable):
    if notable:
        header = f"## 🔴 {len(notable)} notable change{'s' if len(notable) != 1 else ''} -- check before merging\n\n" + \
            "\n".join(f"- {line}" for line in notable) + "\n\n---\n\n"
    else:
        header = "No notable changes this run — routine `retrieved` date refresh only.\n\n---\n\n"
    body = header + (
        "Automated refresh of data/ny_reg_map.yaml's pinned legal entity\n"
        "names against NYDFS's live \"List of Licensed Virtual Currency\n"
        "Entities\" table. This does NOT discover new brands -- only\n"
        "re-confirms entities already curated in ny_reg_map.yaml still\n"
        "hold their licence/charter, and catches a licence_type drift\n"
        "(BitLicense vs money transmitter vs trust charter) between the\n"
        "map and the live page. Review for:\n"
        "  - a pinned entity no longer found on the current list (may\n"
        "    have surrendered its licence -- confirm before merging, but\n"
        "    ALSO check whether NYDFS just changed its display name --\n"
        "    matching is by exact legal-entity-name string, so a single\n"
        "    added word or punctuation mark is enough to silently drop a\n"
        "    still-active entry)\n"
        "  - a licence_type mismatch warning (the live page changed what\n"
        "    it says a brand holds)\n"
        "A NY DFS virtual currency licence or limited purpose trust\n"
        "charter is a genuine, state-chartered regime -- distinct from\n"
        "(and never a substitute for) the federal FinCEN MSB\n"
        "registration synced separately by fincen_sync.py under the\n"
        "same countries.US key. Both scripts only ever touch their own\n"
        "slice of that array (matched by the \"via\" field); do not merge\n"
        "a change here that clobbers the other's entries.\n"
    )
    (ROOT / ".pr-body.md").write_text(body)


if __name__ == "__main__":
    main()
