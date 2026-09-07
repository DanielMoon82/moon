#!/usr/bin/env python3
"""임시 프로브 4: NH 장내채권 목록 하나만 깊게 판다.

여기까지 알아낸 것
  · NH m.nhsec.com/finance/bond/bond/inList — 로그인 없이 판매 채권 목록이
    그대로 나온다. 종목명·종류·현재가·전일대비까지 보인다.
  · 다만 지금 보이는 건 가격이지 수익률이 아니다. 화면에 탭이 여럿 있다
    (장내채권/발행어음/RP, 그 아래 주식형/일반채권/소액채권).
  · 삼성·키움·한국투자·미래에셋은 메뉴가 자바스크립트라 주소가 없다.
    한 곳이라도 제대로 되는 걸 먼저 세우고 나서 늘린다.

무엇을 보는가
  탭을 하나씩 눌러 표를 통째로 뜨고, 그동안 오간 요청을 모두 적는다.
  수익률이 어느 탭에 있는지, 목록을 그리는 API 가 무엇인지 알아야 한다.
"""
import json
import re
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent.parent / "probe-out" / "bondlist.txt"
URL = "https://m.nhsec.com/finance/bond/bond/inList"
TABS = ["일반채권", "소액채권", "주식형 채권", "발행어음", "RP"]
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

TABLES = """() => Array.from(document.querySelectorAll('table')).map(t =>
    Array.from(t.querySelectorAll('tr')).slice(0,10).map(r =>
      Array.from(r.querySelectorAll('th,td')).map(c =>
        (c.innerText||'').replace(/\\s+/g,' ').trim())
    ).filter(cs => cs.some(x => x)))"""
# 표가 아니라 목록(ul/li)으로 그린 화면도 있어 그것도 뜬다.
LISTS = """() => Array.from(document.querySelectorAll('ul,ol')).map(u =>
    Array.from(u.children).slice(0,6).map(li =>
      (li.innerText||'').replace(/\\s+/g,' ').trim()).filter(Boolean)
  ).filter(a => a.length > 2 && a.some(x => /\\d/.test(x)))"""

lines = []
calls = []


def say(s=""):
    lines.append(str(s))


def dump(pg, tag):
    say(f"  ── {tag} — {pg.url[:130]}")
    body = pg.evaluate("() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
    say(f"     본문 {len(body)}자")
    say(f"     {body[:2000]}")
    for i, t in enumerate([x for x in pg.evaluate(TABLES) if len(x) > 1][:3]):
        say(f"     [표{i}]")
        for r in t[:10]:
            say("       " + json.dumps(r, ensure_ascii=False)[:260])
    for i, l in enumerate(pg.evaluate(LISTS)[:4]):
        say(f"     [목록{i}]")
        for r in l[:6]:
            say("       " + json.dumps(r, ensure_ascii=False)[:260])


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(locale="ko-KR", user_agent=UA,
                         viewport={"width": 414, "height": 1400},
                         is_mobile=True, has_touch=True, device_scale_factor=2)
    pg = ctx.new_page()

    def on_response(resp):
        try:
            u = resp.url
            if re.search(r"\.(png|jpg|jpeg|gif|css|woff2?|svg|ico)(\?|$)", u):
                return
            ct = (resp.headers or {}).get("content-type", "")
            if not any(k in ct for k in ("json", "xml", "text/plain")):
                return
            b = resp.text()
            if len(b) < 80:
                return
            calls.append((u, ct, len(b), b[:1200]))
        except Exception:  # noqa: BLE001
            pass

    pg.on("response", on_response)

    say("=" * 72)
    say(f"NH 장내채권  {URL}")
    try:
        pg.goto(URL, wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_timeout(8000)
        dump(pg, "처음")
        for tab in TABS:
            try:
                el = pg.get_by_text(tab, exact=True).first
                el.evaluate("e => e.click()")
                pg.wait_for_timeout(6000)
                dump(pg, f"탭: {tab}")
            except Exception as e:  # noqa: BLE001
                say(f"  ── 탭 {tab}: 못 눌렀다 — {str(e)[:110]}")
    except Exception:
        say("  !! 실패\n" + traceback.format_exc()[-600:])

    br.close()

say("")
say("=" * 72)
say(f"오간 요청 {len(calls)}개")
seen = set()
for u, ct, n, head in calls:
    if u in seen:
        continue
    seen.add(u)
    say(f"  · {u[:170]}")
    say(f"    {ct} {n}바이트")
    say(f"    {head[:1000]}")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"{OUT} 에 {len(lines)}줄 적음")
