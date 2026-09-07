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
  네이버   news.naver.com 많이 본 뉴스 랭킹 -> 기사 제목
           (원래 이 자리는 다음이었으나, 다음은 검색어를 자바스크립트로만
            그려 HTML 에 아예 없어 서버에서 가져올 수 없었다. 프로브로 확인.)

각 항목에는 눌러서 갈 주소를 같이 담는다. 기사·게시글은 그 글로 바로 가고,
검색어는 그 포털의 검색 결과로 보낸다. 목록만 보여 주고 카드 전체를 포털
첫 화면으로 보내면, 정작 궁금한 그 항목을 다시 찾아야 한다.

한 포털이 실패해도 나머지는 갱신하고, 실패한 포털은 직전 값을 유지한다.
빈 화면보다 조금 지난 값이 낫고, 없는 값을 지어내지는 않는다.
"""
import json
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote, urljoin
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
    """(글, 주소) 짝에서 글이 겹치는 것을 걷어낸다."""
    seen, out = set(), []
    for text, url in items:
        if text and text not in seen:
            seen.add(text)
            out.append({"t": text, "u": url})
    return out[:KEEP]


def q(term):
    return quote(term, safe="")


def anchors(html):
    """(주소, 글자) 짝을 순서대로 뽑는다. 주소를 알아야 낱개로 누를 수 있다."""
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
        yield m.group(1), clean(m.group(2))


def from_nate():
    data = json.loads(get("https://www.nate.com/js/data/jsonLiveKeywordDataV1.js").text)
    # [순위, 표제, 방향, 변동, 키워드] 중 표제를 쓴다. 키워드보다 문장이라 읽기 쉽다.
    # 검색은 마지막 칸의 키워드로 걸어야 결과가 제대로 나온다.
    out = []
    for row in data:
        if len(row) > 1 and row[1]:
            term = (row[4] if len(row) > 4 and row[4] else row[1]).strip()
            out.append((row[1].strip(),
                        f"https://search.nate.com/search/all.html?q={q(term)}"))
    return dedupe(out)


def from_google():
    xml = get("https://trends.google.com/trending/rss?geo=KR").text
    titles = re.findall(r"<title>(.*?)</title>", xml, re.S)[1:]  # 첫 title 은 피드 제목
    return dedupe([(clean(t), f"https://www.google.com/search?q={q(clean(t))}")
                   for t in titles if clean(t)])


def from_dcinside():
    html = get("https://gall.dcinside.com/board/lists/?id=dcbest").text
    out = []
    for href, t in anchors(html):
        if "board/view" not in href or not t or len(t) > 80:
            continue
        if re.fullmatch(r"\[\d+(?:/\d+)?\]", t):   # 댓글 수 배지
            continue
        if "갤러리 이용 안내" in t:                    # 고정 공지
            continue
        t = re.sub(r"^\[[^\]]{1,6}\]\s*", "", t)   # 앞머리 [싱갤] 같은 갤 표시 제거
        if t:
            out.append((t, urljoin("https://gall.dcinside.com/", href)))
    return dedupe(out)


def from_zum():
    html = get("https://zum.com/").text
    i = html.find("issue-word-list")
    if i == -1:
        raise ValueError("issue-word-list 없음")
    chunk = html[i:i + 8000]
    items = [clean(x) for x in re.findall(r"<li[^>]*>(.*?)</li>", chunk, re.S)]
    # 순위 배지가 앞이나 뒤에 붙어 온다. 양쪽 다 떼어낸다.
    # 검색어로도 쓰는 글자라 숫자가 남으면 엉뚱한 결과가 나온다.
    items = [re.sub(r"^\d{1,2}\s*", "", x) for x in items]
    items = [re.sub(r"\s*\d{1,2}$", "", x) for x in items]
    items = [x.strip() for x in items]
    items = [x for x in items if 1 < len(x) <= 40]
    if not items:
        raise ValueError(f"목록이 비어 있음: {chunk[:200]!r}")
    return dedupe([(x, f"https://search.zum.com/search.zum?method=uni&query={q(x)}")
                   for x in items])


def from_naver_news():
    """네이버 '많이 본 뉴스' 랭킹에서 기사 제목과 그 기사 주소를 뽑는다.

    다음 자리를 대신한다. 다음은 검색어를 자바스크립트로만 그려 서버에서
    가져올 수 없었지만, 네이버 랭킹 페이지는 제목이 HTML 에 그대로 들어 있다.

    제목만 뽑던 것을 주소까지 함께 뽑도록 바꿨다. 이건 검색어가 아니라
    기사라서, 검색 결과로 보내면 정작 그 기사를 다시 찾아야 한다.
    """
    html = get("https://news.naver.com/main/ranking/popularDay.naver").text
    out = []
    for href, t in anchors(html):
        if "article" not in href or not (6 <= len(t) <= 80):
            continue
        out.append((t, urljoin("https://news.naver.com/", href)))
    hits = dedupe(out)
    if len(hits) >= 5:
        print(f"        (네이버: 기사 링크 {len(hits)}개)")
        return hits
    raise ValueError(f"제목을 찾지 못함 (본문 {len(html)}자, 후보 {len(out)}개)")


PORTALS = [
    {"key": "nate", "name": "네이트", "fn": from_nate},
    {"key": "naver_news", "name": "네이버 뉴스", "fn": from_naver_news},
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
            print(f"  [ok] {p['name']}: {len(keywords)}개 — {[k['t'] for k in keywords[:2]]}")
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
