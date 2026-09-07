#!/usr/bin/env python3
"""임시 프로브 3: 증권사 채권 목록의 실제 주소와 API 를 찾는다.

프로브 2 에서 알아낸 것
  · NH 는 채권 메뉴에 진짜 주소가 붙어 있다 — /finance/bond/bond/inList
  · 삼성은 메뉴 코드로 연다 — openMenu('M1494913117909') 가 장외채권매매
  · 키움·한국투자·미래에셋은 메뉴가 전부 javascript:void(0) 라 주소가 없다
  · 삼성 mbw 첫 화면은 509자짜리 껍데기다. 화면에서 본 '채권상품 수익률순'
    묶음은 다른 데서 온다.

그래서 이번엔 화면을 긁지 않고 오가는 요청을 다 본다. 목록을 그리는 API 를
찾으면 그걸 부르는 게 화면 긁기보다 훨씬 튼튼하다.

결과는 로그가 아니라 파일로 남긴다. 액션 로그가 20~40분씩 늦게 올라온다.
"""
import json
import re
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent.parent / "probe-out" / "bondlist.txt"

TARGETS = [
    ("NH-장내채권", "https://m.nhqv.com/finance/bond/bond/inList"),
    ("NH-장외채권", "https://m.nhqv.com/finance/bond/bond/outList"),
    ("삼성-장외채권매매", "https://www.samsungpop.com/?MENU_CODE=M1494913117909"),
    ("삼성-장내채권매매", "https://www.samsungpop.com/?MENU_CODE=M1494913105917"),
    ("삼성-RP/채권", "https://www.samsungpop.com/?MENU_CODE=M1494912868905"),
    ("한국투자-채권", "https://m.truefriend.com/main/bond/bond/_main.jsp"),
    ("키움-국내채권", "https://www.kiwoom.com/h/invest/bond/VBondDomesticMainView"),
]
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

RATE = re.compile(r"\d+\.\d{1,2}\s*%")
# 응답 안에 이런 낱말이 있으면 채권 목록일 가능성이 있다.
JUICY = re.compile(r"수익률|만기일|잔존|채권|종목명|표면이율|민평", re.I)

lines = []


def say(s=""):
    lines.append(str(s))


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(locale="ko-KR", user_agent=UA,
                         viewport={"width": 414, "height": 900},
                         is_mobile=True, has_touch=True, device_scale_factor=2)
    pg = ctx.new_page()

    seen_responses = []

    def on_response(resp):
        try:
            url = resp.url
            if any(url.endswith(x) for x in (".png", ".jpg", ".gif", ".css", ".woff", ".woff2", ".svg", ".ico")):
                return
            ct = (resp.headers or {}).get("content-type", "")
            if not any(k in ct for k in ("json", "xml", "text", "javascript")):
                return
            body = resp.text()
            if len(body) < 60 or not JUICY.search(body):
                return
            seen_responses.append((url, ct, len(body), body[:1400]))
        except Exception:  # noqa: BLE001
            pass

    pg.on("response", on_response)

    for name, url in TARGETS:
        say("=" * 72)
        say(f"{name}  {url}")
        seen_responses.clear()
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(9000)
            body = pg.evaluate(
                "() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
            rates = RATE.findall(body)
            say(f"  최종 주소: {pg.url[:140]}")
            say(f"  본문 {len(body)}자 · 금리표기 {len(rates)}개 {rates[:15]}")
            say(f"  본문: {body[:1400]}")

            tabs = pg.evaluate(
                """() => Array.from(document.querySelectorAll('table')).map(t =>
                     Array.from(t.querySelectorAll('tr')).slice(0,8).map(r =>
                       Array.from(r.querySelectorAll('th,td')).map(c =>
                         (c.innerText||'').replace(/\\s+/g,' ').trim())
                     ).filter(cs => cs.some(x => x)))""")
            tabs = [t for t in tabs if len(t) > 1]
            say(f"  줄 있는 표 {len(tabs)}개")
            for i, t in enumerate(tabs[:4]):
                say(f"    [표{i}]")
                for r in t[:8]:
                    say("      " + json.dumps(r, ensure_ascii=False)[:240])

            say(f"  볼 만한 응답 {len(seen_responses)}개")
            for u, ct, n, head in seen_responses[:8]:
                say(f"    · {u[:150]}")
                say(f"      {ct} {n}바이트")
                say(f"      {head[:900]}")
        except Exception:
            say("  !! 실패\n" + traceback.format_exc()[-500:])

    br.close()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"{OUT} 에 {len(lines)}줄 적음")
