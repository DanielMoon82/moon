#!/usr/bin/env python3
"""임시 프로브: 증권사 채권 매물 목록이 로그인 없이 보이는지 다시 본다.

앞서 'PC 웹 메뉴가 안 열린다' 는 것만 보고 '여덟 곳 다 로그인해야 한다' 고
단정했는데 틀렸다. 삼성증권 모바일웹은 로그인 단추가 그대로 있는 채로
판매 채권 수익률이 보인다(사용자 화면으로 확인). 모바일 쪽을 안 봤다.

그래서 이번엔 휴대폰인 척하고 각 증권사 모바일웹을 연다. 먼저 첫 화면에서
'채권' 이 걸린 링크를 모두 훑고, 그 링크를 따라가 표와 금리를 찍는다.
"""
import json
import re
from playwright.sync_api import sync_playwright

HOMES = [
    ("삼성증권", "https://www.samsungpop.com/published/main/index_mbw.html"),
    ("삼성증권-mbw", "https://www.samsungpop.com/mbw/start/start_main.pop"),
    ("한국투자증권", "https://m.truefriend.com/"),
    ("미래에셋증권", "https://m.securities.miraeasset.com/"),
    ("NH투자증권", "https://m.nhqv.com/"),
    ("키움증권", "https://m.kiwoom.com/"),
]
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

LINKS = """() => Array.from(document.querySelectorAll('a,button,li,span')).map(e => ({
    t: (e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,40),
    h: e.getAttribute('href') || e.getAttribute('data-url') || ''
  })).filter(x => /채권/.test(x.t) && x.t.length < 40)"""
RATE = re.compile(r"\d+\.\d{1,2}\s*%")


def look(pg, tag):
    body = pg.evaluate("() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
    rates = RATE.findall(body)
    print(f"  [{tag}] 본문 {len(body)}자 · 금리표기 {len(rates)}개 {rates[:12]}")
    if "채권" in body:
        i = body.find("채권")
        print("   ...", body[max(0, i - 60):i + 700])
    return body


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(locale="ko-KR", user_agent=MOBILE_UA,
                         viewport={"width": 414, "height": 900},
                         is_mobile=True, has_touch=True, device_scale_factor=2)
    pg = ctx.new_page()
    for name, url in HOMES:
        print("=" * 70)
        print(name, url)
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(5000)
            look(pg, "첫 화면")
            links = pg.evaluate(LINKS)
            seen, out = set(), []
            for l in links:
                key = (l["t"], l["h"])
                if key in seen:
                    continue
                seen.add(key)
                out.append(l)
            print(f"  '채권' 걸린 것 {len(out)}개:")
            for l in out[:25]:
                print("   ", json.dumps(l, ensure_ascii=False)[:200])
        except Exception as e:
            print("  !! 실패", str(e)[:130])
    br.close()
