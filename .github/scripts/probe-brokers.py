#!/usr/bin/env python3
"""임시 프로브: 증권사 채권 목록 주소를 하나씩 찍어 본다.

왜 클릭을 그만뒀나
  메뉴를 눌러 들어가는 방식은 못 찾을 때마다 기다리다 작업 제한을 넘겼다.
  대신 앞 프로브가 알려 준 주소 규칙을 가지고 곧바로 찍어 본다. 안 열리면
  바로 다음으로 넘어가니 멈출 일이 없다.

앞 프로브가 알려 준 것
  · 신한 m.shinhansec.com/mweb/fnin/bond/fbond1002 가 열린다. 다만 그 화면은
    채권 설명이지 목록이 아니다. 번호가 붙어 있으니 이웃 번호를 훑는다.
  · KB 는 상품 자료를 json 파일로 따로 낸다
    (m.kbsec.com/ndatatopweb/www/json/main/goods.json). 채권판이 있는지 본다.
  · 키움 국내채권은 error 페이지로 갔다. 다른 주소를 찾아야 한다.
  · 삼성·미래에셋은 눌러도 화면이 안 바뀌었다.

결과는 로그가 아니라 파일로 남긴다. 액션 로그가 20~40분씩 늦게 올라온다.
"""
import json
import re
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent.parent / "probe-out" / "brokers.txt"

SHINHAN = [(f"신한 fbond{n}", f"https://m.shinhansec.com/mweb/fnin/bond/fbond{n}")
           for n in (1001, 1003, 1004, 1005, 1006, 1007)]
OTHERS = [
    ("KB goods.json", "https://m.kbsec.com/ndatatopweb/www/json/main/goods.json"),
    ("KB 채권메뉴", "https://m.kbsec.com/go.able?linkcd=m01010006"),
    ("삼성 mbw메인", "https://www.samsungpop.com/mbw/main/main.pop"),
    ("삼성 장외채권", "https://www.samsungpop.com/mbw/bond/bond_main.pop"),
    ("키움 국내채권", "https://www1.kiwoom.com/m/wm/bond/domesticBondList"),
    ("한국투자 채권", "https://m.koreainvestment.com/mobile/bond/bondList.jsp"),
    ("하나 채권", "https://m.hanaw.com/mw/fnnc/bond/main.cmd"),
    ("대신 채권", "https://m.daishin.com/mweb/product/bond/bondList"),
]
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

BONDY = re.compile(r"채권|bond|수익률|ert|yld|만기|rdmp|isnm", re.I)
DECI = re.compile(r"\d+\.\d{2,3}")
PCT = re.compile(r"\d+\.\d{1,3} ?%")

lines = []


def say(s=""):
    lines.append(str(s))


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(locale="ko-KR", user_agent=UA,
                         viewport={"width": 414, "height": 1000},
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
            if len(b) < 200 or not BONDY.search(b) or len(DECI.findall(b)) < 5:
                return
            hits.append((u, len(b), b[:900]))
        except Exception:  # noqa: BLE001
            pass

    pg.on("response", on_response)

    for name, url in SHINHAN + OTHERS:
        say("=" * 72)
        say(f"{name}  {url}")
        hits.clear()
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=20000)
            pg.wait_for_timeout(5000)
            body = pg.evaluate(
                "() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
            say(f"  도착 {pg.url[:130]}")
            say(f"  본문 {len(body)}자 · 수익률꼴 {len(PCT.findall(body))}개 "
                f"{PCT.findall(body)[:12]}")
            say(f"  {body[:1500]}")

            tabs = pg.evaluate(
                """() => Array.from(document.querySelectorAll('table')).map(t =>
                     Array.from(t.querySelectorAll('tr')).slice(0,6).map(r =>
                       Array.from(r.querySelectorAll('th,td')).map(c =>
                         (c.innerText||'').replace(/\\s+/g,' ').trim())
                     ).filter(cs => cs.some(x => x)))""")
            for i, t in enumerate([x for x in tabs if len(x) > 1][:2]):
                say(f"  [표{i}]")
                for r in t[:6]:
                    say("    " + json.dumps(r, ensure_ascii=False)[:220])

            if hits:
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

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"{OUT} 에 {len(lines)}줄 적음")
