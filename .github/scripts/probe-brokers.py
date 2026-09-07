#!/usr/bin/env python3
"""임시 프로브(마지막): 남은 두 곳만 판다.

여기까지 밝혀진 것
  · 신한 fbond1002 는 '채권이란 무엇인가' 설명 페이지다. 목록으로 가는
    링크가 아예 없다(#con_01 같은 문서 내 앵커뿐).
  · KB 채권 메뉴는 자기 자신만 가리킨다. 하위 메뉴가 없다.
  · 키움은 채권 메뉴가 전부 javascript:void(0) 이고 여는 함수도 노출이 없다.
  · 한국투자는 채권이 data-screen-no=8407 이다. 앱 화면 번호라 웹 주소가 없다.
  · 하나는 사이트가 아예 안 열린다(두 번 다 시간 초과).
  · 대신은 우대채권이 /g.ds?m=3812&p=3698&v=2732 로 진짜 주소가 있다.
  · 삼성은 openMenu 가 _common.open_menu 를 부른다. 그 안을 봐야 한다.

그래서 대신 주소를 열어 보고, 삼성은 _common.open_menu 본문을 캔 뒤
실제로 장외채권 메뉴를 눌러 어디로 가는지 본다.
"""
import json
import re
import traceback

from playwright.sync_api import sync_playwright

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")
PCT = re.compile(r"\d+\.\d{1,3} ?%")
BONDY = re.compile(r"채권|bond|수익률|만기|isnm|ert", re.I)


def say(s=""):
    print(s, flush=True)


def dump(pg, tag):
    body = pg.evaluate("() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
    say(f"  ── {tag} → {pg.url[:140]}")
    say(f"     본문 {len(body)}자 · 수익률꼴 {len(PCT.findall(body))}개 {PCT.findall(body)[:12]}")
    say(f"     {body[:1800]}")
    tabs = pg.evaluate(
        """() => Array.from(document.querySelectorAll('table')).map(t =>
             Array.from(t.querySelectorAll('tr')).slice(0,8).map(r =>
               Array.from(r.querySelectorAll('th,td')).map(c =>
                 (c.innerText||'').replace(/\\s+/g,' ').trim())
             ).filter(cs => cs.some(x => x)))""")
    for i, t in enumerate([x for x in tabs if len(x) > 1][:3]):
        say(f"     [표{i}]")
        for r in t[:8]:
            say("       " + json.dumps(r, ensure_ascii=False)[:240])


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
            if len(b) < 150 or not BONDY.search(b):
                return
            hits.append((u, len(b), b[:1100]))
        except Exception:  # noqa: BLE001
            pass

    pg.on("response", on_response)

    # 1) 대신증권 우대채권 — 주소가 확실히 있는 곳
    say("=" * 72)
    say("대신 우대채권")
    hits.clear()
    try:
        pg.goto("https://m.daishin.com/g.ds?m=3812&p=3698&v=2732",
                wait_until="domcontentloaded", timeout=25000)
        pg.wait_for_timeout(7000)
        dump(pg, "우대채권")
        say(f"  채권 같은 응답 {len(hits)}개")
        for u, n, head in hits[:5]:
            say(f"    · {u[:150]}  ({n}바이트)")
            say(f"      {head[:800]}")
    except Exception:
        say("  !! 실패 " + traceback.format_exc().strip().split("\n")[-1][:160])

    # 2) 삼성 — 메뉴 여는 속을 보고 실제로 눌러 본다
    say("=" * 72)
    say("삼성 장외채권매매")
    hits.clear()
    try:
        pg.goto("https://www.samsungpop.com/published/main/index_mbw.html",
                wait_until="domcontentloaded", timeout=25000)
        pg.wait_for_timeout(5000)
        src = pg.evaluate(
            """() => { try { return (window._common && window._common.open_menu)
                 ? window._common.open_menu.toString().slice(0,1500) : '(없음)'; }
               catch (e) { return '오류: ' + e.message; } }""")
        say("  [_common.open_menu]")
        say("    " + src.replace("\n", "\n    "))
        pg.evaluate("() => { try { window.openMenu('M1494913117909'); } catch (e) {} }")
        pg.wait_for_timeout(8000)
        dump(pg, "openMenu 누른 뒤")
        say(f"  채권 같은 응답 {len(hits)}개")
        for u, n, head in hits[:5]:
            say(f"    · {u[:150]}  ({n}바이트)")
            say(f"      {head[:800]}")
    except Exception:
        say("  !! 실패 " + traceback.format_exc().strip().split("\n")[-1][:160])

    br.close()

say("# 끝")
