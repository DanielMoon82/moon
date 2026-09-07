#!/usr/bin/env python3
"""임시 프로브: 증권사 채권 목록 주소를 '추측' 말고 '캐낸다'.

앞 프로브에서 배운 것
  주소를 지어내 찍는 건 다 빗나갔다. 신한 fbond1001·1003~1007 은 전부
  '페이지를 찾을 수 없습니다', 키움·한국투자·대신도 오류 화면이었다.
  KB 의 goods.json 에는 펀드만 있고 채권은 없었다.

그래서 이번엔 열리는 게 확인된 화면에서 그 화면이 가진 것을 통째로 캔다.
  · 모든 링크의 href 와 onclick — 하위 메뉴 주소가 거기 적혀 있다
  · 메뉴를 여는 함수의 본문 — 삼성은 openMenu('M14949...') 로 여는데
    그 함수가 주소를 어떻게 만드는지 봐야 한다
  · data- 로 시작하는 속성 — 요즘 화면은 주소를 거기 숨겨 둔다

결과는 로그로 낸다. 커밋은 권한 403 으로 밀린 적이 있다.
"""
import json
import re
import traceback

from playwright.sync_api import sync_playwright

# 열리는 것이 확인된 화면만 넣는다.
PAGES = [
    ("신한 채권", "https://m.shinhansec.com/mweb/fnin/bond/fbond1002"),
    ("KB 채권메뉴", "https://m.kbsec.com/go.able?linkcd=m01010006"),
    ("삼성 메뉴", "https://www.samsungpop.com/published/main/index_mbw.html"),
    ("키움 메인", "https://www1.kiwoom.com/m/main"),
    ("한국투자 메인", "https://m.koreainvestment.com/mobile/index.jsp"),
    ("하나 메인", "https://www.hanaw.com/"),
    ("대신 메인", "https://m.daishin.com/"),
]
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

# 링크를 통째로 캔다. 글자에 '채권' 이 없어도 주소에 bond 가 있으면 후보다.
DIG = """() => {
  const out = [];
  document.querySelectorAll('*').forEach(e => {
    const t = (e.innerText||'').replace(/\\s+/g,' ').trim().slice(0,30);
    const href = e.getAttribute('href') || '';
    const onclick = e.getAttribute('onclick') || '';
    const data = Array.from(e.attributes || [])
      .filter(a => a.name.startsWith('data-'))
      .map(a => a.name + '=' + String(a.value).slice(0,60)).join(' ');
    const blob = href + ' ' + onclick + ' ' + data + ' ' + t;
    if (!/채권|bond|Bond|BOND/.test(blob)) return;
    if (t.length > 30) return;
    out.push({ t, href: href.slice(0,110), onclick: onclick.slice(0,140),
               data: data.slice(0,140) });
  });
  return out;
}"""

# 메뉴를 여는 함수가 주소를 어떻게 만드는지 본다.
FUNCS = """() => {
  const names = ['openMenu','goMenu','goPage','movePage','fnMove','linkPage',
                 'goLink','fnGoMenu','moveMenu','callMenu','openHp'];
  const out = {};
  names.forEach(n => {
    try { if (typeof window[n] === 'function')
      out[n] = window[n].toString().slice(0, 700); } catch (e) {}
  });
  return out;
}"""


def say(s=""):
    print(s, flush=True)


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(locale="ko-KR", user_agent=UA,
                         viewport={"width": 414, "height": 1000},
                         is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.set_default_timeout(6000)

    for name, url in PAGES:
        say("=" * 72)
        say(f"{name}  {url}")
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=20000)
            pg.wait_for_timeout(5000)
            say(f"  도착 {pg.url[:130]}")

            found = pg.evaluate(DIG)
            seen, uniq = set(), []
            for f in found:
                key = (f["t"], f["href"], f["onclick"], f["data"])
                if key in seen:
                    continue
                seen.add(key)
                uniq.append(f)
            say(f"  채권/bond 가 걸린 것 {len(uniq)}개")
            for f in uniq[:30]:
                bits = [f"'{f['t']}'"]
                if f["href"]:
                    bits.append(f"href={f['href']}")
                if f["onclick"]:
                    bits.append(f"onclick={f['onclick']}")
                if f["data"]:
                    bits.append(f"data={f['data']}")
                say("    · " + "  ".join(bits))

            fns = pg.evaluate(FUNCS)
            if fns:
                say(f"  메뉴 여는 함수 {list(fns)}")
                for n, src in fns.items():
                    say(f"    [{n}] {src}")
        except Exception:
            say("  !! 실패 " + traceback.format_exc().strip().split("\n")[-1][:160])

    br.close()

say("# 끝")
