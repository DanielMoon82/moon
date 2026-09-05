#!/usr/bin/env python3
"""Fetch each portal's realtime keyword list into data/portal-trends.json.

The portals publish no documented API, so every parser here was derived by
probing the real responses from a runner and reading the run log — not guessed.
What each one turned out to be:

  네이트   www.nate.com/js/data/jsonLiveKeywordDataV1.js
           -> [["1","제목","s","0","키워드"], ...] 그대로 JSON
  구글     trends.google.com RSS -> <item><title>
  디시     실시간 베스트 갤러리 목록 HTML -> board/view 링크의 글 제목
           (댓글 수 [12] 같은 배지가 링크로 같이 잡혀 걸러낸다)
  줌       zum.com 홈에 박힌 issue-word-list 마크업
  다음     자바스크립트로만 그려지고 공개 주소가 없다. PC 홈에는 키워드가
           아예 없고 트렌드 애니메이션 번들만 있다. 모바일 홈을 한 번 더
           시도하되, 실패하면 그 포털만 값 없이 두고 나머지는 정상 표시한다.

한 포털이 실패해도 나머지는 갱신하고, 실패한 포털은 직전 값을 유지한다.
빈 화면보다 조금 지난 값이 낫고, 없는 값을 지어내지는 않는다.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_JSON = ROOT / "data" / "portal-trends.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}
TIMEOUT = 20
KEEP = 10


def get(url, encoding=None):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    if encoding:
        r.encoding = encoding
    return r


def clean(text):
    """태그를 걷어내고 공백을 하나로 줄인다."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def dedupe(items):
    seen, out = set(), []
    for it in items:
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out[:KEEP]


def from_nate():
    data = json.loads(get("https://www.nate.com/js/data/jsonLiveKeywordDataV1.js").text)
    # [순위, 표제, 방향, 변동, 키워드] 중 표제를 쓴다. 키워드보다 문장이라 읽기 쉽다.
    return dedupe([row[1].strip() for row in data if len(row) > 1 and row[1]])


def from_google():
    xml = get("https://trends.google.com/trending/rss?geo=KR").text
    titles = re.findall(r"<title>(.*?)</title>", xml, re.S)[1:]  # 첫 title 은 피드 제목
    return dedupe([clean(t) for t in titles])


def from_dcinside():
    html = get("https://gall.dcinside.com/board/lists/?id=dcbest").text
    raw = re.findall(r'<a[^>]+href="[^"]*board/view[^"]*"[^>]*>(.*?)</a>', html, re.S)
    out = []
    for t in raw:
        t = clean(t)
        if not t or len(t) > 80:
            continue
        if re.fullmatch(r"\[\d+(?:/\d+)?\]", t):   # 댓글 수 배지
            continue
        if "갤러리 이용 안내" in t:                  # 고정 공지
            continue
        t = re.sub(r"^\[[^\]]{1,6}\]\s*", "", t)   # 앞머리 [싱갤] 같은 갤 표시 제거
        if t:
            out.append(t)
    return dedupe(out)


def from_zum():
    html = get("https://zum.com/").text
    i = html.find("issue-word-list")
    if i == -1:
        raise ValueError("issue-word-list 없음")
    chunk = html[i:i + 8000]
    items = [clean(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", chunk, re.S)]
    # 순위 숫자가 앞에 붙어 오는 경우가 있어 떼어낸다
    items = [re.sub(r"^\d{1,2}\s*", "", x) for x in items]
    items = [x for x in items if 1 < len(x) <= 40]
    if not items:
        raise ValueError(f"목록이 비어 있음: {chunk[:200]!r}")
    return dedupe(items)


def from_daum():
    """PC 홈에는 키워드가 없다. 모바일 홈에 서버에서 그려진 목록이 있는지 본다."""
    html = get("https://m.daum.net/").text
    for pat in (r'class="[^"]*(?:tit_rank|txt_rank|link_rank|keyword)[^"]*"[^>]*>([^<]{2,40})<',
                r'<a[^>]+href="[^"]*(?:trend|rank)[^"]*"[^>]*>([^<]{2,40})</a>'):
        hits = dedupe([clean(h) for h in re.findall(pat, html)])
        if len(hits) >= 5:
            return hits
    raise ValueError("모바일 홈에서도 실시간 검색어를 찾지 못함")


PORTALS = [
    {"key": "nate", "name": "네이트", "fn": from_nate},
    {"key": "daum", "name": "다음", "fn": from_daum},
    {"key": "zum", "name": "줌", "fn": from_zum},
    {"key": "dcinside", "name": "디시인사이드", "fn": from_dcinside},
    {"key": "google", "name": "구글", "fn": from_google},
]


def main():
    try:
        old = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    old_portals = old.get("portals") or {}

    now = datetime.now(timezone.utc).isoformat()
    portals, fresh = {}, 0

    for p in PORTALS:
        try:
            keywords = p["fn"]()
            if not keywords:
                raise ValueError("빈 목록")
            portals[p["key"]] = {"name": p["name"], "keywords": keywords, "updated_at": now}
            fresh += 1
            print(f"  [ok] {p['name']}: {len(keywords)}개 — {keywords[:3]}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [fail] {p['name']}: {exc}", file=sys.stderr)
            kept = old_portals.get(p["key"])
            if kept:
                portals[p["key"]] = kept
                print(f"  [keep] {p['name']}: 직전 값 유지 ({kept.get('updated_at')})")

    if not fresh:
        print("모든 포털 실패 — 기존 파일 유지", file=sys.stderr)
        return 0

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({"updated_at": now, "portals": portals}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"{OUT_JSON.relative_to(ROOT)} 기록 — {fresh}/{len(PORTALS)} 갱신")
    return 0


if __name__ == "__main__":
    sys.exit(main())
