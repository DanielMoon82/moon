#!/usr/bin/env python3
"""Probe round 3 — narrowed to the three portals still unsolved.

Settled so far (round 2):
  네이트  https://www.nate.com/js/data/jsonLiveKeywordDataV1.js -> JSON 배열
  구글    trends.google.com RSS -> <title>

Still open: 줌(리스트 마크업), 디시(링크 정규식), 다음(자바스크립트 렌더라 주소 불명).
Writes nothing. Delete once fetch-portal-trends.py is settled.
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
    "Referer": "https://www.daum.net/",
}
TIMEOUT = 20


def get(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


def probe_zum():
    print("\n### 줌 — issue-word-list 안쪽")
    try:
        html = get("https://zum.com/")
    except Exception as exc:  # noqa: BLE001
        print(f"  실패: {exc}")
        return
    i = html.find("issue-word-list")
    if i == -1:
        print("  issue-word-list 없음")
        return
    chunk = html[i:i + 3000]
    print(f"  원문 1200자: {chunk[:1200]!r}")
    # 리스트 항목의 텍스트만 뽑아 본다
    items = re.findall(r"<li[^>]*>(.*?)</li>", chunk, re.S)[:12]
    for it in items[:8]:
        print(f"    li: {re.sub(r'<[^>]+>', ' ', it).strip()[:80]!r}")


def probe_dc():
    print("\n### 디시 — 링크 정규식 넓혀서")
    try:
        html = get("https://gall.dcinside.com/board/lists/?id=dcbest")
    except Exception as exc:  # noqa: BLE001
        print(f"  실패: {exc}")
        return
    print(f"  'board/view' 등장 횟수: {html.count('board/view')}")
    i = html.find("board/view")
    if i != -1:
        print(f"  주변 원문: {html[max(0, i - 400):i + 400]!r}")
    loose = re.findall(r'<a[^>]+href="[^"]*board/view[^"]*"[^>]*>(.*?)</a>', html, re.S)
    cleaned = [re.sub(r"<[^>]+>|\s+", " ", t).strip() for t in loose]
    cleaned = [t for t in cleaned if 2 <= len(t) <= 80][:12]
    print(f"  -> 제목 후보: {cleaned}")


def probe_daum():
    print("\n### 다음 — 실검 주소 찾기")
    candidates = [
        "https://tab.search.daum.net/api/trend/realtime",
        "https://tab.search.daum.net/aa/rt/keyword",
        "https://www.daum.net/api/trend",
        "https://search.daum.net/qsearch?w=tot&col=trend",
        "https://m.daum.net/",
    ]
    for url in candidates:
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            body = r.text
            print(f"  [{r.status_code}] {url}  {len(body)}자  "
                  f"{r.headers.get('content-type')}")
            print(f"    raw: {body[:260]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [실패] {url}: {exc}")

    # 홈에 박힌 스크립트 주소 중 트렌드/실검 관련이 있는지
    try:
        html = get("https://www.daum.net/")
        srcs = re.findall(r'src="([^"]+)"', html)
        hit = [s for s in srcs if re.search(r"trend|rank|keyword|issue", s, re.I)]
        print(f"  스크립트 후보: {hit[:10]}")
        for key in ("실시간", "트렌드", "급상승"):
            j = html.find(key)
            if j != -1:
                around = re.sub(r"\s+", " ", html[max(0, j - 250):j + 350])
                print(f"  '{key}' 주변: {around!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"  홈 조회 실패: {exc}")


def main():
    for fn in (probe_zum, probe_dc, probe_daum):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"  [예외] {fn.__name__}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
