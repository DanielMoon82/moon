#!/usr/bin/env python3
"""임시 프로브: 증권사 채권 매물이 로그인 없이 보이는지 본다.

왜 결과를 파일로 남기는가
  이 컨테이너는 증권사 사이트로 못 나간다(프록시가 막는다). 그래서 액션에서만
  볼 수 있는데, 액션 로그가 20~40분씩 늦게 올라온다. 로그 대신 파일로 적어
  커밋하면 곧바로 받아 읽을 수 있다.

무엇을 보는가
  앞서 PC 웹 메뉴만 보고 '여덟 곳 다 로그인해야 한다' 고 단정했는데 틀렸다.
  삼성증권 모바일웹은 로그인 안 해도 판매 채권 수익률이 보인다.
  그래서 휴대폰인 척하고 각 증권사 모바일웹을 연다. 첫 화면을 훑고,
  '채권' 이 걸린 링크를 따라 들어가 표와 금리를 적는다.
"""
import re
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent.parent / "probe-out" / "bondlist.txt"

HOMES = [
    ("삼성증권", "https://www.samsungpop.com/published/main/index_mbw.html"),
    ("삼성증권-시작", "https://www.samsungpop.com/mbw/start/start_main.pop"),
    ("한국투자증권", "https://m.truefriend.com/"),
    ("미래에셋증권", "https://m.securities.miraeasset.com/"),
    ("NH투자증권", "https://m.nhqv.com/"),
    ("키움증권", "https://m.kiwoom.com/"),
]
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

LINKS = """() => Array.from(document.querySelectorAll('a,button,[onclick],[data-url]')).map(e => ({
    t: (e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,36),
    h: e.getAttribute('href') || e.getAttribute('data-url') || '',
    o: (e.getAttribute('onclick')||'').slice(0,120)
  })).filter(x => /채권/.test(x.t))"""
RATE = re.compile(r"\d+\.\d{1,2}\s*%")

lines = []


def say(s=""):
    lines.append(str(s))


def snapshot(pg, tag):
    body = pg.evaluate("() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
    rates = RATE.findall(body)
    say(f"  [{tag}] {pg.url[:120]}")
    say(f"  본문 {len(body)}자 · 금리표기 {len(rates)}개 {rates[:15]}")
    # '채권' 이 나오는 자리마다 앞뒤를 떠 본다. 목록이 거기 있을 것이다.
    for m in list(re.finditer("채권", body))[:4]:
        i = m.start()
        say("   … " + body[max(0, i - 80):i + 500])
    return body


def run(pg, name, url):
    say("=" * 72)
    say(f"{name}  {url}")
    try:
        pg.goto(url, wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_timeout(6000)
        snapshot(pg, "첫 화면")
        seen, links = set(), []
        for l in pg.evaluate(LINKS):
            key = (l["t"], l["h"], l["o"])
            if key not in seen:
                seen.add(key)
                links.append(l)
        say(f"  '채권' 걸린 것 {len(links)}개")
        for l in links[:30]:
            say(f"    · {l['t']!r} href={l['h'][:90]!r} onclick={l['o'][:90]!r}")
        # 주소가 붙은 링크는 따라 들어가 본다.
        followed = 0
        for l in links:
            href = l["h"]
            if not href or href.startswith(("#", "javascript")):
                continue
            if followed >= 3:
                break
            followed += 1
            try:
                pg.goto(href if href.startswith("http") else
                        re.sub(r"(https?://[^/]+).*", r"\1", url) + href,
                        wait_until="domcontentloaded", timeout=25000)
                pg.wait_for_timeout(6000)
                snapshot(pg, f"따라감: {l['t']}")
            except Exception as e:  # noqa: BLE001
                say(f"  따라가기 실패 {l['t']!r}: {str(e)[:90]}")
    except Exception:
        say("  !! 실패\n" + traceback.format_exc()[-600:])


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(locale="ko-KR", user_agent=UA,
                         viewport={"width": 414, "height": 900},
                         is_mobile=True, has_touch=True, device_scale_factor=2)
    pg = ctx.new_page()
    for name, url in HOMES:
        run(pg, name, url)
    br.close()

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"{OUT} 에 {len(lines)}줄 적음")
