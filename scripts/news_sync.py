#!/usr/bin/env python3
"""
news_sync.py - keyword-matches tracked brand names against a small set of
reputable outlets' public RSS feeds, and records any hits per brand.

Sources (all public, no signup/API key -- see below for why these and not
others): The Guardian's dedicated "Cryptocurrencies" tag feed and BBC's
Business and Technology feeds (general-interest outlets, broader but
reputable), Cointelegraph and The Block (established crypto-native
outlets whose RSS feeds run far denser on exchange names than general
press, since exchanges are their actual beat), and -- unlike the other
four -- the SEC's and DOJ's own official press-release RSS feeds. Those
last two are tagged category="regulatory" from the source itself, since
a headline from the regulator's own newsroom naming a tracked brand is a
categorically stronger signal than a keyword match against a news outlet.
DOJ's feed is a firehose covering every US Attorney's office nationwide,
not crypto-specific -- but the Binance $4.3B case was a DOJ action, not
an SEC one, so excluding it would miss exactly the kind of story this
category exists for. Reuters' public RSS feeds are dead; NYT's API is
explicitly CC BY-NC (non-commercial only) and has no crypto-specific feed
either, so neither is used here.

Entries from the four general-news sources also get tagged
category="regulatory" when the headline itself contains recognisable
regulatory-action language (see REGULATORY_KEYWORDS) -- a Cointelegraph
headline about an SEC settlement is regulatory news even though
Cointelegraph itself isn't a regulator. Everything else is
category="general".

Categorising is NOT a claim that a "regulatory" match is a formal
regulatory action *against* the brand named, or that a "general" match is
unrelated to its regulatory status -- it's a keyword/source heuristic,
kept in its own `news_mentions` field, same "cited, dated, not
synthesized" discipline as `third_party_reviews`. The frontend must say
so explicitly. Matching is deliberately conservative: a whole-word,
case-insensitive match against the brand's exact `brand` string, skipped
entirely for brand names under 4 characters (too many false positives
from short/generic names) -- still expect some noise (a brand name
that's also a common word or a different company entirely can match),
which is why this is presented as "mentions", not "news about this
exchange".

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
    ("The Guardian", "https://www.theguardian.com/technology/cryptocurrencies/rss", "general"),
    ("BBC", "https://feeds.bbci.co.uk/news/business/rss.xml", "general"),
    ("BBC", "https://feeds.bbci.co.uk/news/technology/rss.xml", "general"),
    ("Cointelegraph", "https://cointelegraph.com/rss", "general"),
    ("The Block", "https://www.theblock.co/rss.xml", "general"),
    ("SEC", "https://www.sec.gov/news/pressreleases.rss", "regulatory"),
    ("DOJ", "https://www.justice.gov/news/rss?type=press_release", "regulatory"),
]

MIN_BRAND_LEN = 4
MAX_PER_BRAND = 8

# Headline language that marks a general-news match as regulatory even
# though the outlet itself isn't a regulator -- e.g. a Cointelegraph
# headline about an SEC settlement. Deliberately conservative: no bare
# "court" or "ban" (too easy to false-positive on "X courts investors" or
# unrelated country-level bans), same caution as SKIP_BRANDS below.
REGULATORY_KEYWORDS = [
    "SEC", "CFTC", "DOJ", "FinCEN", "FCA", "regulator", "regulators",
    "lawsuit", "sues", "sued", "charges", "charged", "indictment",
    "indicted", "settlement", "settles", "fined", "sanctions",
    "sanctioned", "guilty plea", "compliance", "investigation",
    "subpoena", "license revoked", "banned", "prosecutors",
]
REGULATORY_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in REGULATORY_KEYWORDS) + r")\b", re.IGNORECASE
)

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
    for source, url, source_category in FEEDS:
        try:
            items = fetch_feed(url)
        except Exception as e:
            print(f"  WARNING: failed to fetch {source} ({url}): {e}", file=sys.stderr)
            continue
        for item in items:
            item["source"] = source
            # A regulatory-source item is regulatory regardless of its
            # headline; a general-source item earns the tag only if its
            # own headline uses regulatory-action language.
            item["category"] = (
                "regulatory" if source_category == "regulatory" or REGULATORY_PATTERN.search(item["title"])
                else "general"
            )
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
                "category": item["category"],
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
