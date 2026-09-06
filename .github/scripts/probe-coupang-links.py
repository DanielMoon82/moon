#!/usr/bin/env python3
"""Probe — 홈페이지에 걸린 쿠팡 파트너스 단축링크가 어떤 제품인지 확인한다.

여행용품 카드의 제품명이 "샘소나이트 등", "2만원대 라인업"처럼 두루뭉술하다.
링크는 진짜인데 그 링크가 무엇을 가리키는지 모르면 제품명을 정확히 적을 수
없다. 엉뚱한 제품명을 적으면 링크와 설명이 어긋나 더 나쁘다.

그래서 단축링크를 따라가 최종 주소와 제목을 읽는다. 아무것도 쓰지 않는다.
"""
import re
import sys

import requests

TIMEOUT = 25
UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def main():
    html = open("index.html", encoding="utf-8").read()
    links = re.findall(r'href="(https://link\.coupang\.com/a/[A-Za-z0-9]+)"', html)
    print(f"찾은 링크 {len(links)}개\n")

    for i, url in enumerate(links, 1):
        print(f"[{i}] {url}")
        try:
            r = requests.get(url, headers=UA, timeout=TIMEOUT, allow_redirects=True)
        except Exception as exc:  # noqa: BLE001
            print(f"    실패: {str(exc)[:110]}\n")
            continue
        print(f"    {r.status_code} {len(r.text)}자")
        print(f"    최종 주소: {r.url[:150]}")
        # 제품 페이지라면 제목이나 og:title 에 제품명이 들어 있다.
        for pat, label in (
            (r'<meta[^>]+property="og:title"[^>]+content="([^"]{4,200})"', "og:title"),
            (r'<title>([^<]{4,200})</title>', "title"),
            (r'"productName"\s*:\s*"([^"]{4,200})"', "productName"),
        ):
            m = re.search(pat, r.text, re.I)
            if m:
                print(f"    {label}: {m.group(1).strip()[:160]}")
        price = re.search(r'"salePrice"\s*:\s*(\d+)|(\d{1,3}(?:,\d{3})+)\s*원', r.text)
        if price:
            print(f"    가격 후보: {price.group(0)[:40]}")
        if "로봇" in r.text or "captcha" in r.text.lower() or len(r.text) < 1500:
            print(f"    ! 봇 검사 또는 빈 응답으로 보인다. 앞부분: {r.text[:200]!r}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
