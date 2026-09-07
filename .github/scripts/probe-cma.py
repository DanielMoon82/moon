#!/usr/bin/env python3
"""임시 프로브: 증권사 CMA 페이지의 표 구조를 그대로 찍어 본다."""
import json, re, sys
from playwright.sync_api import sync_playwright

TARGETS = [
    ("KB증권", "https://www.kbsec.com/go.able?linkcd=m01030002"),
    ("신한투자증권", "https://www.shinhansec.com/siw/wealth-management/cma/info/view.do"),
    ("한국투자증권", "https://securities.koreainvestment.com/main/mall/opencma/CmaInfo.jsp?cmd=TF02bb010000"),
]
GRAB = """() => Array.from(document.querySelectorAll('table')).map(t =>
    Array.from(t.querySelectorAll('tr')).map(r =>
        Array.from(r.querySelectorAll('th,td')).map(c => (c.innerText||'').replace(/\\s+/g,' ').trim())
    ).filter(cs => cs.length))"""

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(locale="ko-KR", viewport={"width": 1400, "height": 1200},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
    pg = ctx.new_page()
    for name, url in TARGETS:
        print("=" * 70)
        print(name, url)
        try:
            pg.goto(url, wait_until="domcontentloaded", timeout=45000)
            try: pg.wait_for_load_state("networkidle", timeout=9000)
            except Exception: pass
            pg.wait_for_timeout(3000)
            body = pg.evaluate("() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
            print(f"-- 본문 {len(body)}자 / 금리표기 {re.findall(r'[0-9]+[.][0-9]{1,2} *%', body)[:20]}")
            print("-- 본문:", body[:2500])
            tabs = pg.evaluate(GRAB)
            print(f"-- 표 {len(tabs)}개")
            for i, t in enumerate(tabs[:8]):
                print(f"  [표{i}] {len(t)}행")
                for r in t[:12]:
                    print("    ", json.dumps(r, ensure_ascii=False)[:300])
            if name.startswith("신한"):
                iframes = pg.evaluate("() => Array.from(document.querySelectorAll('iframe')).map(f=>f.src)")
                print("-- iframe:", iframes)
                for fr in pg.frames[1:]:
                    try:
                        ft = fr.evaluate("() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
                        print(f"-- frame {fr.url[:100]} : {len(ft)}자 :: {ft[:1200]}")
                        ftabs = fr.evaluate(GRAB)
                        for i, t in enumerate(ftabs[:6]):
                            print(f"  [frame표{i}] {len(t)}행")
                            for r in t[:12]:
                                print("    ", json.dumps(r, ensure_ascii=False)[:300])
                    except Exception as e:
                        print("-- frame 실패", str(e)[:80])
        except Exception as e:
            print("!! 실패", str(e)[:200])
    br.close()
