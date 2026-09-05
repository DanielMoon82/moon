#!/usr/bin/env python3
"""Append the current KOSPI/KOSDAQ index level to data/index-intraday.json so the
site can draw a 장중 (intraday) line for each index.

There is no public endpoint that hands back a full intraday minute series we can
rely on, so this builds the series itself: the workflow runs every 15 minutes
during KRX hours and each run appends one point. A missed run just leaves a gap
in the line; it never corrupts what is already stored.

Sources are tried in order, most structured first:
  1. Naver's realtime polling JSON (what finance.naver.com's own ticker uses)
  2. Naver's index page HTML (#now_value), which has been stable for years
KRX's official API is not used here — .github/scripts/fetch-stock-data.py
documents that it is blocked outright for GitHub Actions' IP ranges.

Like the sibling stock fetcher, any failure leaves the last known-good file in
place and exits 0, so the site never shows a broken chart because of a flaky
upstream. Every attempt is logged so a silent breakage is visible in the run log.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_JSON = ROOT / "data" / "index-intraday.json"

KST = timezone(timedelta(hours=9))

INDICES = [
    {"code": "KOSPI", "name": "코스피"},
    {"code": "KOSDAQ", "name": "코스닥"},
]

# 09:00 개장 ~ 15:30 종가. 종가가 확정으로 반영될 여유를 두고 15:45까지 받는다.
OPEN_MINUTES = 9 * 60
CLOSE_MINUTES = 15 * 60 + 45

POLL_URL = "https://polling.finance.naver.com/api/realtime/domestic/index/{code}"
PAGE_URL = "https://finance.naver.com/sise/sise_index.naver"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; moon-index-bot/1.0)",
    "Referer": "https://finance.naver.com/",
}
TIMEOUT = 10


def _num(text):
    """'3,245.67' -> 3245.67. 콤마와 부호 문자를 걷어낸 뒤 숫자만 남긴다."""
    if text is None:
        return None
    m = re.search(r"-?[\d,]+(?:\.\d+)?", str(text).replace("\xa0", " "))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _walk(obj):
    """중첩 JSON을 훑어 dict를 모두 내놓는다. 네이버 응답 구조가 바뀌어도
    키 이름만 맞으면 값을 건질 수 있게 위치가 아니라 키로 찾기 위한 것."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def from_polling(code):
    """네이버 실시간 폴링 JSON. 키 이름으로만 값을 찾는다."""
    resp = requests.get(POLL_URL.format(code=code), headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()

    now = prev = None
    for node in _walk(payload):
        if now is None:
            for key in ("closePrice", "nv", "currentValue", "now", "tradePrice"):
                if key in node:
                    now = _num(node[key])
                    break
        if prev is None:
            for key in ("previousClose", "pcv", "prevClose", "baseValue"):
                if key in node:
                    prev = _num(node[key])
                    break
        if now is not None and prev is not None:
            break

    if now is None:
        raise ValueError("polling 응답에서 현재가를 찾지 못함")
    return now, prev


def from_page(code):
    """지수 페이지 HTML. #now_value는 오래 유지돼 온 마크업이라 최후 수단으로 둔다."""
    resp = requests.get(
        PAGE_URL, params={"code": code}, headers=HEADERS, timeout=TIMEOUT
    )
    resp.raise_for_status()
    resp.encoding = "euc-kr"
    html = resp.text

    m = re.search(r'id="now_value"[^>]*>([^<]+)<', html)
    if not m:
        raise ValueError("#now_value 를 찾지 못함")
    now = _num(m.group(1))
    if now is None:
        raise ValueError("#now_value 를 숫자로 읽지 못함")

    prev = None
    m = re.search(r'id="change_value_and_rate"[^>]*>(.*?)</span>\s*</span>', html, re.S)
    if m:
        chunk = re.sub(r"<[^>]+>", " ", m.group(1))
        diff = _num(chunk)
        if diff is not None:
            # 하락이면 페이지가 '하락'/'down' 표기를 함께 싣는다.
            falling = ("하락" in chunk) or ("down" in html[m.start() - 400 : m.start()])
            prev = round(now + diff, 2) if falling else round(now - diff, 2)
    return now, prev


def fetch(code):
    """소스를 순서대로 시도하고, 성공한 소스를 로그에 남긴다."""
    errors = []
    for source in (from_polling, from_page):
        try:
            now, prev = source(code)
            print(f"  [ok] {code}: {now} (prev={prev}) via {source.__name__}")
            return now, prev
        except Exception as exc:  # noqa: BLE001 - 소스별 실패는 다음 소스로 넘어간다
            errors.append(f"{source.__name__}: {exc}")
    print(f"  [fail] {code}: " + " | ".join(errors), file=sys.stderr)
    return None, None


def load_existing():
    try:
        return json.loads(OUT_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def probe():
    """소스가 살아 있는지만 확인한다. 장 시간·요일과 무관하게 돌고 아무것도 쓰지
    않는다. 상류를 직접 호출해 볼 수 없는 환경에서 워크플로를 수동 실행해
    로그로 확인하기 위한 것."""
    print("probe: 장 시간/요일 검사 없이 소스만 확인합니다 (파일은 쓰지 않음)")
    ok = 0
    for meta in INDICES:
        value, prev = fetch(meta["code"])
        if value is not None:
            ok += 1
        if prev is None:
            # 전일 종가 키를 못 찾았을 때만 원문을 찍는다. 응답 구조를 직접
            # 확인할 수 없는 환경에서 키 이름을 알아내기 위한 것.
            try:
                raw = requests.get(
                    POLL_URL.format(code=meta["code"]), headers=HEADERS, timeout=TIMEOUT
                ).text
                print(f"  [dump] {meta['code']} polling 원문 (앞 1200자): {raw[:1200]}")
            except Exception as exc:  # noqa: BLE001
                print(f"  [dump] {meta['code']} 원문 조회 실패: {exc}")
    print(f"probe 결과: {ok}/{len(INDICES)} 성공")
    return 0 if ok == len(INDICES) else 1


def main():
    if "--probe" in sys.argv:
        return probe()

    now_kst = datetime.now(KST)
    today = now_kst.strftime("%Y-%m-%d")
    minutes = now_kst.hour * 60 + now_kst.minute

    if now_kst.weekday() >= 5:
        print(f"주말({today}) — 건너뜀")
        return 0
    if not (OPEN_MINUTES <= minutes <= CLOSE_MINUTES):
        print(f"장 시간 밖({now_kst:%H:%M} KST) — 건너뜀")
        return 0

    existing = load_existing()
    # 날짜가 바뀌면 새 하루로 시작한다. 전날 선이 오늘 선에 이어지면 안 된다.
    same_day = existing.get("trading_date") == today
    prev_points = {}
    prev_bases = {}
    if same_day:
        for idx in existing.get("indices", []):
            prev_points[idx.get("code")] = idx.get("points") or []
            prev_bases[idx.get("code")] = idx.get("prev_close")

    stamp = now_kst.strftime("%H:%M")
    out_indices = []
    got_any = False

    for meta in INDICES:
        code = meta["code"]
        value, prev_close = fetch(code)
        points = list(prev_points.get(code, []))

        if value is not None:
            got_any = True
            # 같은 분에 두 번 돌면 덮어쓴다(크론이 밀려 중복 실행될 수 있다).
            points = [p for p in points if p.get("t") != stamp]
            points.append({"t": stamp, "v": round(value, 2)})
            points.sort(key=lambda p: p["t"])
        elif not points:
            continue  # 값도 없고 쌓인 것도 없으면 이 지수는 아예 싣지 않는다

        # 기준선은 하루 동안 고정한다. 새로 못 받으면 이미 저장된 값을 유지한다.
        base = prev_close if prev_close else prev_bases.get(code)
        latest = points[-1]["v"] if points else None
        entry = {
            "code": code,
            "name": meta["name"],
            "prev_close": round(base, 2) if base else None,
            "value": latest,
            "points": points,
        }
        if latest is not None and base:
            entry["change"] = round(latest - base, 2)
            entry["change_pct"] = round((latest - base) / base * 100, 2)
        if points:
            values = [p["v"] for p in points]
            entry["high"] = max(values)
            entry["low"] = min(values)
        out_indices.append(entry)

    if not got_any:
        print("모든 소스 실패 — 기존 파일 유지", file=sys.stderr)
        return 0

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "trading_date": today,
                "market_open": minutes <= 15 * 60 + 30,
                "indices": out_indices,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    counts = ", ".join(f"{i['code']} {len(i['points'])}점" for i in out_indices)
    print(f"{OUT_JSON.relative_to(ROOT)} 기록 — {today} {stamp} ({counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
