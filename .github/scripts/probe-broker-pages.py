#!/usr/bin/env python3
"""Probe — 증권사별 CMA 금리 / 장외채권·단기사채 페이지가 어디인지 찾는다.

앞선 조사로 못박은 것
  - 증권사별 CMA 금리도, 장외채권 판매 목록도 모아 주는 공개 피드가 없다.
    금융투자협회 전자공시에는 CMA 항목 자체가 없다.
  - 증권사 홈페이지는 대부분 1.8~7.5KB 짜리 자바스크립트 껍데기라
    그냥 받아서는 아무것도 안 나온다. 브라우저로 그려야 한다.

그래서 브라우저로 홈페이지를 열어 링크를 훑고, CMA·채권 관련 주소를 모은다.
주소를 알아야 파서를 쓸 수 있다. 아무것도 쓰지 않는다.
"""
import re
import sys

from playwright.sync_api import sync_playwright

BROKERS = [
    ("미래에셋증권", "https://securities.miraeasset.com/"),
    ("삼성증권", "https://www.samsungpop.com/"),
    ("NH투자증권", "https://www.nhqv.com/"),
    ("한국투자증권", "https://securities.koreainvestment.com/"),
    ("KB증권", "https://www.kbsec.com/"),
    ("키움증권", "https://www.kiwoom.com/"),
    ("신한투자증권", "https://www.shinhansec.com/"),
    ("대신증권", "https://www.daishin.com/"),
]

CMA_KEY = re.compile(r"CMA|씨엠에이|종합자산관리", re.I)
BOND_KEY = re.compile(r"장외채권|채권상품|채권\s*몰|전자단기사채|단기사채|채권매매|채권 ?판매")
RATE_KEY = re.compile(r"\d+\.\d{1,3}\s*%")


def look(page, name, url):
    print(f"\n=== {name} {url}", flush=True)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3500)
    except Exception as exc:  # noqa: BLE001
        print(f"  열기 실패: {str(exc)[:120]}", flush=True)
        return
    try:
        links = page.eval_on_selector_all(
            "a", "els => els.map(e => [ (e.innerText||'').trim().slice(0,40), e.href ])")
    except Exception as exc:  # noqa: BLE001
        print(f"  링크 못 읽음: {str(exc)[:120]}", flush=True)
        return
    print(f"  링크 {len(links)}개", flush=True)

    def show(label, rx):
        hits, seen = [], set()
        for text, href in links:
            if not href or href.startswith("javascript"):
                continue
            if rx.search(text) or rx.search(href):
                key = href.split("#")[0]
                if key in seen:
                    continue
                seen.add(key)
                hits.append((text, href))
        print(f"  [{label}] {len(hits)}개", flush=True)
        for t, h in hits[:8]:
            print(f"    {t!r} -> {h}", flush=True)

    show("CMA", CMA_KEY)
    show("채권", BOND_KEY)

    # 홈에 이미 금리가 찍혀 있는 경우도 있다.
    try:
        body = page.inner_text("body")[:20000]
        near = []
        for m in CMA_KEY.finditer(body):
            s = max(0, m.start() - 80)
            chunk = re.sub(r"\s+", " ", body[s:m.start() + 120])
            if RATE_KEY.search(chunk):
                near.append(chunk)
        if near:
            print(f"  [홈에 찍힌 CMA 금리] {near[:3]}", flush=True)
    except Exception:  # noqa: BLE001
        pass


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            locale="ko-KR",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
            viewport={"width": 1400, "height": 1000})
        page = ctx.new_page()
        for name, url in BROKERS:
            look(page, name, url)
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
