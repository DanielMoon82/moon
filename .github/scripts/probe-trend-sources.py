#!/usr/bin/env python3
"""Probe round 2: find where each portal's keyword list actually lives.

Round 1 showed all four portals answer 200 from a runner, but a head-of-body
snippet is all boilerplate. This round applies per-site heuristics and prints
only the matched regions, so the real markup/JSON shape can be read off the
run log and turned into a parser. Writes nothing.

Delete once fetch-portal-trends.py is settled.
"""
import json
import re
import sys

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}
TIMEOUT = 20


def get(url, **kw):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def show(title, items):
    print(f"    -> {title}: {items[:12]}")


def probe_nate():
    print("\n### 네이트")
    for url in ("https://www.nate.com/js/data/jsonLiveKeywordDataV1.js",
                "https://www.nate.com/js/data/jsonLiveKeywordDataV1.js?v=1"):
        try:
            r = get(url)
            print(f"  [{r.status_code}] {url}  {len(r.text)}자")
            print(f"    raw: {r.text[:500]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [실패] {url}: {exc}")
    try:
        html = get("https://www.nate.com/").text
        # 실검 영역을 감싸는 클래스 후보를 찾는다
        for pat in (r'class="[^"]*rank[^"]*"', r'class="[^"]*keyword[^"]*"',
                    r'class="[^"]*issue[^"]*"'):
            hits = sorted(set(re.findall(pat, html)))[:8]
            if hits:
                show(f"nate.com {pat}", hits)
    except Exception as exc:  # noqa: BLE001
        print(f"  [실패] nate.com: {exc}")


def probe_daum():
    print("\n### 다음")
    try:
        html = get("https://www.daum.net/").text
    except Exception as exc:  # noqa: BLE001
        print(f"  [실패] {exc}")
        return
    for pat in (r'class="[^"]*(?:rank|keyword|trend|issue)[^"]*"',):
        hits = sorted(set(re.findall(pat, html)))[:14]
        show("daum 클래스", hits)
    # 페이지에 박힌 JSON 후보
    for m in re.finditer(r'(?:window\.\w+|var\s+\w+)\s*=\s*(\{.{0,200})', html):
        print(f"    json 후보: {m.group(1)[:200]!r}")
        break
    idx = html.find("실시간")
    if idx != -1:
        around = re.sub(r"\s+", " ", html[idx - 300:idx + 500])
        print(f"    '실시간' 주변: {around!r}")


def probe_zum():
    print("\n### 줌")
    try:
        html = get("https://zum.com/").text
    except Exception as exc:  # noqa: BLE001
        print(f"  [실패] {exc}")
        return
    m = re.search(r'id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if m:
        try:
            data = json.loads(m.group(1))
            print(f"    __NEXT_DATA__ 최상위 키: {list(data.keys())}")
            page = (data.get("props") or {}).get("pageProps") or {}
            print(f"    pageProps 키: {list(page.keys())[:25]}")
            # 이슈/키워드로 보이는 가지를 찾아 본다
            def walk(node, path=""):
                if isinstance(node, dict):
                    for k, v in node.items():
                        if re.search(r"issue|keyword|rank|trend", k, re.I):
                            print(f"    후보 {path}/{k}: {json.dumps(v, ensure_ascii=False)[:300]}")
                        walk(v, path + "/" + k)
                elif isinstance(node, list):
                    for v in node[:3]:
                        walk(v, path + "[]")
            walk(page)
        except Exception as exc:  # noqa: BLE001
            print(f"    __NEXT_DATA__ 파싱 실패: {exc}")
    else:
        print("    __NEXT_DATA__ 없음")
        idx = html.find("이슈")
        if idx != -1:
            around = re.sub(r"\s+", " ", html[idx - 200:idx + 400])
            print(f"    '이슈' 주변: {around!r}")


def probe_dc():
    print("\n### 디시 실시간 베스트")
    try:
        html = get("https://gall.dcinside.com/board/lists/?id=dcbest").text
    except Exception as exc:  # noqa: BLE001
        print(f"  [실패] {exc}")
        return
    titles = re.findall(r'<a href="/board/view/\?id=dcbest[^"]*"[^>]*>([^<]{2,80})</a>', html)
    titles = [t.strip() for t in titles if t.strip()]
    show("글 제목", titles)
    print(f"    총 {len(titles)}건")


def probe_google():
    print("\n### 구글 트렌드 RSS")
    try:
        xml = get("https://trends.google.com/trending/rss?geo=KR").text
        titles = re.findall(r"<title>(.*?)</title>", xml, re.S)[1:]
        show("키워드", [t.strip() for t in titles])
    except Exception as exc:  # noqa: BLE001
        print(f"  [실패] {exc}")


def main():
    for fn in (probe_nate, probe_daum, probe_zum, probe_dc, probe_google):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"  [예외] {fn.__name__}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
