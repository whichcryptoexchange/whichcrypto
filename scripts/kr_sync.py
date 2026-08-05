#!/usr/bin/env python3
"""
kr_sync.py - Korea FIU (KoFIU) Virtual Asset Service Provider (VASP)
registration ingestion.

KoFIU publishes the "가상자산사업자 신고에 관한 정보공개 현황" (VASP registration
disclosure status) as a structured .xlsx attached to a board post. There is
no fixed download URL -- the file's download token changes with each
updated post -- so this script first calls the board-list JSON API to find
the current post and its file token, then downloads that specific file.
Neither step is bot-walled; both are plain unauthenticated HTTP requests.

Registration under the Act on Reporting and Using Specified Financial
Transaction Information is AML/CFT reporting only, not a business licence
(confirmed against legal analysis of the Act, not assumed) -- same tier as
UK/Canada/US, not the genuine-licence tier of MiCA/VARA/MAS/SFC/GFSC/FSA/SC.
We therefore emit
  regime: "Korea FIU VASP Registration"
  status: "registered"

Rows with a value in the "직권말소" (ex officio cancellation) column are
excluded -- same discipline as excluding Malaysia's/Hong Kong's historical
tables. Matching against data/kr_reg_map.yaml is by legal entity name
(column C), kept in its original Korean as printed in the primary source
rather than guessed at in translation.

Usage:
  python3 scripts/kr_sync.py
"""
import datetime as dt
import http.cookiejar
import io
import json
import pathlib
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BOARD_LIST_URL = ("https://www.kofiu.go.kr/cmn/board/selectBoardListFile.do"
                   "?ntcnYardOrdrNo=&page=1&seCd=0007&selScope=&size=4&subSech=")
DOWNLOAD_BASE = "https://www.kofiu.go.kr/cmn/file/downloadBoard.do?fileId="
PAGE_URL = "https://www.kofiu.go.kr/kor/notification/notice.do"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def fetch_current_xlsx():
    # The download token (fileId) is tied to the session cookie set by the
    # board-list request -- both calls must share one cookie jar, or the
    # download endpoint returns a "file download error" HTML page instead
    # of the file, even though the fileId value itself looks valid.
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    req = urllib.request.Request(BOARD_LIST_URL, headers={"User-Agent": UA})
    with opener.open(req, timeout=30) as r:
        board = json.loads(r.read().decode("utf-8"))

    posts = [p for p in board.get("result", []) if "가상자산사업자 신고 현황" in (p.get("ntcnYardSjNm") or "")]
    if not posts:
        raise RuntimeError("no '가상자산사업자 신고 현황' board post found -- page structure changed")
    post = posts[0]
    files = post.get("fileList") or []
    if not files:
        raise RuntimeError("current board post has no attached file")
    file_id = files[0]["fileId"]
    url = DOWNLOAD_BASE + urllib.parse.quote(file_id, safe="")
    req2 = urllib.request.Request(url, headers={"User-Agent": UA})
    with opener.open(req2, timeout=30) as r2:
        return r2.read(), post.get("ntcnYardSjNm", "")


def parse_registrations(xlsx_bytes):
    z = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    sst = ET.fromstring(z.read("xl/sharedStrings.xml"))
    strings = ["".join((t.text or "") for t in si.findall(".//a:t", NS))
               for si in sst.findall("a:si", NS)]
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))

    def row_vals(row):
        vals = {}
        for c in row.findall("a:c", NS):
            col = "".join(ch for ch in c.get("r") if ch.isalpha())
            v = c.find("a:v", NS)
            if v is None:
                continue
            vals[col] = strings[int(v.text)] if c.get("t") == "s" else v.text
        return vals

    registrations = {}
    for row in sheet.findall(".//a:row", NS):
        d = row_vals(row)
        no = (d.get("A") or "").strip()
        if not no.isdigit():
            continue
        entity = d.get("C", "")
        if not entity or d.get("O"):  # skip 직권말소 (ex officio cancellation) rows
            continue
        registrations[entity] = {
            "service_name": d.get("B", ""),
            "accepted": d.get("I", ""),
        }
    return registrations


def iso_date(korean_date):
    korean_date = (korean_date or "").strip().rstrip(".")
    try:
        return dt.datetime.strptime(korean_date, "%Y.%m.%d").date().isoformat()
    except ValueError:
        return None


def main():
    as_of = dt.date.today().isoformat()
    reg_map = yaml.safe_load((DATA / "kr_reg_map.yaml").read_text()) or []
    exch_dir = DATA / "exchanges"

    print("Fetching current KoFIU VASP registration board post...", file=sys.stderr)
    xlsx_bytes, post_title = fetch_current_xlsx()
    print(f"Using post: {post_title}", file=sys.stderr)
    registrations = parse_registrations(xlsx_bytes)
    print(f"Found {len(registrations)} active registrations", file=sys.stderr)

    for item in reg_map:
        brand_id, entity = item["brand_id"], item["entity"]
        path = exch_dir / f"{brand_id}.yaml"
        if not path.exists():
            print(f"  WARNING: no data/exchanges/{brand_id}.yaml — skipping (kr_reg_map.yaml id mismatch?)",
                  file=sys.stderr)
            continue
        row = registrations.get(entity)
        if not row:
            print(f"  WARNING: {entity} for {brand_id} not found in the current registration list — "
                  f"may have been cancelled", file=sys.stderr)
            continue

        entry = {
            "status": "registered",
            "regime": "Korea FIU VASP Registration",
            "via": "kr_fiu_register",
            "entity": entity,
            "since": iso_date(row["accepted"]),
        }
        if item.get("caveat"):
            entry["caveat"] = item["caveat"]

        doc = yaml.safe_load(path.read_text())
        doc.setdefault("countries", {})["KR"] = [entry]
        sources = doc.setdefault("sources", [])
        if not any(s.get("name") == "Korea FIU VASP Registration Disclosure" for s in sources):
            sources.append({
                "name": "Korea FIU VASP Registration Disclosure",
                "url": PAGE_URL,
                "retrieved": as_of,
            })
        else:
            for s in sources:
                if s.get("name") == "Korea FIU VASP Registration Disclosure":
                    s["retrieved"] = as_of
        path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
        print(f"  {brand_id}: wrote KR entry")

    print("Done.")


if __name__ == "__main__":
    main()
