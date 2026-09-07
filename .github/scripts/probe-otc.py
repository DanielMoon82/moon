#!/usr/bin/env python3
"""임시 프로브 2: 세이브로 단기사채 금리 화면을 눌러서 열어 본다.

앞 프로브에서 알아낸 것 — 세이브로도 채권정보센터도 표의 머리글만 그리고
내용은 비어 있다. 조회 단추를 눌러야 그때 값을 받아 온다. 그래서 이번엔
메뉴를 눌러 화면을 옮기고 조회까지 눌러 본다.
"""
import json
from playwright.sync_api import sync_playwright

START = ("https://seibro.or.kr/websquare/control.jsp?w2xPath=%2FIPORTAL%2Fuser%2F"
         "moneyMarke%2FBIP_CNTS04030V.xml&menuNo=940")
MENUS = ["발행금리조회", "매매금리조회", "단기금융증권만기수익률"]

GRAB = """() => Array.from(document.querySelectorAll('table')).map(t =>
    Array.from(t.querySelectorAll('tr')).map(r =>
      Array.from(r.querySelectorAll('th,td')).map(c => (c.innerText||'').replace(/\\s+/g,' ').trim())
    ).filter(cs => cs.some(x => x)))"""


def dump(pg, tag):
    tabs = [t for t in pg.evaluate(GRAB) if t and len(t) > 1]
    print(f"  -- {tag}: 여러 줄인 표 {len(tabs)}개")
    for i, t in enumerate(tabs[:4]):
        print(f"    [표{i}] {len(t)}행")
        for r in t[:10]:
            print("      ", json.dumps(r, ensure_ascii=False)[:240])


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(locale="ko-KR", viewport={"width": 1500, "height": 1200},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
    pg = ctx.new_page()
    pg.goto(START, wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(5000)

    for menu in MENUS:
        print("=" * 70)
        print("메뉴:", menu)
        try:
            # 메뉴는 접혀 있어 눈에 안 보인다. 보일 때까지 기다리면 시간만
            # 지나므로 요소에 직접 클릭을 걸어 준다.
            link = pg.get_by_text(menu, exact=True).first
            link.evaluate("el => el.click()")
            pg.wait_for_timeout(6000)
            print("  주소:", pg.url[:130])
            head = pg.evaluate("() => (document.body.innerText||'').replace(/\\s+/g,' ').slice(0,700)")
            print("  본문머리:", head)
            dump(pg, "조회 누르기 전")

            # 조회/검색 단추를 찾아 누른다. 이름이 회사마다 달라 몇 가지를 본다.
            pressed = ""
            for label in ["조회", "검색", "Search"]:
                try:
                    btn = pg.get_by_role("button", name=label).first
                    btn.click(timeout=4000)
                    pressed = label
                    break
                except Exception:
                    try:
                        btn = pg.locator(f"a:has-text('{label}'), input[value='{label}']").first
                        btn.click(timeout=4000)
                        pressed = label
                        break
                    except Exception:
                        continue
            print("  누른 단추:", pressed or "(못 찾음)")
            pg.wait_for_timeout(7000)
            dump(pg, "조회 누른 뒤")
        except Exception as e:
            print("  !! 실패", str(e)[:150])
    br.close()
