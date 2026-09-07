#!/usr/bin/env python3
"""증권사별 CMA 금리를 모아 data/cma.json 에 쓴다.

왜 브라우저로 받는가
  증권사 홈페이지는 자바스크립트로 그려서 그냥 받으면 껍데기만 온다(확인함).
  그래서 Playwright 로 실제로 열어 표를 읽는다.

무엇을 비교하는가
  CMA 는 넣어 둔 돈을 무엇으로 굴리느냐에 따라 네 가지로 갈린다.
  RP형·발행어음형은 약정수익률이라 숫자가 확정이고, MMW형·MMF형은
  실적배당이라 확정 숫자가 없다. 비교는 같은 유형끼리 해야 뜻이 있으므로
  회사가 아니라 유형을 기준으로 묶는다.

표를 어떻게 읽는가
  회사마다 표가 다르다. 열 번호를 박으면 한 곳만 바뀌어도 엉뚱한 값을
  가져오므로 두 가지만 본다.
    · 금리 — '연 2.50%' 처럼 '연' 이 앞에 붙은 값. 안 붙었으면 머리글에
      '수익률(%)' 이라 적힌 열의 맨숫자. 보수율·수수료가 적힌 칸은 건너뛴다.
      (KB 의 MMW 줄 비고에 '보수율 : 개인 0.10%' 가 있어 이걸 금리로
       읽은 적이 있다.)
    · 상품 유형 — 줄 안에 RP/발행어음/MMW/MMF 가 있으면 그걸로, 없으면
      표 바로 앞 제목에서 찾는다. 한국투자는 줄에 '수익률 개인' 만 있고
      상품 이름이 표 제목에 있다.

한 곳이 실패해도 나머지는 갱신하고, 실패한 곳은 직전 값을 남긴다.
값이 달라졌을 때만 파일을 쓴다 — 자주 확인해도 커밋이 쌓이지 않게.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "cma.json"

# 주소는 여러 개 적어 둔다. 회사가 페이지를 옮기는 일이 잦아서, 먼저 열리는
# 쪽을 쓰고 다 안 되면 그 회사만 건너뛴다.
BROKERS = [
    {"id": "kb", "name": "KB증권", "urls": [
        "https://www.kbsec.com/go.able?linkcd=m01030002"]},
    {"id": "shinhan", "name": "신한투자증권", "urls": [
        "https://www.shinhansec.com/siw/wealth-management/cma/info/view.do"]},
    {"id": "koreainvest", "name": "한국투자증권", "urls": [
        "https://securities.koreainvestment.com/main/mall/opencma/CmaInfo.jsp?cmd=TF02bb010000"]},
    {"id": "mirae", "name": "미래에셋증권", "urls": [
        "https://securities.miraeasset.com/hks/hks4311/n02.do",
        "https://securities.miraeasset.com/hks/hks4113/n02.do"]},
    {"id": "samsung", "name": "삼성증권", "urls": [
        "https://www.samsungpop.com/mbw/finance/cma.do?cmd=guide",
        "https://www.samsungpop.com/ux/kor/finance/cma/cma/benefit.do"]},
    {"id": "nh", "name": "NH투자증권", "urls": [
        "https://www.nhqv.com/WMDoc.action?viewPage=/finance/cma/introCma.jsp",
        "https://m.nhsec.com/finance/cma/cma/cmaView?pdCd=CMA030"]},
]

TYPES = [
    {"key": "cp", "name": "발행어음형", "desc": "약정수익률 · 확정"},
    {"key": "rp", "name": "RP형", "desc": "약정수익률 · 확정"},
    {"key": "mmw", "name": "MMW형", "desc": "실적배당 · 확정 아님"},
    {"key": "mmf", "name": "MMF형", "desc": "실적배당 · 확정 아님"},
]
TYPE_NAME = {t["key"]: t["name"] for t in TYPES}
TYPE_PAT = re.compile(r"발행어음|MMW|MMF|RP")
TYPE_KEY = {"발행어음": "cp", "MMW": "mmw", "MMF": "mmf", "RP": "rp"}

YEAR_RATE = re.compile(r"연\s*(\d+(?:\.\d{1,2})?)\s*%")
PURE_RATE = re.compile(r"^(\d+\.\d{1,2})$")
TERM = re.compile(r"^\d{1,3}일$")           # '90일' 처럼 칸 하나가 통째로 기간인 것
FEE = re.compile(r"보수|수수료|한도|대출")   # 금리로 읽으면 안 되는 칸
AS_OF = re.compile(r"기준일[^\d]{0,8}(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
GENERIC_HEAD = re.compile(r"^(수익률|연수익률|금리|구분|대상|비고|가입대상|상품유형)")

GRAB = """() => Array.from(document.querySelectorAll('table')).map(t => {
    // 표 바로 앞에 놓인 글을 함께 가져온다. 상품 이름과 기준일이 표가 아니라
    // 그 앞 제목에 적혀 있는 회사가 있다.
    let ctx = '', n = t, hop = 0;
    while (n && ctx.length < 400 && hop < 10) {
      let p = n.previousElementSibling;
      while (p && ctx.length < 400) {
        const s = (p.innerText || '').replace(/\\s+/g, ' ').trim();
        if (s) ctx = s + ' ' + ctx;
        p = p.previousElementSibling;
      }
      n = n.parentElement; hop++;
    }
    const cap = t.querySelector('caption');
    if (cap) ctx += ' ' + (cap.innerText || '').replace(/\\s+/g, ' ').trim();
    return {
      ctx: ctx.trim().slice(-400),
      rows: Array.from(t.querySelectorAll('tr')).map(r =>
        Array.from(r.querySelectorAll('th,td')).map(c => (c.innerText || '').replace(/\\s+/g, ' ').trim())
      ).filter(cs => cs.length)
    };
  })"""


def classify(text):
    """가장 나중에 나온 상품 낱말을 쓴다 — 표에 가까운 쪽이 그 표 이야기다."""
    found = TYPE_PAT.findall(text or "")
    return TYPE_KEY[found[-1]] if found else None


def rate_col(header):
    """머리글에 '수익률(%)' 이라 적힌 열을 찾는다. 숫자만 든 표를 위해서다."""
    for i, c in enumerate(header):
        if ("수익률" in c or "금리" in c) and "%" in c:
            return i
    return -1


def read_row(cells, header, col):
    """(금리, 금리가 있던 열, 실적배당 여부)"""
    for i, c in enumerate(cells):
        if FEE.search(c):
            continue
        m = YEAR_RATE.search(c)
        if m:
            return float(m.group(1)), i, False
    if 0 <= col < len(cells) and len(cells) == len(header):
        m = PURE_RATE.match(cells[col])
        if m:
            return float(m.group(1)), col, False
    if any("실적배당" in c or "실적 배당" in c for c in cells):
        return None, -1, True
    return None, -1, False


def note_for(cells, header, idx, label):
    """비고를 고른다. 금리 열의 머리글이 '1일 ~ 30일' 처럼 조건을 담고 있으면
    그게 가장 쓸모 있고, 아니면 줄에서 설명처럼 보이는 칸을 쓴다."""
    if 0 <= idx < len(header) and len(cells) == len(header):
        h = header[idx]
        if h and not GENERIC_HEAD.match(h) and "%" not in h:
            return h[:34]
    for c in reversed(cells):
        if c and c != label and not YEAR_RATE.search(c) and not PURE_RATE.match(c) \
                and len(c) > 4 and "실적배당" not in c and not FEE.search(c):
            return c[:34]
    return ""


def parse(tables, body):
    """유형별 대표 금리 하나와, 유형에 안 맞는 특이 상품(약정식 RP 등)을 나눈다."""
    picked, extra, mmf_rates = {}, [], []
    for tb in tables:
        rows = tb["rows"]
        if not rows:
            continue
        header, ctx = rows[0], tb["ctx"]
        col = rate_col(header)
        ctx_type = classify(ctx)
        ctx_as_of = ""
        m = AS_OF.search(ctx)
        if m:
            ctx_as_of = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

        for cells in rows[1:]:
            flat = " ".join(cells)
            # 개인 기준으로 모은다. 법인만 적힌 줄은 건너뛴다.
            if "법인" in flat and "개인" not in flat:
                continue
            rate, idx, floating = read_row(cells, header, col)
            if rate is None and not floating:
                continue
            kind = classify(" ".join(c for c in cells if not YEAR_RATE.search(c))) or ctx_type
            if not kind:
                continue
            label = next((c for c in cells if TYPE_PAT.search(c)), "") or TYPE_NAME[kind]
            note = note_for(cells, header, idx, label)

            term = next((c for c in cells if TERM.match(c)), "")
            if term and rate is not None:
                # 기간을 약정하고 맡기는 상품이다. 수시입출금과 나란히 두면 안 된다.
                item = {"label": f"{label} {term}", "rate": rate,
                        "note": note, "as_of": ctx_as_of}
                if item not in extra:
                    extra.append(item)
                continue

            if kind == "mmf" and rate is not None:
                mmf_rates.append(rate)
                continue
            if kind in picked:
                continue
            picked[kind] = {"rate": rate, "text": None if rate is not None else "실적배당",
                            "note": note, "as_of": ctx_as_of}

    if mmf_rates and "mmf" not in picked:
        lo, hi = min(mmf_rates), max(mmf_rates)
        span = f"연 {lo:.2f}%" if lo == hi else f"연 {lo:.2f}~{hi:.2f}%"
        picked["mmf"] = {"rate": None, "text": "실적배당",
                         "note": f"최근 1주일 실적 {span}", "as_of": ""}

    page_as_of = ""
    m = AS_OF.search(body)
    if m:
        page_as_of = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    for v in picked.values():
        if not v["as_of"]:
            v["as_of"] = page_as_of
    return picked, extra[:3], page_as_of


def scrape(page, b):
    last = ""
    for url in b["urls"]:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=9000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            body = page.evaluate(
                "() => (document.body&&document.body.innerText||'').replace(/\\s+/g,' ')")
            picked, extra, as_of = parse(page.evaluate(GRAB), body)
            if picked:
                return {"name": b["name"], "url": url, "as_of": as_of,
                        "rates": picked, "extra": extra}
            last = f"{url} — 금리표 못 찾음(본문 {len(body)}자)"
        except Exception as exc:  # noqa: BLE001
            last = f"{url} — {str(exc)[:70]}"
        print(f"    · {last}")
    raise ValueError(last or "주소 없음")


def main():
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        old = {}
    old_b = {b["id"]: b for b in (old.get("brokers") or []) if isinstance(b, dict)}

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
                r = got[b["id"]]["rates"]
                shown = " · ".join(
                    f"{k} {v['rate']}%" if v["rate"] is not None else f"{k} 실적배당"
                    for k, v in r.items())
                print(f"  [ok] {b['name']}: {shown} (기준 {got[b['id']]['as_of'] or '표기 없음'})")
            except Exception as exc:  # noqa: BLE001
                print(f"  [fail] {b['name']}: {str(exc)[:120]}", file=sys.stderr)
                if old_b.get(b["id"]):
                    got[b["id"]] = {k: v for k, v in old_b[b["id"]].items() if k != "id"}
                    print(f"  [keep] {b['name']}: 직전 값 유지")
        browser.close()

    if not fresh:
        print("모두 실패 — 기존 파일 유지", file=sys.stderr)
        return 0

    brokers = [dict(id=b["id"], **got[b["id"]]) for b in BROKERS if b["id"] in got]
    body = {"types": TYPES, "brokers": brokers}
    if {k: old.get(k) for k in body} == body:
        print("금리 그대로 — 파일 두고 넘어간다")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"updated_at": datetime.now(timezone.utc).isoformat(), **body},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)} 기록 — {fresh}/{len(BROKERS)}곳")
    return 0


if __name__ == "__main__":
    sys.exit(main())
