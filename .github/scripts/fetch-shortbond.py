#!/usr/bin/env python3
"""단기금융증권 만기수익률을 모아 data/shortbond.json 에 쓴다.

무엇인가
  CD·CP·전자단기사채를 신용등급과 남은 만기별로 나눠 놓은 수익률표다.
  한국예탁결제원 세이브로가 KIS채권평가 자료로 매일 낸다.

왜 이걸 싣는가
  증권사가 파는 장외채권 매물 목록은 여덟 곳 모두 로그인해야 보인다(확인함).
  회사별 매물은 자동으로 가져올 방법이 없다. 대신 시장 전체 금리를 싣는다.
  '지금 단기물 금리가 등급별로 얼마인지' 는 이걸로 알 수 있다.

왜 브라우저로 받는가
  세이브로는 화면 뼈대만 먼저 오고 표는 나중에 자바스크립트로 그린다.
  그냥 받으면 머리글만 있고 줄이 하나도 없다(확인함). 그래서 표에 줄이
  생길 때까지 기다린다.

값이 달라졌을 때만 파일을 쓴다.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "shortbond.json"

PAGE = ("https://seibro.or.kr/websquare/control.jsp?w2xPath=/IPORTAL/user/moneyMarke/"
        "BIP_CNTS04016V.xml&menuNo=494")
# 곧바로 열리지 않을 때를 대비해, 단기금융시장 첫 화면에서 메뉴를 눌러 들어간다.
HOME = ("https://seibro.or.kr/websquare/control.jsp?w2xPath=%2FIPORTAL%2Fuser%2F"
        "moneyMarke%2FBIP_CNTS04030V.xml&menuNo=940")
MENU = "단기금융증권만기수익률"

GRAB = """() => Array.from(document.querySelectorAll('table')).map(t =>
    Array.from(t.querySelectorAll('tr')).map(r =>
      Array.from(r.querySelectorAll('th,td')).map(c => (c.innerText||'').replace(/\\s+/g,' ').trim())
    ).filter(cs => cs.some(x => x)))"""

TERM = re.compile(r"^\d{1,2}(일|월|년)$")
NUM = re.compile(r"^\d+(\.\d+)?$")


def pick_table(tables):
    """만기 머리글이 붙고 줄이 여럿인 표를 고른다. 세이브로 화면에는 메뉴를
    담은 표가 여럿 섞여 있어 모양으로 골라야 한다."""
    for rows in tables:
        if len(rows) < 3:
            continue
        head = rows[0]
        terms = [c for c in head if TERM.match(c)]
        if len(terms) >= 5:
            return rows
    return None


def parse(rows):
    head = rows[0]
    # 머리글 앞쪽 빈 칸은 종류·등급 자리다. 만기가 시작되는 데를 찾는다.
    start = next(i for i, c in enumerate(head) if TERM.match(c))
    terms = head[start:]

    groups, kind = [], ""
    for cells in rows[1:]:
        vals = [c for c in cells if NUM.match(c)]
        if len(vals) < len(terms) - 2:
            continue
        labels = [c for c in cells if c and not NUM.match(c)]
        # 종류(CD·CP·전단채)는 세로로 합쳐 있어 첫 줄에만 적힌다. 빈 줄은
        # 바로 윗줄의 종류를 잇는다.
        if len(labels) >= 2:
            kind, grade = labels[0], labels[1]
        elif labels:
            grade = labels[0]
        else:
            continue
        if not kind:
            continue
        if not groups or groups[-1]["kind"] != kind:
            groups.append({"kind": kind, "rows": []})
        groups[-1]["rows"].append({"grade": grade, "rates": [float(v) for v in vals]})

    # 값이 전부 0 인 열은 자료가 없다는 뜻이다. 0% 로 보이면 안 되니 뺀다.
    keep = [i for i in range(len(terms))
            if any(i < len(r["rates"]) and r["rates"][i] != 0
                   for g in groups for r in g["rows"])]
    terms = [terms[i] for i in keep]
    for g in groups:
        for r in g["rows"]:
            r["rates"] = [r["rates"][i] if i < len(r["rates"]) else None for i in keep]
    return terms, groups


def scrape(page):
    for url in (PAGE, None):
        if url:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        else:
            page.goto(HOME, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(5000)
            # 메뉴는 접혀 있어 눈에 안 보인다. 요소에 직접 클릭을 건다.
            page.get_by_text(MENU, exact=True).first.evaluate("el => el.click()")
        # 표에 줄이 채워질 때까지 기다린다. 뼈대만 먼저 오기 때문이다.
        try:
            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('table')).some(t =>"
                " t.querySelectorAll('tr').length > 5)", timeout=30000)
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(5000)
        rows = pick_table([t for t in page.evaluate(GRAB) if t])
        if rows:
            body = page.evaluate(
                "() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
            return rows, body, page.url
        print(f"  · {'곧바로 열기' if url else '메뉴 눌러 들어가기'} — 표를 못 찾음")
    raise ValueError("수익률표를 못 찾음")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            locale="ko-KR",
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
            viewport={"width": 1500, "height": 1200})
        page = ctx.new_page()
        try:
            rows, body, url = scrape(page)
        except Exception as exc:  # noqa: BLE001
            print(f"실패 — 기존 파일 유지: {str(exc)[:120]}", file=sys.stderr)
            return 0
        finally:
            browser.close()

    terms, groups = parse(rows)
    if not groups:
        print("표는 찾았는데 읽을 줄이 없다 — 기존 파일 유지", file=sys.stderr)
        return 0

    as_of = ""
    m = re.search(r"기준일[^\d]{0,8}(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", body)
    if m:
        as_of = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    payload = {"as_of": as_of, "source": "한국예탁결제원 세이브로 · KIS채권평가",
               "url": url, "terms": terms, "groups": groups}
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
        same = {k: old.get(k) for k in payload} == payload
    except (OSError, ValueError):
        same = False
    if same:
        print("금리 그대로 — 파일 두고 넘어간다")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"updated_at": datetime.now(timezone.utc).isoformat(), **payload},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(len(g["rows"]) for g in groups)
    print(f"{OUT.relative_to(ROOT)} 기록 — {as_of or '기준일 표기 없음'}, "
          f"{len(groups)}종류 {n}줄, 만기 {len(terms)}개")
    for g in groups:
        print(f"  {g['kind']}: " + ", ".join(r["grade"] for r in g["rows"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
