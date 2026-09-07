#!/usr/bin/env python3
"""임시 프로브: 증권사마다 채권 목록이 어디서 오는지 찾는다.

NH 에서 통한 방법을 그대로 쓴다 — 화면을 긁지 말고 오가는 JSON 을 잡는다.
NH 는 목록을 그릴 때 inListData.json 을 부르는데 거기 종목명·등급·만기·
수익률이 다 들어 있었다. 다른 곳도 그럴 것이다.

메뉴가 javascript:void(0) 라 주소가 없는 곳이 많다. 그래서 링크를 따라가지
않고, 화면에서 '채권' 이 걸린 것을 찾아 직접 눌러 본다. 접혀 있어 안 보이는
메뉴도 요소에 클릭을 걸면 눌린다(NH·삼성에서 확인).

결과는 로그가 아니라 파일로 남긴다. 액션 로그가 20~40분씩 늦게 올라온다.
"""
import json
import os
import re
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent.parent / "probe-out" / "brokers.txt"

BROKERS = [
    ("삼성증권", "https://www.samsungpop.com/published/main/index_mbw.html"),
    ("키움증권", "https://www1.kiwoom.com/m/main"),
    ("한국투자증권", "https://m.koreainvestment.com/mobile/index.jsp"),
    ("미래에셋증권", "https://securities.miraeasset.com/mw/main.do"),
    ("신한투자증권", "https://m.shinhansec.com/"),
    ("KB증권", "https://m.kbsec.com/"),
    ("하나증권", "https://m.hanaw.com/"),
    ("대신증권", "https://m.daishin.com/"),
]
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

# 이런 이름이 붙은 것만 눌러 본다. '채권형 펀드' 같은 건 목록이 아니다.
WANT = re.compile(r"^(장외채권|장내채권|국내채권|채권|채권/RP|채권매매|채권 ?투자|"
                  r"장외채권매매|장내채권매매|채권상품|채권 ?목록)")
SKIP = re.compile(r"펀드|전망|리포트|이슈|쿠폰|해외|안내|이란|앱|App|Weekly")
# 응답이 채권 목록 같은지 보는 잣대
BONDY = re.compile(r"채권|bond|수익률|ert|yld|만기|rdmp|isnm", re.I)
DECI = re.compile(r"\d+\.\d{2,3}")

lines = []


def say(s=""):
    lines.append(str(s))


def clickables(pg):
    return pg.evaluate("""() => Array.from(
        document.querySelectorAll('a,button,li,span,[onclick]')).map((e,i) => ({
          i, t: (e.innerText||'').replace(/\\s+/g,' ').trim()
        })).filter(x => x.t && x.t.length <= 12 && /채권/.test(x.t))""")


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(locale="ko-KR", user_agent=UA,
                         viewport={"width": 414, "height": 1000},
                         is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    # 요소를 못 찾으면 기본 30초를 기다린다. 여덟 곳 × 세 번이면 그것만
    # 12분이라 작업 제한을 넘겼다. 못 찾으면 빨리 포기하게 한다.
    pg.set_default_timeout(8000)
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

    half = os.environ.get("HALF", "1")
todo = BROKERS[:4] if half == "1" else BROKERS[4:]
say(f"# 이번 차례: {[b[0] for b in todo]}")
for name, home in todo:
        say("=" * 72)
        say(f"{name}  {home}")
        hits.clear()
        try:
            pg.goto(home, wait_until="domcontentloaded", timeout=25000)
            pg.wait_for_timeout(4000)
            say(f"  도착: {pg.url[:120]}")

            cands = [c for c in clickables(pg)
                     if WANT.match(c["t"]) and not SKIP.search(c["t"])]
            seen, uniq = set(), []
            for c in cands:
                if c["t"] in seen:
                    continue
                seen.add(c["t"])
                uniq.append(c)
            say(f"  누를 만한 것: {[c['t'] for c in uniq][:8]}")

            for c in uniq[:3]:
                try:
                    pg.get_by_text(c["t"], exact=True).first.evaluate("e => e.click()")
                    pg.wait_for_timeout(5000)
                    body = pg.evaluate(
                        "() => (document.body&&document.body.innerText||'')"
                        ".replace(/\\s+/g,' ')")
                    pct = re.findall(r"\d+\.\d{1,3} ?%", body)
                    say(f"  ── '{c['t']}' → {pg.url[:120]}")
                    say(f"     본문 {len(body)}자 · 수익률꼴 {len(pct)}개 {pct[:10]}")
                    say(f"     {body[:900]}")
                except Exception as e:  # noqa: BLE001
                    say(f"  ── '{c['t']}' 못 눌렀다: {str(e)[:90]}")

            say(f"  채권 같은 응답 {len(hits)}개")
            got = set()
            for u, n, head in hits:
                if u in got:
                    continue
                got.add(u)
                say(f"    · {u[:160]}  ({n}바이트)")
                say(f"      {head[:700]}")
        except Exception:
            say("  !! 실패\n" + traceback.format_exc()[-400:])

    br.close()

OUT = OUT.with_name(f"brokers-{half}.txt")
OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"{OUT} 에 {len(lines)}줄 적음")
