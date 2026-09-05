#!/usr/bin/env python3
"""Probe candidate endpoints for each portal's realtime keyword list.

This exists because the portals publish no documented API, and the sandbox this
was written in has no outbound network. Rather than guessing parsers and
shipping something that silently returns nothing, this fetches each candidate
from a GitHub Actions runner and prints the status, size and a snippet so the
real response shape can be read off the run log. It writes nothing.

Delete once the parsers in fetch-portal-trends.py are settled.
"""
import re
import sys

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Accept": "text/html,application/json,*/*;q=0.8",
}

CANDIDATES = [
    ("네이트 JSON", "https://www.nate.com/js/data/jsonLiveKeywordDataV1.js"),
    ("네이트 홈", "https://www.nate.com/"),
    ("다음 홈", "https://www.daum.net/"),
    ("다음 트렌드 API", "https://tab.search.daum.net/api/trend/realtime"),
    ("줌 홈", "https://zum.com/"),
    ("줌 이슈 API", "https://api.zum.com/issue/rank"),
    ("디시 실베", "https://gall.dcinside.com/board/lists/?id=dcbest"),
    ("구글 트렌드 RSS", "https://trends.google.com/trending/rss?geo=KR"),
]


def snippet(text, n=400):
    """태그와 공백을 걷어내 눈으로 읽을 수 있게 줄인다."""
    flat = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.S | re.I)
    flat = re.sub(r"<style[^>]*>.*?</style>", " ", flat, flags=re.S | re.I)
    flat = re.sub(r"\s+", " ", flat)
    return flat[:n]


def main():
    for name, url in CANDIDATES:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            body = resp.text
            print(f"\n### {name}  [{resp.status_code}]  {len(body)}자  {url}")
            print(f"    content-type: {resp.headers.get('content-type')}")
            # 원문 앞부분(태그 포함)과 텍스트만 남긴 것 둘 다 보여 준다.
            print(f"    raw : {body[:300]!r}")
            print(f"    text: {snippet(body)!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"\n### {name}  [실패] {url}\n    {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
