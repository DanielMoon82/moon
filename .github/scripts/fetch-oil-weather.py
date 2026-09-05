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

# 소스 우선순위: FRED -> Yahoo.
# Stooq 는 쓰지 않는다. GitHub Actions IP 로 부르면 시세 CSV 대신
# "this site requires javascript to verify your browser" 봇 검사 페이지를
# 돌려준다(실행 로그로 확인). 브라우저에서 중계를 거쳐 받던 이유가 이것이고,
# 그래서 서버에서는 봇 검사가 없는 소스로 바꿨다.
#   FRED  : 미국 세인트루이스 연준 공개 CSV. 키가 필요 없고 차단하지 않는다.
#   Yahoo : FRED 가 쉬는 날(공표 지연)을 메우는 예비 소스.
SERIES = [
    {"key": "wti", "name": "WTI", "unit": "USD/배럴",
     "fred": "DCOILWTICO", "yahoo": "CL=F"},
    {"key": "brent", "name": "브렌트", "unit": "USD/배럴",
     "fred": "DCOILBRENTEU", "yahoo": "BZ=F"},
]
FX = {"key": "usdkrw", "name": "USD/KRW", "fred": "DEXKOUS", "yahoo": "KRW=X"}

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={start}"
YAHOO_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
               "?range=2y&interval=1d")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; moon-oil-bot/1.0)",
    "Accept": "text/csv,application/json;q=0.9,*/*;q=0.8",
}
TIMEOUT = 20

# 사이트가 기본으로 보여 주는 도시.
DEFAULT_CITY = {"label": "인천공항", "lat": 37.4602, "lon": 126.4407, "tz": "Asia/Seoul"}
FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast"
    "?latitude={lat}&longitude={lon}"
    "&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m"
    "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
    "&timezone={tz}&forecast_days=5"
)


def from_fred(sid):
    """FRED 공개 CSV. 결측치는 '.' 로 온다. 헤더 이름이 예전엔 DATE,
    지금은 observation_date 라 둘 다 받는다."""
    start = (datetime.now(timezone.utc) - timedelta(days=KEEP_DAYS + 30)).strftime("%Y-%m-%d")
    resp = requests.get(FRED_CSV.format(sid=sid, start=start), headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    lines = resp.text.strip().splitlines()
    if len(lines) < 2:
        raise ValueError(f"행이 없음: {resp.text[:80]!r}")
    head = [h.strip().lower() for h in lines[0].split(",")]
    di = next((i for i, h in enumerate(head) if h in ("observation_date", "date")), None)
    if di is None or len(head) < 2:
        raise ValueError(f"열 이름을 찾지 못함: {head[:3]}")
    ci = 1 if di == 0 else 0

    points = []
    for line in lines[1:]:
        cols = line.split(",")
        if len(cols) <= max(di, ci):
            continue
        try:
            points.append({"d": cols[di].strip(), "c": round(float(cols[ci]), 2)})
        except ValueError:
            continue  # 휴일은 '.'
    if not points:
        raise ValueError("쓸 수 있는 값이 없음")
    return points


def from_yahoo(symbol):
    """야후 차트 JSON. FRED 가 아직 공표하지 않은 최근 며칠을 메운다."""
    resp = requests.get(YAHOO_CHART.format(sym=symbol), headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise ValueError("result 없음")
    stamps = result.get("timestamp") or []
    closes = (((result.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    points = []
    for ts, close in zip(stamps, closes):
        if close is None:
            continue
        day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
        points.append({"d": day, "c": round(float(close), 2)})
    if not points:
        raise ValueError("종가가 비어 있음")
    return points


def merge(primary, extra):
    """두 소스를 날짜로 합친다. 먼저 온 소스(FRED)의 값을 우선한다."""
    by_day = {p["d"]: p["c"] for p in (extra or [])}
    by_day.update({p["d"]: p["c"] for p in (primary or [])})
    return [{"d": d, "c": by_day[d]} for d in sorted(by_day)][-KEEP_DAYS:]


def fetch_series(spec):
    """소스를 순서대로 시도하고 어디서 받았는지 로그에 남긴다."""
    got, errors = {}, []
    for label, fn, arg in (("FRED", from_fred, spec.get("fred")),
                           ("Yahoo", from_yahoo, spec.get("yahoo"))):
        if not arg:
            continue
        try:
            got[label] = fn(arg)
            print(f"  [ok] {spec['name']} <- {label}: {len(got[label])}일, "
                  f"최근 {got[label][-1]['d']} {got[label][-1]['c']}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}: {exc}")
    if not got:
        raise ValueError(" | ".join(errors) or "소스 없음")
    if errors:
        print(f"  [warn] {spec['name']}: " + " | ".join(errors), file=sys.stderr)
    return merge(got.get("FRED"), got.get("Yahoo"))


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
    for spec in SERIES:
        try:
            pts = fetch_series(spec)
            series[spec["key"]] = {"name": spec["name"], "unit": spec["unit"], "points": pts}
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{spec['name']}: {exc}")

    fx = None
    try:
        fx = fetch_series(FX)[-1]["c"]
    except Exception as exc:  # noqa: BLE001
        failures.append(f"USD/KRW: {exc}")

    if failures:
        print("  [warn] " + " | ".join(failures), file=sys.stderr)

    old = load(OIL_JSON) or {}
    if not series:
        print("유가: 전부 실패 — 기존 파일 유지", file=sys.stderr)
        return False

    # 한 종목만 실패했다면 직전 파일의 값을 살려 카드가 비지 않게 한다.
    for spec in SERIES:
        key = spec["key"]
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
