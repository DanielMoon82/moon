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


def _first(node, *keys):
    for k in keys:
        if k in node and node[k] not in (None, ""):
            return node[k]
    return None


def from_polling(code):
    """네이버 실시간 폴링 JSON.

    응답에는 전일 종가 필드가 따로 없다. 대신 전일 대비 등락폭
    (compareToPreviousClosePrice)과 방향(compareToPreviousPrice.name = RISING /
    FALLING)이 오므로 현재가에서 되짚어 계산한다. 콤마가 없는 *Raw 필드를
    우선 쓴다. 고가·저가는 우리가 15분마다 찍은 표본이 아니라 장중 실제
    고저이므로 그대로 가져온다.
    """
    resp = requests.get(POLL_URL.format(code=code), headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()

    rows = payload.get("datas") or []
    row = next((r for r in rows if r.get("itemCode") == code), rows[0] if rows else None)
    if not row:
        raise ValueError("datas 가 비어 있음")

    value = _num(_first(row, "closePriceRaw", "closePrice"))
    if value is None:
        raise ValueError("closePrice 를 읽지 못함")

    diff = _num(_first(row, "compareToPreviousClosePriceRaw", "compareToPreviousClosePrice"))
    direction = (row.get("compareToPreviousPrice") or {}).get("name") or ""
    prev_close = None
    if diff is not None:
        signed = -abs(diff) if direction == "FALLING" else abs(diff)
        if direction not in ("RISING", "FALLING"):
            signed = 0.0 if abs(diff) < 1e-9 else signed
        prev_close = round(value - signed, 2)

    return {
        "value": value,
        "prev_close": prev_close,
        "change_pct": _num(_first(row, "fluctuationsRatioRaw", "fluctuationsRatio")),
        "open": _num(_first(row, "openPriceRaw", "openPrice")),
        "high": _num(_first(row, "highPriceRaw", "highPrice")),
        "low": _num(_first(row, "lowPriceRaw", "lowPrice")),
        "market_status": row.get("marketStatus"),
        "traded_at": row.get("localTradedAt"),
    }


def from_page(code):
    """지수 페이지 HTML. 폴링 API가 죽었을 때만 쓰는 최후 수단이라 현재가와
    전일 종가만 건진다. #now_value 는 오래 유지돼 온 마크업이다."""
    resp = requests.get(PAGE_URL, params={"code": code}, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    resp.encoding = "euc-kr"
    html = resp.text

    m = re.search(r'id="now_value"[^>]*>([^<]+)<', html)
    if not m:
        raise ValueError("#now_value 를 찾지 못함")
    value = _num(m.group(1))
    if value is None:
        raise ValueError("#now_value 를 숫자로 읽지 못함")

    prev_close = None
    m = re.search(r'id="change_value_and_rate"[^>]*>(.*?)</span>\s*</span>', html, re.S)
    if m:
        chunk = re.sub(r"<[^>]+>", " ", m.group(1))
        diff = _num(chunk)
        if diff is not None:
            falling = "하락" in chunk
            prev_close = round(value + abs(diff), 2) if falling else round(value - abs(diff), 2)

    return {"value": value, "prev_close": prev_close}


def fetch(code):
    """소스를 순서대로 시도하고, 성공한 소스를 로그에 남긴다."""
    errors = []
    for source in (from_polling, from_page):
        try:
            quote = source(code)
            print(
                f"  [ok] {code}: {quote['value']} (prev={quote.get('prev_close')}, "
                f"status={quote.get('market_status')}, traded_at={quote.get('traded_at')}) "
                f"via {source.__name__}"
            )
            return quote
        except Exception as exc:  # noqa: BLE001 - 소스별 실패는 다음 소스로 넘어간다
            errors.append(f"{source.__name__}: {exc}")
    print(f"  [fail] {code}: " + " | ".join(errors), file=sys.stderr)
    return None


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
        quote = fetch(meta["code"])
        if quote and quote.get("value") is not None and quote.get("prev_close") is not None:
            ok += 1
            print(
                f"        open={quote.get('open')} high={quote.get('high')} "
                f"low={quote.get('low')} pct={quote.get('change_pct')}"
            )
            continue
        # 값이 비면 응답 구조가 바뀐 것이다. 키 이름을 로그에서 확인할 수 있게 원문을 남긴다.
        try:
            raw = requests.get(
                POLL_URL.format(code=meta["code"]), headers=HEADERS, timeout=TIMEOUT
            ).text
            print(f"  [dump] {meta['code']} polling 원문 (앞 1200자): {raw[:1200]}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [dump] {meta['code']} 원문 조회 실패: {exc}")
    print(f"probe 결과: {ok}/{len(INDICES)} 성공")
    return 0 if ok == len(INDICES) else 1


def traded_date_and_time(quote, now_kst):
    """체결 시각(localTradedAt)이 오면 그걸 쓴다. 크론은 공휴일을 모르기 때문에,
    벽시계 대신 상류가 알려준 시각을 기준으로 삼아야 휴장일에 전일 종가를
    오늘 값으로 반복해서 쌓는 사고를 막을 수 있다."""
    raw = quote.get("traded_at")
    if raw:
        try:
            dt = datetime.fromisoformat(str(raw)).astimezone(KST)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
        except ValueError:
            pass
    return now_kst.strftime("%Y-%m-%d"), now_kst.strftime("%H:%M")


def main():
    if "--probe" in sys.argv:
        return probe()

    now_kst = datetime.now(KST)
    today = now_kst.strftime("%Y-%m-%d")
    minutes = now_kst.hour * 60 + now_kst.minute
    in_session = now_kst.weekday() < 5 and OPEN_MINUTES <= minutes <= CLOSE_MINUTES

    existing = load_existing()
    # 날짜가 바뀌면 새 하루로 시작한다. 전날 선이 오늘 선에 이어지면 안 된다.
    same_day = existing.get("trading_date") == today
    prev_points = {}
    prev_bases = {}
    if same_day:
        for idx in existing.get("indices", []):
            prev_points[idx.get("code")] = idx.get("points") or []
            prev_bases[idx.get("code")] = idx.get("prev_close")

    out_indices = []
    changed = 0
    market_open = False
    file_date = today

    for meta in INDICES:
        code = meta["code"]
        quote = fetch(code) or {}
        value = quote.get("value")
        points = list(prev_points.get(code, []))

        if value is not None:
            traded_date, stamp = traded_date_and_time(quote, now_kst)
            if traded_date == today and in_session:
                # 같은 분에 두 번 돌면 덮어쓴다(크론이 밀려 중복 실행될 수 있다).
                points = [p for p in points if p.get("t") != stamp]
                points.append({"t": stamp, "v": round(value, 2)})
                points.sort(key=lambda p: p["t"])
                changed += 1
                if str(quote.get("market_status") or "").upper() == "OPEN":
                    market_open = True
            elif not same_day:
                # 장이 닫혀 있거나 휴장일. 오늘 쌓인 선이 없으므로 마지막 거래일
                # 값을 그대로 싣는다. 선은 그리지 않고 숫자만 보여 준다.
                # (오늘 날짜로 어제 값을 붙이면 가짜 선이 된다.)
                file_date = traded_date
                changed += 1
                print(f"  [close] {code}: 장 마감 · {traded_date} 종가 {value}")

        base = quote.get("prev_close") or prev_bases.get(code)
        if not points and value is None:
            continue  # 쌓인 것도 없고 새로 받은 값도 없으면 싣지 않는다

        # 기준선은 하루 동안 고정한다. 새로 못 받으면 이미 저장된 값을 유지한다.
        latest = points[-1]["v"] if points else round(value, 2)
        entry = {
            "code": code,
            "name": meta["name"],
            "prev_close": round(base, 2) if base else None,
            "value": latest,
            "points": points,
        }
        if base:
            entry["change"] = round(latest - base, 2)
            entry["change_pct"] = (
                quote.get("change_pct")
                if quote.get("change_pct") is not None
                else round((latest - base) / base * 100, 2)
            )
        # 고가·저가는 상류의 장중 실제 고저를 쓴다. 15분 표본의 최대·최소는
        # 그 사이에 찍은 고점을 놓치므로 실제보다 좁게 나온다.
        sampled = [p["v"] for p in points] or [latest]
        entry["high"] = quote.get("high") or max(sampled)
        entry["low"] = quote.get("low") or min(sampled)
        if quote.get("open"):
            entry["open"] = quote["open"]
        out_indices.append(entry)

    if not changed:
        print("이번 실행에서 바뀐 값 없음 — 기존 파일 유지")
        return 0

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "trading_date": file_date,
                "market_open": market_open,
                "indices": out_indices,
            },
            ensure_ascii=False,
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    counts = ", ".join(f"{i['code']} {len(i['points'])}점" for i in out_indices)
    print(f"{OUT_JSON.relative_to(ROOT)} 기록 — {file_date} ({counts})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
