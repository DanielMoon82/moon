#!/usr/bin/env python3
"""임시 프로브: 여러 증권사 채권을 모아 보여주는 곳이 웹을 여는지 본다.

증권사 여덟 곳을 직접 확인한 결과 채권 목록을 로그인 없이 웹에 여는 곳은
NH 하나뿐이었다. 나머지는 앱 안에서만 보여 주거나 로그인을 요구한다.

그래서 모아서 보여 주는 쪽을 본다.
  · 토스증권 — 웹판이 있다. 채권을 다루는지 본다.
  · 네이버페이 증권 — 국내 증시 자료를 웹으로 넓게 연다.
  · 한국거래소 정보데이터시스템 — 장내채권 시세를 공식으로 낸다.
    증권사별은 아니지만 종목별 수익률이 나오면 쓸모가 있다.

화면을 긁지 말고 오가는 JSON 을 잡는다. NH 를 뚫은 것도 그 방법이었다.
결과는 로그로 낸다.
"""
import json
import re
import traceback

from playwright.sync_api import sync_playwright

TARGETS = [
    ("토스증권", "https://www.tossinvest.com/"),
    ("네이버페이 증권", "https://m.stock.naver.com/"),
    ("네이버 시장지표", "https://finance.naver.com/marketindex/"),
    ("거래소 채권 시세", "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd?menuId=MDC0106"),
    ("거래소 정보데이터", "http://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd"),
]
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

PCT = re.compile(r"\d+\.\d{1,3} ?%")
BONDY = re.compile(r"채권|bond|수익률|만기|isnm|ert|yld", re.I)


def say(s=""):
    print(s, flush=True)


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(locale="ko-KR", user_agent=UA,
                         viewport={"width": 414, "height": 1100},
                         is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.set_default_timeout(6000)
    hits = []

    def on_response(resp):
        try:
            u = resp.url
            if re.search(r"\.(png|jpe?g|gif|css|woff2?|svg|ico)(\?|$)", u):
                return
            ct = (resp.headers or {}).get("content-type", "")
            if not any(k in ct for k in ("json", "xml", "text/plain")):
                return
            b = resp.text()
            if len(b) < 200 or not BONDY.search(b):
                return
            hits.append((u, len(b), b[:900]))
        except Exception:  # noqa: BLE001
            pass

    pg.on("response", on_response)

    for name, url in TARGETS:
        say("=" * 72)
        say(f"{name}  {url}")
        hits.clear()
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=25000)
            pg.wait_for_timeout(7000)
            body = pg.evaluate(
                "() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
            say(f"  도착 {pg.url[:140]}")
            say(f"  본문 {len(body)}자 · 수익률꼴 {len(PCT.findall(body))}개 {PCT.findall(body)[:12]}")
            say(f"  {body[:1200]}")

            # '채권' 이 걸린 링크만 따로 본다. 어디로 들어가야 하는지 알아야 한다.
            links = pg.evaluate(
                """() => Array.from(document.querySelectorAll('a,button,[onclick]')).map(e => ({
                     t: (e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,26),
                     h: (e.getAttribute('href')||'').slice(0,110),
                     o: (e.getAttribute('onclick')||'').slice(0,110)
                   })).filter(x => /채권|bond/i.test(x.t + ' ' + x.h + ' ' + x.o))""")
            seen, uniq = set(), []
            for l in links:
                k = (l["t"], l["h"], l["o"])
                if k not in seen:
                    seen.add(k)
                    uniq.append(l)
            say(f"  채권 걸린 링크 {len(uniq)}개")
            for l in uniq[:14]:
                say(f"    · '{l['t']}'  href={l['h']}  onclick={l['o']}")

            say(f"  채권 같은 응답 {len(hits)}개")
            got = set()
            for u, n, head in hits:
                if u in got:
                    continue
                got.add(u)
                say(f"    · {u[:150]}  ({n}바이트)")
                say(f"      {head[:700]}")
        except Exception:
            say("  !! 실패 " + traceback.format_exc().strip().split("\n")[-1][:160])

    br.close()

say("# 끝")
