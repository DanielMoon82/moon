#!/usr/bin/env python3
"""증권사가 파는 채권 목록을 모아 data/brokerbond.json 에 쓴다.

어떻게 찾았나
  증권사 채권 목록은 로그인해야 보는 줄 알았는데 틀렸다. NH투자증권
  모바일웹은 로그인 없이 그대로 보인다. 화면을 긁을 필요도 없다 —
  목록을 그리는 JSON 이 따로 있다.
    · /finance/bond/bond/inListData.json  장내채권 목록
    · /finance/bond/bond/commonTr.json    발행어음·RP 약정수익률

왜 그래도 브라우저를 쓰나
  저 JSON 을 부를 때 무슨 값을 딸려 보내는지 모른다. 화면을 열면 화면이
  알아서 제대로 부르므로, 열어 놓고 오가는 응답만 주워 담는다. 주소를
  직접 두드리다 규칙이 틀리면 조용히 빈 값이 오는데 그게 더 위험하다.

무엇을 담는가
  종목명·종류·신용등급·만기일·표면이율·체결수익률·현재가.
  체결수익률은 마지막으로 거래가 붙은 값이지 내가 살 때 받는 값이 아니다.
  그 말은 화면에 적는다.

값이 달라졌을 때만 파일을 쓴다.
"""
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data" / "brokerbond.json"

BROKER = "NH투자증권"
LIST_URL = "https://m.nhsec.com/finance/bond/bond/inList"
TABS = ["주식형 채권", "일반채권", "소액채권"]
UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 "
      "(KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1")

KEEP = 8          # 한 갈래에 여덟 줄이면 훑어보기 좋다
MAX_YIELD = 20.0  # 이보다 높으면 값이 잘못 들어온 것으로 본다


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f else None       # 0 은 값 없음이다


def ymd(v):
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", str(v or ""))
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else ""


def left(mature):
    """만기까지 남은 기간을 사람이 읽는 말로."""
    if not mature:
        return ""
    try:
        d = (date.fromisoformat(mature) - date.today()).days
    except ValueError:
        return ""
    if d < 0:
        return ""
    if d < 31:
        return f"{d}일"
    if d < 365:
        return f"{d // 30}개월"
    return f"{d // 365}년"


def rows_from(payload):
    content = ((payload or {}).get("resultList") or {}).get("content") or []
    out = []
    for c in content:
        y = num(c.get("bond_cntg_ert"))
        if y is None or y > MAX_YIELD:
            continue          # 거래가 없어 수익률이 안 잡힌 종목은 뺀다
        grade = (c.get("cfd_grd_cd") or "").strip()
        mature = ymd(c.get("rdmp_date"))
        out.append({
            "name": (c.get("bond_isnm") or "").strip()[:40],
            "kind": (c.get("bnd_tp_cd_nm") or "").strip(),
            "grade": "" if grade in ("", "_") else grade,
            "mature": mature,
            "left": left(mature),
            "coupon": num(c.get("srfc_mnrt")),
            "yield": y,
            "price": num(c.get("bond_prpr")),
        })
    return out


def main():
    got, seen_urls = {}, []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(locale="ko-KR", user_agent=UA,
                                  viewport={"width": 414, "height": 1400},
                                  is_mobile=True, has_touch=True)
        page = ctx.new_page()
        bucket = []

        def on_response(resp):
            if "inListData.json" not in resp.url:
                return
            try:
                bucket.append(resp.json())
            except Exception:  # noqa: BLE001
                pass

        page.on("response", on_response)
        try:
            page.goto(LIST_URL, wait_until="domcontentloaded", timeout=40000)
            page.wait_for_timeout(7000)
            for tab in TABS:
                bucket.clear()
                if tab != TABS[0]:
                    try:
                        # 탭은 눌러야 그 갈래를 새로 받아 온다.
                        page.get_by_text(tab, exact=True).first.evaluate("e => e.click()")
                    except Exception as exc:  # noqa: BLE001
                        print(f"  [건너뜀] {tab}: {str(exc)[:70]}", file=sys.stderr)
                        continue
                page.wait_for_timeout(6000)
                rows = []
                for payload in bucket:
                    rows.extend(rows_from(payload))
                if not rows:
                    print(f"  [빈손] {tab}", file=sys.stderr)
                    continue
                rows.sort(key=lambda r: r["yield"], reverse=True)
                uniq, names = [], set()
                for r in rows:
                    if r["name"] in names:
                        continue
                    names.add(r["name"])
                    uniq.append(r)
                got[tab] = uniq[:KEEP]
                seen_urls.append(page.url)
                print(f"  [ok] {tab}: {len(uniq)}종목 중 {len(got[tab])}줄 "
                      f"— 최고 {got[tab][0]['yield']}%")
        finally:
            browser.close()

    if not got:
        print("한 갈래도 못 받았다 — 기존 파일 유지", file=sys.stderr)
        return 0

    payload = {
        "broker": BROKER,
        "url": LIST_URL,
        "note": "장내채권 체결수익률",
        "groups": [{"kind": k, "rows": v} for k, v in got.items()],
    }
    try:
        old = json.loads(OUT.read_text(encoding="utf-8"))
        same = {k: old.get(k) for k in payload} == payload
    except (OSError, ValueError):
        same = False
    if same:
        print("목록 그대로 — 파일 두고 넘어간다")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"updated_at": datetime.now(timezone.utc).isoformat(), **payload},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(len(g["rows"]) for g in payload["groups"])
    print(f"{OUT.relative_to(ROOT)} 기록 — {len(payload['groups'])}갈래 {n}줄")
    return 0


if __name__ == "__main__":
    sys.exit(main())
