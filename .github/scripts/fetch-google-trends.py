#!/usr/bin/env python3
"""Fetch Google Trends' public RSS feed for South Korea and write it to
data/trends-kr.json for the site to read client-side. Run on a schedule
by .github/workflows/fetch-trends.yml.
"""
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

FEED_URL = "https://trends.google.com/trending/rss?geo=KR"
OUT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "trends-kr.json"


def fetch_keywords():
    req = urllib.request.Request(
        FEED_URL,
        headers={"User-Agent": "Mozilla/5.0 (compatible; moon-trends-bot/1.0)"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        body = resp.read()

    root = ET.fromstring(body)
    keywords = [item.findtext("title") for item in root.iter("item")]
    return [k.strip() for k in keywords if k and k.strip()]


def main():
    try:
        keywords = fetch_keywords()
    except Exception as exc:  # network/parse failure: keep last good data
        print(f"fetch failed, leaving existing data in place: {exc}", file=sys.stderr)
        return 0

    if not keywords:
        print("no keywords parsed, leaving existing data in place", file=sys.stderr)
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "geo": "KR",
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "keywords": keywords[:15],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(keywords[:15])} keywords to {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
