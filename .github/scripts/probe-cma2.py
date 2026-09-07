#!/usr/bin/env python3
"""임시 프로브: 아직 확인 못 한 증권사 CMA 페이지 표를 그대로 찍어 본다."""
import json
from playwright.sync_api import sync_playwright

TARGETS = [
    ("삼성증권-guide", "https://www.samsungpop.com/mbw/finance/cma.do?cmd=guide"),
    ("삼성증권-benefit", "https://www.samsungpop.com/ux/kor/finance/cma/cma/benefit.do"),
    ("NH-m", "https://m.nhsec.com/finance/cma/cma/cmaView?pdCd=CMA030"),
    ("미래에셋-4113", "https://securities.miraeasset.com/hks/hks4113/n02.do"),
    ("미래에셋-공시", "https://securities.miraeasset.com/mw/mks/mks4113/n02.do"),
]
GRAB = """() => Array.from(document.querySelectorAll('table')).map(t => {
    let ctx = '', n = t, hop = 0;
    while (n && ctx.length < 400 && hop < 10) {
      let p = n.previousElementSibling;
      while (p && ctx.length < 400) {
        const s = (p.innerText || '').replace(/\\s+/g,' ').trim();
        if (s) ctx = s + ' ' + ctx;
        p = p.previousElementSibling;
      }
      n = n.parentElement; hop++;
    }
    return {ctx: ctx.trim().slice(-300),
      rows: Array.from(t.querySelectorAll('tr')).map(r =>
        Array.from(r.querySelectorAll('th,td')).map(c => (c.innerText||'').replace(/\\s+/g,' ').trim())
      ).filter(cs => cs.length)};
  })"""

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
            print(f"-- 본문 {len(body)}자")
            print("-- 본문:", body[:1800])
            for i, t in enumerate(pg.evaluate(GRAB)[:10]):
                if not t["rows"]:
                    continue
                print(f"  [표{i}] ctx={t['ctx'][-140:]}")
                for r in t["rows"][:10]:
                    print("    ", json.dumps(r, ensure_ascii=False)[:280])
        except Exception as e:
            print("!! 실패", str(e)[:160])
    br.close()
