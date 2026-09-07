#!/usr/bin/env python3
"""Probe 3차 — CMA 금리표를 실제로 뽑아내고, 장외채권 공개 소스를 찾는다.

2차에서 알아낸 것 (1·2차 판단을 뒤집는 부분이 있다)
  - '로그인요구' 판정이 틀렸다. 페이지에 '로그인' 글자만 있어도 True 가 되게
    짜 놔서, 정작 금리표가 다 보이는 페이지를 막힌 것으로 잘못 봤다.
    한국투자 CMA 페이지에는 "RP 투자형 수익률 … 기준일 2026.08.31" 이
    그대로 있었고, KB 11개·대신 24개의 금리 표기가 잡혔다.
  - 장외채권은 다르다. KB 만 메뉴가 있고(장외채권매매·단기사채매매) 열면
    482자에 금리 0개다. 로그인 뒤 화면이다. 나머지 7곳은 메뉴조차 없다.

그래서 이번엔
  (가) CMA 금리가 보이는 네 곳에서 표를 실제로 뽑아 본다. 숫자가 나와야
       화면에 올릴 수 있다.
  (나) 증권사 대신 공시 기관을 본다. 금융투자협회 채권정보센터와
       한국예탁결제원 세이브로에 장외채권·전자단기사채 공개 자료가 있는지.

아무것도 쓰지 않는다.
"""
import re
import sys

from playwright.sync_api import sync_playwright

CMA_PAGES = [
    ("한국투자증권", "https://securities.koreainvestment.com/main/mall/opencma/CmaInfo.jsp?cmd=TF02bb010000"),
    ("KB증권", "https://www.kbsec.com/go.able?linkcd=m01030002"),
    ("신한투자증권", "https://www.shinhansec.com/siw/wealth-management/cma/info/view.do"),
    ("미래에셋증권", "https://securities.miraeasset.com/mw/bnk/BNK1010M.do"),
]

# 증권사가 아니라 공시 기관. 회사별 판매 목록은 아니어도 공개 자료다.
PUBLIC_SOURCES = [
    ("금융투자협회 채권정보센터", "https://www.kofiabond.or.kr/"),
    ("채권정보센터 최종호가수익률", "https://www.kofiabond.or.kr/websquare/websquare.html?w2xPath=/wq/bond/BISBondSPrcInq.xml"),
    ("한국예탁결제원 세이브로", "https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/index.xml"),
]

RATE = re.compile(r"\d+\.\d{1,3}\s*%")


def text_of(page, limit=9000):
    return page.evaluate(
        "n => (document.body && document.body.innerText || '').slice(0,n)", limit)


def look_cma(page, name, url):
    print(f"\n=== {name}\n    {url}", flush=True)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(2500)
    except Exception as exc:  # noqa: BLE001
        print(f"    열기 실패: {str(exc)[:110]}", flush=True)
        return
    txt = text_of(page)
    flat = re.sub(r"\s+", " ", txt)
    rates = RATE.findall(flat)
    print(f"    글자 {len(flat)} · 금리표기 {len(rates)}개 {rates[:12]}", flush=True)

    # 기준일이 있으면 언제 자료인지 알 수 있다. 이게 없으면 못 쓴다.
    for m in re.finditer(r"기준일[^\d]{0,6}(\d{4}[.\-]\d{1,2}[.\-]\d{1,2})", flat):
        print(f"    기준일: {m.group(1)}", flush=True)

    # 표를 통째로 읽어 본다. 금리가 표 안에 있어야 파서를 쓸 수 있다.
    try:
        tables = page.evaluate("""() => Array.from(document.querySelectorAll('table')).map(t =>
            Array.from(t.querySelectorAll('tr')).slice(0,9).map(r =>
              Array.from(r.querySelectorAll('th,td')).map(c => (c.innerText||'').trim()).join(' | ')
            ).filter(x => x)
        ).filter(rows => rows.join(' ').match(/\\d+\\.\\d/))""")
    except Exception as exc:  # noqa: BLE001
        print(f"    표 못 읽음: {str(exc)[:80]}", flush=True)
        return
    print(f"    금리가 든 표 {len(tables)}개", flush=True)
    for i, rows in enumerate(tables[:3], 1):
        print(f"    --- 표 {i} ---", flush=True)
        for r in rows[:7]:
            print(f"      {r[:120]}", flush=True)


def look_public(page, name, url):
    print(f"\n=== {name}\n    {url}", flush=True)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(3000)
    except Exception as exc:  # noqa: BLE001
        print(f"    열기 실패: {str(exc)[:110]}", flush=True)
        return
    flat = re.sub(r"\s+", " ", text_of(page, 4000))
    print(f"    글자 {len(flat)}", flush=True)
    print(f"    {flat[:600]}", flush=True)
    hits = re.findall(r"[^ ]{0,12}(?:장외|단기사채|전단채|최종호가|수익률)[^ ]{0,12}", flat)
    print(f"    관련 낱말: {sorted(set(hits))[:14]}", flush=True)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            locale="ko-KR",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
            viewport={"width": 1400, "height": 1000})
        page = ctx.new_page()

        print("######## 가. CMA 금리표", flush=True)
        for name, url in CMA_PAGES:
            look_cma(page, name, url)

        print("\n\n######## 나. 장외채권·단기사채 공시 기관", flush=True)
        for name, url in PUBLIC_SOURCES:
            look_public(page, name, url)

        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
