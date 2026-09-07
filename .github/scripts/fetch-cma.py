#!/usr/bin/env python3
"""증권사별 CMA 금리를 모아 data/cma.json 에 쓴다.

왜 브라우저로 받는가
  증권사 홈페이지는 자바스크립트로 그려서 그냥 받으면 껍데기만 온다(확인함).
  그래서 Playwright 로 실제로 열어 표를 읽는다.

무엇을 담는가
  CMA 계좌에 넣어 둔 돈에 붙는 약정 수익률이다. RP형·발행어음형은 확정,
  MMF·MMW형은 실적배당이라 숫자가 없을 수 있고 그때는 '실적배당'으로 둔다.

한 곳이 실패해도 나머지는 갱신하고, 실패한 곳은 직전 값을 남긴다.
값이 달라졌을 때만 파일을 쓴다 — 자주 확인해도 커밋이 쌓이지 않게.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "cma.json"
KST = timezone(timedelta(hours=9))

# 프로브로 실제 표가 보이는 걸 확인한 곳만 넣는다. 늘릴 땐 여기에 한 줄.
BROKERS = [
    {"id": "kb", "name": "KB증권",
     "url": "https://www.kbsec.com/go.able?linkcd=m01030002"},
    {"id": "shinhan", "name": "신한투자증권",
     "url": "https://www.shinhansec.com/siw/wealth-management/cma/info/view.do"},
    {"id": "koreainvest", "name": "한국투자증권",
     "url": "https://securities.koreainvestment.com/main/mall/opencma/CmaInfo.jsp?cmd=TF02bb010000"},
]

RATE = re.compile(r"(\d+\.\d{1,2})\s*%")
# 표에서 이런 낱말이 있는 칸을 상품 이름으로 본다.
KIND = re.compile(r"RP|발행어음|MMF|MMW|CMA|예수금|수시|약정")

GRAB_TABLES = """() => Array.from(document.querySelectorAll('table')).map(t =>
    Array.from(t.querySelectorAll('tr')).map(r =>
        Array.from(r.querySelectorAll('th,td')).map(c => (c.innerText||'').replace(/\\s+/g,' ').trim())
    ).filter(cells => cells.length)
)"""


def rows_from(tables):
    """표에서 (상품, 금리, 메모)를 뽑는다. 회사마다 열 구성이 달라
    열 번호를 박지 않고, 금리가 든 칸과 이름이 든 칸을 찾아 짝짓는다."""
    out = []
    for rows in tables:
        for cells in rows:
            rate = None
            for c in cells:
                m = RATE.search(c)
                if m:
                    rate = float(m.group(1))
                    break
            names = [c for c in cells if KIND.search(c) and not RATE.search(c)]
            if rate is None or not names:
                continue
            label = names[0][:40]
            # 개인/법인처럼 구분이 따로 있으면 이름에 붙인다.
            for c in cells:
                if c.strip() in ("개인", "법인") and c.strip() not in label:
                    label = f"{label} ({c.strip()})"
                    break
            note = ""
            for c in cells:
                if c and c != label and not RATE.search(c) and len(c) > 6:
                    note = c[:60]
                    break
            out.append({"label": label, "rate": rate, "note": note})
    # 같은 상품이 여러 표에 겹쳐 나온다. 처음 것만 남긴다.
    seen, uniq = set(), []
    for r in out:
        key = (r["label"], r["rate"])
        if key not in seen:
            seen.add(key)
            uniq.append(r)
    return uniq[:6]


def scrape(page, b):
    page.goto(b["url"], wait_until="domcontentloaded", timeout=45000)
    try:
        page.wait_for_load_state("networkidle", timeout=9000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(2500)

    body = page.evaluate("() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
    tables = page.evaluate(GRAB_TABLES)
    items = rows_from(tables)
    if not items:
        raise ValueError(f"금리가 든 표를 못 찾음 (본문 {len(body)}자)")

    as_of = ""
    m = re.search(r"기준일[^\d]{0,6}(\d{4})[.\-](\d{1,2})[.\-](\d{1,2})", body)
    if m:
        as_of = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return {"name": b["name"], "url": b["url"], "as_of": as_of, "items": items}


def main():
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    old_b = old.get("brokers") or {}

    got, fresh = {}, 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            locale="ko-KR",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
            viewport={"width": 1400, "height": 1000})
        page = ctx.new_page()
        for b in BROKERS:
            try:
                got[b["id"]] = scrape(page, b)
                fresh += 1
                one = got[b["id"]]["items"][0]
                print(f"  [ok] {b['name']}: {len(got[b['id']]['items'])}개 "
                      f"— {one['label']} {one['rate']}% (기준 {got[b['id']]['as_of'] or '표기 없음'})")
            except Exception as exc:  # noqa: BLE001
                print(f"  [fail] {b['name']}: {str(exc)[:90]}", file=sys.stderr)
                if old_b.get(b["id"]):
                    got[b["id"]] = old_b[b["id"]]
                    print(f"  [keep] {b['name']}: 직전 값 유지")
        browser.close()

    if not fresh:
        print("모두 실패 — 기존 파일 유지", file=sys.stderr)
        return 0

    body = {"brokers": got}
    same = {k: old.get(k) for k in body} == body
    if same:
        print("금리 그대로 — 파일 두고 넘어간다")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"updated_at": datetime.now(timezone.utc).isoformat(), **body},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(len(v["items"]) for v in got.values())
    print(f"{OUT.relative_to(ROOT)} 기록 — {fresh}/{len(BROKERS)}곳, 항목 {n}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
