#!/usr/bin/env python3
"""임시 프로브: 한국거래소 채권 통계 화면에서 자료 API 를 캔다.

앞 프로브가 길을 열어 줬다. 거래소 정보데이터시스템에 이런 메뉴가 있다.
  · 장외 채권수익률      MDCSTAT114   ← 처음 찾던 바로 그것
  · 상장채권 상세검색    MDCSTAT108
  · 상장채권 발행정보    MDCSTAT109

증권사별 매물은 아니지만 거래소가 내는 공식 자료다. 증권사 여덟 곳이
전부 앱 안에 가둬 둔 것과 달리 여기는 열려 있다.

거래소 화면은 조회 단추를 눌러야 값을 받아 온다(세이브로와 같다).
그때 오가는 JSON 을 잡으면 그다음부턴 그걸 바로 부르면 된다.
"""
import json
import re
import traceback

from playwright.sync_api import sync_playwright

MAIN = "https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd"
MENUS = ["장외 채권수익률", "상장채권 상세검색"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def say(s=""):
    print(s, flush=True)


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(locale="ko-KR", user_agent=UA,
                         viewport={"width": 1400, "height": 1100})
    pg = ctx.new_page()
    pg.set_default_timeout(8000)
    calls = []

    def on_response(resp):
        try:
            u = resp.url
            # 거래소는 자료를 이 한 곳으로 다 받아 온다.
            if "getJsonData" not in u and "MDCSTAT" not in u:
                return
            b = resp.text()
            if len(b) < 60:
                return
            calls.append((u, resp.request.method,
                          (resp.request.post_data or "")[:600], len(b), b[:1600]))
        except Exception:  # noqa: BLE001
            pass

    pg.on("response", on_response)

    for menu in MENUS:
        say("=" * 72)
        say(f"메뉴: {menu}")
        calls.clear()
        try:
            pg.goto(MAIN, wait_until="domcontentloaded", timeout=25000)
            pg.wait_for_timeout(4000)
            # 메뉴는 접혀 있을 수 있어 요소에 직접 클릭을 건다.
            pg.get_by_text(menu, exact=True).first.evaluate("e => e.click()")
            pg.wait_for_timeout(7000)
            say(f"  도착 {pg.url[:150]}")

            # 조회 단추를 찾아 누른다. 거래소는 이걸 눌러야 값이 온다.
            pressed = ""
            for sel in ["#jsSearchButton", "a.btn_hdr:has-text('조회')",
                        "button:has-text('조회')", "a:has-text('조회')",
                        "input[value='조회']"]:
                try:
                    pg.locator(sel).first.click(timeout=4000)
                    pressed = sel
                    break
                except Exception:  # noqa: BLE001
                    continue
            say(f"  누른 단추: {pressed or '(못 찾음)'}")
            pg.wait_for_timeout(9000)

            body = pg.evaluate(
                "() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
            say(f"  본문 {len(body)}자")
            say(f"  {body[:900]}")
            tabs = pg.evaluate(
                """() => Array.from(document.querySelectorAll('table')).map(t =>
                     Array.from(t.querySelectorAll('tr')).slice(0,8).map(r =>
                       Array.from(r.querySelectorAll('th,td')).map(c =>
                         (c.innerText||'').replace(/\\s+/g,' ').trim())
                     ).filter(cs => cs.some(x => x)))""")
            for i, t in enumerate([x for x in tabs if len(x) > 1][:3]):
                say(f"  [표{i}]")
                for r in t[:8]:
                    say("    " + json.dumps(r, ensure_ascii=False)[:250])

            say(f"  자료 요청 {len(calls)}건")
            for u, m, post, n, head in calls[:6]:
                say(f"    · {m} {u[:140]}  ({n}바이트)")
                if post:
                    say(f"      보낸 값: {post}")
                say(f"      받은 값: {head[:1100]}")
        except Exception:
            say("  !! 실패 " + traceback.format_exc().strip().split("\n")[-1][:170])

    br.close()

say("# 끝")
