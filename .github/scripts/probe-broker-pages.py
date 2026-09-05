#!/usr/bin/env python3
"""Probe — 증권사별 CMA 금리 / 장외채권·단기사채 페이지가 어디인지 찾는다.

앞선 조사로 못박은 것
  - 증권사별 CMA 금리도, 장외채권 판매 목록도 모아 주는 공개 피드가 없다.
    금융투자협회 전자공시에는 CMA 항목 자체가 없다.
  - 증권사 홈페이지는 대부분 1.8~7.5KB 짜리 자바스크립트 껍데기라
    그냥 받아서는 아무것도 안 나온다. 브라우저로 그려야 한다.

그래서 브라우저로 홈페이지를 열어 링크를 훑고, CMA·채권 관련 주소를 모은다.
주소를 알아야 파서를 쓸 수 있다. 아무것도 쓰지 않는다.

1차에서 알아낸 것
  - 한국투자증권(링크 870개)과 KB증권(884개)은 잘 읽힌다. KB 에서는
    장내채권매매·장외채권매매·단기사채매매 메뉴를 그대로 찾았다.
  - 미래에셋·삼성·NH·키움은 링크가 0개였다. 3.5초로는 화면이 덜 그려진다.
  - 신한은 30초 안에 안 열렸다.
  - 대신증권은 eval_on_selector_all 이 깨졌다. 사이트가 페이지 안에서
    무언가를 덮어써 Playwright 선택자 엔진과 부딪힌다. 그래서 선택자 엔진을
    쓰지 않고 브라우저에서 document.querySelectorAll 을 직접 돌린다.
  - 링크가 iframe 안에 있는 경우도 있어 프레임까지 훑는다.
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
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception as exc:  # noqa: BLE001
        print(f"  열기 실패: {str(exc)[:120]}", flush=True)
        return
    # 다 그려질 때까지 기다린다. 조용해지면 바로 넘어가고, 안 되면 8초에서 끊는다.
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(2500)

    # Playwright 선택자 엔진을 거치지 않는다. 대신증권처럼 페이지가 그 엔진과
    # 부딪히는 곳이 있어서, 브라우저에서 그냥 querySelectorAll 을 돌린다.
    GRAB = """() => Array.from(document.querySelectorAll('a'))
        .map(e => [ (e.innerText || e.textContent || '').trim().slice(0,40), e.href ])"""
    links = []
    for fr in [page.main_frame] + list(page.frames):
        try:
            got = fr.evaluate(GRAB)
        except Exception:  # noqa: BLE001
            continue
        if got:
            links.extend(got)
    # 프레임 목록에 메인이 또 들어 있어 같은 링크가 겹친다. 주소로 한 번 걸러낸다.
    uniq, seen = [], set()
    for t, h in links:
        if (t, h) not in seen:
            seen.add((t, h))
            uniq.append((t, h))
    links = uniq
    print(f"  링크 {len(links)}개 (프레임 {len(page.frames)}개)", flush=True)
    if not links:
        try:
            txt = page.evaluate("() => (document.body && document.body.innerText || '').slice(0,300)")
            # f-string 안에 역슬래시를 못 넣어(3.11) 밖에서 미리 정리한다.
            flat = re.sub(r"\s+", " ", txt)
            print(f"    본문 앞부분: {flat!r}", flush=True)
        except Exception:  # noqa: BLE001
            print("    본문도 못 읽음", flush=True)

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
        return hits[:3]

    cands = show("CMA", CMA_KEY) + show("채권", BOND_KEY)

    # 홈에 이미 금리가 찍혀 있는 경우도 있다.
    try:
        body = page.evaluate(
            "() => (document.body && document.body.innerText || '').slice(0,20000)")
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

    # 찾은 주소를 실제로 열어 본다. 금리가 보이면 쓸 수 있는 것이고,
    # 로그인 화면이 나오면 이 길은 막힌 것이다. 열어 봐야 알 수 있다.
    for text, href in cands[:4]:
        try:
            page.goto(href, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2000)
            txt = page.evaluate(
                "() => (document.body && document.body.innerText || '').slice(0,6000)")
        except Exception as exc:  # noqa: BLE001
            print(f"  [열기] {text!r} 실패: {str(exc)[:90]}", flush=True)
            continue
        flat = re.sub(r"\s+", " ", txt)
        rates = RATE_KEY.findall(flat)
        login = bool(re.search(r"로그인|공동인증|아이디를 입력", flat))
        print(f"  [열기] {text!r} 글자 {len(flat)} 금리표기 {len(rates)}개 "
              f"로그인요구={login}", flush=True)
        if rates:
            print(f"      {flat[:400]}", flush=True)


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
