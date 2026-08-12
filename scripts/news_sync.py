#!/usr/bin/env python3
"""
news_sync.py - keyword-matches tracked brand names against a small set of
reputable outlets' public RSS feeds, and records any hits per brand.

Sources (all public, no signup/API key -- see below for why these two and
not others): The Guardian's dedicated "Cryptocurrencies" tag feed (good
topical signal), plus BBC's Business and Technology feeds (no crypto-
specific tag, broader, but reputable and confirmed working). Reuters'
public RSS feeds are dead; NYT's API is explicitly CC BY-NC (non-
commercial only) and has no crypto-specific feed either, so neither is
used here.

This is NOT a claim that a match is relevant to regulatory status --
it's an unfiltered keyword match against general news coverage, kept
in its own `news_mentions` field, same "cited, dated, not synthesized"
discipline as `third_party_reviews`. The frontend must say so explicitly.
Matching is deliberately conservative: a whole-word, case-insensitive
match against the brand's exact `brand` string, skipped entirely for
brand names under 4 characters (too many false positives from short/
generic names) -- still expect some noise (a brand name that's also a
common word or a different company entirely can match), which is why
this is presented as "mentions", not "news about this exchange".

Matching is against the HEADLINE only, not the article body/description
-- an early test run matched "Strike" (the Bitcoin brand) against a
Guardian story about unlicensed gambling casinos sponsoring football
teams, purely because the word "strike" appeared somewhere in the
description text. The headline of that same article had no match at
all. Headline-only trades recall for precision: a brand named only in
an article's body is missed, but a brand whose name is incidental
background noise in unrelated body text is not falsely flagged --
worth it, since the point is a small number of trustworthy signals,
not maximum coverage.

Unlike the FRN/reference-based syncs, there's no curated per-brand
reference to verify against -- every run is a fresh keyword sweep, and
new matches accumulate (deduped by URL, capped at 8 most recent per
brand) rather than replacing what's there, since RSS feeds are rolling
windows and an older match would otherwise be silently lost once it
ages out of the feed. The GitHub Actions workflow opens a PR rather
than pushing straight to main, same as every other sync -- review every
match before merging; keyword matching against general news will never
be perfectly precise, and this workflow's own history is proof.

Usage:
  python3 scripts/news_sync.py
"""
import datetime as dt
import pathlib
import re
import sys
import urllib.request

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

FEEDS = [
    ("The Guardian", "https://www.theguardian.com/technology/cryptocurrencies/rss"),
    ("BBC", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("BBC", "https://feeds.bbci.co.uk/news/technology/rss.xml"),
]

MIN_BRAND_LEN = 4
MAX_PER_BRAND = 8

# Brand names that are also common English words, confirmed to produce
# false-positive title matches on ordinary news headlines that have
# nothing to do with the brand. "Strike" was caught by a real test run
# matching "Workers strike over pay dispute at car plant" -- title-only
# matching (see fetch_feed) fixes substring/body-text noise but can't
# fix a brand name that's a genuine dictionary word appearing in its
# ordinary sense. Add to this set as further cases turn up in PR review
# -- this list will never be complete on its own, which is exactly why
# every run still goes through a reviewed PR rather than a direct push.
SKIP_BRANDS = {"strike", "shares"}


def strip_cdata(s):
    m = re.match(r"^<!\[CDATA\[(.*)\]\]>$", s.strip(), re.S)
    return (m.group(1) if m else s).strip()


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_pubdate(raw):
    # RFC 822 format, e.g. "Tue, 28 Jul 2026 13:59:13 GMT"
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S %z"):
        try:
            return dt.datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def fetch_feed(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        xml = r.read().decode("utf-8", errors="replace")
    items = []
    for raw in re.findall(r"<item>(.*?)</item>", xml, re.S):
        title_m = re.search(r"<title>(.*?)</title>", raw, re.S)
        link_m = re.search(r"<link>(.*?)</link>", raw, re.S)
        pub_m = re.search(r"<pubDate>(.*?)</pubDate>", raw, re.S)
        if not (title_m and link_m):
            continue
        items.append({
            "title": clean(strip_cdata(title_m.group(1))),
            "url": clean(strip_cdata(link_m.group(1))),
            "published": parse_pubdate(pub_m.group(1)) if pub_m else None,
        })
    return items


def main():
    exch_dir = DATA / "exchanges"
    brands = []
    for path in sorted(exch_dir.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        brand = doc.get("brand")
        if brand and len(brand) >= MIN_BRAND_LEN and brand.lower() not in SKIP_BRANDS:
            brands.append((path, doc))

    as_of = dt.date.today().isoformat()
    all_items = []
    for source, url in FEEDS:
        try:
            items = fetch_feed(url)
        except Exception as e:
            print(f"  WARNING: failed to fetch {source} ({url}): {e}", file=sys.stderr)
            continue
        for item in items:
            item["source"] = source
        all_items.extend(items)
        print(f"  {source}: {len(items)} items from {url}", file=sys.stderr)

    matched_any = 0
    for path, doc in brands:
        brand = doc["brand"]
        pattern = re.compile(r"\b" + re.escape(brand) + r"\b", re.IGNORECASE)
        hits = [item for item in all_items if pattern.search(item["title"])]
        if not hits:
            continue

        existing = doc.get("news_mentions", [])
        existing_urls = {e["url"] for e in existing}
        new_entries = [
            {
                "source": item["source"],
                "title": item["title"],
                "url": item["url"],
                "published": item["published"],
                "retrieved": as_of,
            }
            for item in hits if item["url"] not in existing_urls
        ]
        if not new_entries:
            continue

        combined = existing + new_entries
        combined.sort(key=lambda e: e.get("published") or "", reverse=True)
        doc["news_mentions"] = combined[:MAX_PER_BRAND]
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        matched_any += 1
        print(f"  {doc['id']}: +{len(new_entries)} new mention(s)")

    print(f"Done. {matched_any} brand file(s) updated.")


if __name__ == "__main__":
    main()
