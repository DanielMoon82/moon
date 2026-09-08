#!/usr/bin/env python3
"""임시 프로브: 거래소가 400 을 주는 이유를 가른다.

bld 후보 열한 개가 전부 400 이었다. 이름이 틀린 건지, 아니면 그냥 POST 로는
안 받아 주는 건지부터 갈라야 한다. 그래서 이미 되는 걸 아는 이름
(MDCMAIN00101, 앞 프로브에서 브라우저가 실제로 불렀다)을 같은 방식으로
던져 본다.
  · 그것도 400 이면 → 이름이 아니라 방식 문제다. 쿠키가 필요하다.
  · 그것만 되면 → 이름이 틀린 것이다.

그리고 화면 주소를 곧바로 연다. 메뉴와 jsp 이름이 짝지어 있으니
MDCSTAT114.jsp 를 열면 그 화면이 무슨 bld 를 부르는지 그대로 보인다.
지어내는 것보다 확실하다.
"""
import json
import re
import traceback
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

API = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
JSPS = [
    ("장외 채권수익률", "https://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT114.jsp"),
    ("상장채권 상세검색", "https://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT108.jsp"),
]


def say(s=""):
    print(s, flush=True)


# ── 1. 되는 걸 아는 이름을 같은 방식으로 던져 본다
say("=" * 72)
say("되는 걸 아는 이름으로 방식 확인  bld=dbms/MDC/MAIN/MDCMAIN00101")
try:
    body = urllib.parse.urlencode({"bld": "dbms/MDC/MAIN/MDCMAIN00101"}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "User-Agent": UA,
        "Referer": "https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read().decode("utf-8", "replace")
    say(f"  ✅ 그냥 POST 로도 된다 — {len(raw)}바이트")
    say(f"     {raw[:300]}")
    say("  → 400 은 이름이 틀려서다. 이름만 찾으면 된다.")
except Exception as exc:  # noqa: BLE001
    say(f"  ❌ 이것도 막힌다 — {type(exc).__name__}: {str(exc)[:120]}")
    say("  → 이름이 아니라 방식 문제다. 쿠키를 받아 와야 한다.")

# ── 2. 화면 주소를 곧바로 열어 무슨 bld 를 부르는지 본다
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(locale="ko-KR", user_agent=UA,
                         viewport={"width": 1400, "height": 1000})
    pg = ctx.new_page()
    pg.set_default_timeout(8000)
    calls = []

    def on_response(resp):
        try:
            if "getJsonData" not in resp.url:
                return
            calls.append(((resp.request.post_data or "")[:400],
                          resp.status, resp.text()[:1500]))
        except Exception:  # noqa: BLE001
            pass

    pg.on("response", on_response)

    for name, url in JSPS:
        say("=" * 72)
        say(f"{name}  {url}")
        calls.clear()
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=25000)
            pg.wait_for_timeout(5000)
            body = pg.evaluate(
                "() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
            say(f"  본문 {len(body)}자 · {body[:500]}")

            # 화면 안에 bld 가 글자로 박혀 있는 경우가 많다. 통째로 훑는다.
            html = pg.content()
            blds = sorted(set(re.findall(r"dbms/[A-Za-z0-9/_]+", html)))
            say(f"  화면에 박힌 bld {len(blds)}개: {blds[:12]}")

            for sel in ["#jsSearchButton", "a:has-text('조회')",
                        "button:has-text('조회')", "input[value='조회']"]:
                try:
                    pg.locator(sel).first.click(timeout=4000)
                    say(f"  조회 눌렀다: {sel}")
                    break
                except Exception:  # noqa: BLE001
                    continue
            pg.wait_for_timeout(8000)

            say(f"  요청 {len(calls)}건")
            for post, status, head in calls[:5]:
                say(f"    · [{status}] 보낸 값: {post}")
                say(f"      받은 값: {head[:900]}")
        except Exception:
            say("  !! 실패 " + traceback.format_exc().strip().split("\n")[-1][:170])

    br.close()

say("# 끝")
