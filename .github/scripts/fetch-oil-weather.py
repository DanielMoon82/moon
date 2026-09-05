#!/usr/bin/env python3
"""Fetch oil prices and a weather snapshot into data/oil.json and data/weather.json.

Why this exists: the page used to pull Stooq straight from the browser. Stooq
sends no CORS header, so it had to go through public relay services
(allorigins / corsproxy). Those rate-limit and go down, and when they do the
유가 card shows nothing — the one thing a reader most expects to be there.
Fetching it here instead removes that dependency entirely: the page reads a
file from its own origin, which cannot be blocked by CORS and needs no relay.

Weather (Open-Meteo) does send CORS headers and works from the browser, but a
snapshot of the default city is stored too so the card has something to show
the instant the page opens, before any network call finishes.

Run by .github/workflows/fetch-oil-weather.yml. Any failure leaves the last
known-good file in place and exits 0 — a stale price beats an empty card.
"""
import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
OIL_JSON = ROOT / "data" / "oil.json"
WEATHER_JSON = ROOT / "data" / "weather.json"

# 페이지의 기간 버튼이 최대 1년이라 그만큼만 담는다.
KEEP_DAYS = 400

SYMBOLS = [
    ("wti", "cl.f", "WTI", "USD/배럴"),
    ("brent", "cb.f", "브렌트", "USD/배럴"),
]
FX_SYMBOL = "usdkrw"

STOOQ_CSV = "https://stooq.com/q/d/l/?s={sym}&i=d"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; moon-oil-bot/1.0)"}
TIMEOUT = 20

# 히어로 사진과 무관하게, 이 사이트가 기본으로 보여주는 도시.
DEFAULT_CITY = {"label": "인천공항", "lat": 37.4602, "lon": 126.4407, "tz": "Asia/Seoul"}
FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"
    "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
    "&timezone={tz}&forecast_days=5"
)


def fetch_series(symbol):
    """Stooq 일봉 CSV -> [{d, c}]. 헤더 이름으로 열을 찾아 순서가 바뀌어도 견딘다."""
    resp = requests.get(STOOQ_CSV.format(sym=symbol), headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    text = resp.text.strip()
    if not text or text.lower().startswith("no data"):
        raise ValueError(f"빈 응답: {text[:60]!r}")

    lines = text.splitlines()
    head = [h.strip().lower() for h in lines[0].split(",")]
    try:
        di, ci = head.index("date"), head.index("close")
    except ValueError as exc:
        raise ValueError(f"열 이름을 찾지 못함: {head}") from exc

    points = []
    for line in lines[1:]:
        cols = line.split(",")
        if len(cols) <= max(di, ci):
            continue
        try:
            close = float(cols[ci])
        except ValueError:
            continue  # 거래 없는 날은 'N/D' 로 온다
        points.append({"d": cols[di], "c": round(close, 2)})

    if not points:
        raise ValueError("쓸 수 있는 행이 없음")
    return points[-KEEP_DAYS:]


def load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def do_oil():
    series, failures = {}, []
    for key, sym, name, unit in SYMBOLS:
        try:
            pts = fetch_series(sym)
            series[key] = {"name": name, "unit": unit, "points": pts}
            print(f"  [ok] {name}: {len(pts)}일, 최근 {pts[-1]['d']} {pts[-1]['c']}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {exc}")

    fx = None
    try:
        fx_pts = fetch_series(FX_SYMBOL)
        fx = fx_pts[-1]["c"]
        print(f"  [ok] USD/KRW: {fx}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"USD/KRW: {exc}")

    if failures:
        print("  [warn] " + " | ".join(failures), file=sys.stderr)

    if not series:
        print("유가: 전부 실패 — 기존 파일 유지", file=sys.stderr)
        return False

    # 한 종목만 실패했다면 직전 파일의 값을 살려 카드가 비지 않게 한다.
    old = load(OIL_JSON) or {}
    for key in ("wti", "brent"):
        if key not in series and (old.get("series") or {}).get(key):
            series[key] = old["series"][key]
            print(f"  [keep] {key}: 이번엔 못 받아 직전 값을 유지")
    if fx is None:
        fx = old.get("usdkrw")

    write(OIL_JSON, {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "series": series,
        "usdkrw": fx,
    })
    print(f"{OIL_JSON.relative_to(ROOT)} 기록")
    return True


def do_weather():
    c = DEFAULT_CITY
    try:
        resp = requests.get(
            FORECAST_URL.format(lat=c["lat"], lon=c["lon"], tz=c["tz"]),
            headers=HEADERS, timeout=TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        if "current" not in payload:
            raise ValueError("current 없음")
    except Exception as exc:  # noqa: BLE001
        print(f"날씨: 실패({exc}) — 기존 파일 유지", file=sys.stderr)
        return False

    write(WEATHER_JSON, {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "label": c["label"],
        "latitude": c["lat"],
        "longitude": c["lon"],
        "current": payload.get("current"),
        "daily": payload.get("daily"),
    })
    cur = payload["current"]
    print(f"{WEATHER_JSON.relative_to(ROOT)} 기록 — {c['label']} {cur.get('temperature_2m')}°")
    return True


def main():
    print("유가")
    oil_ok = do_oil()
    print("날씨")
    weather_ok = do_weather()
    if not oil_ok and not weather_ok:
        print("둘 다 실패했지만 기존 파일은 그대로다.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
