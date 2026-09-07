#!/usr/bin/env python3
"""임시 프로브: 장외채권·단기사채 공개 자료를 긁을 수 있는지 본다.

증권사별 장외채권 매물 목록은 여덟 곳 모두 로그인을 요구한다(확인함).
그래서 대신 볼 수 있는 공개 자료 두 곳을 확인한다.
  · 금융투자협회 채권정보센터 — 등급·만기별 장외 거래 대표 수익률
  · 세이브로(한국예탁결제원) — 전자단기사채 발행 정보
둘 다 WebSquare 라 예전에 0자로 나온 적이 있어, 이번엔 오래 기다려 본다.
"""
import json
from playwright.sync_api import sync_playwright

TARGETS = [
    ("KOFIA 장외거래대표수익률",
     "https://www.kofiabond.or.kr/websquare/websquare.html?w2xPath=%2Fxml%2FsubMain.xml"
     "&divisionId=MBIS01010020000000&parentDivisionId=MBIS01010000000000"
     "&parentMenuIndex=0&menuIndex=1"),
    ("SEIBro 단기사채",
     "https://seibro.or.kr/websquare/control.jsp?w2xPath=%2FIPORTAL%2Fuser%2FmoneyMarke%2F"
     "BIP_CNTS04030V.xml&menuNo=940"),
    ("SEIBro 채권종목검색",
     "https://seibro.or.kr/websquare/control.jsp?w2xPath=%2FIPORTAL%2Fuser%2Fbond%2F"
     "BIP_CNTS03002V.xml&menuNo=87"),
]
GRAB = """() => Array.from(document.querySelectorAll('table')).map(t =>
    Array.from(t.querySelectorAll('tr')).map(r =>
      Array.from(r.querySelectorAll('th,td')).map(c => (c.innerText||'').replace(/\\s+/g,' ').trim())
    ).filter(cs => cs.some(x => x)))"""

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(locale="ko-KR", viewport={"width": 1500, "height": 1200},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
    pg = ctx.new_page()
    for name, url in TARGETS:
        print("=" * 70)
        print(name)
        print(url)
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=45000)
            # WebSquare 는 뼈대만 먼저 오고 표를 나중에 그린다. 표가 생길 때까지 기다린다.
            try:
                pg.wait_for_function(
                    "() => document.querySelectorAll('table td').length > 8", timeout=25000)
            except Exception as e:
                print("   (표 기다리다 시간 초과)", str(e)[:60])
            pg.wait_for_timeout(4000)
            body = pg.evaluate("() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
            print(f"-- 본문 {len(body)}자")
            print("-- 본문:", body[:1500])
            tabs = [t for t in pg.evaluate(GRAB) if t]
            print(f"-- 내용 있는 표 {len(tabs)}개")
            for i, t in enumerate(tabs[:6]):
                print(f"  [표{i}] {len(t)}행")
                for r in t[:12]:
                    print("    ", json.dumps(r, ensure_ascii=False)[:260])
        except Exception as e:
            print("!! 실패", str(e)[:160])
    br.close()
