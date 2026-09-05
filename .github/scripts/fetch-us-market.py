#!/usr/bin/env python3
"""Fetch US index and sector-ETF closes from Stooq and write them to
data/us-market.json (plus two chart PNGs under data/us/) for the daily
US market report.

Stooq serves plain daily CSV with no API key, which is the same source the
homepage's oil section uses. On any failure (network, symbol change, no new
session yet) this leaves the last known-good data in place and exits 0, so a
flaky upstream never breaks the site or the report.
"""
import csv
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_JSON = ROOT / "data" / "us-market.json"
OUT_CHART_DIR = ROOT / "data" / "us"

# 국내 관행에 맞춰 상승 빨강 / 하락 파랑. 사이트 --up/--down 토큰과 같은 값.
UP_COLOR = "#E5484D"
DOWN_COLOR = "#3B82F6"

INDICES = [
    {"symbol": "^spx", "yahoo": "^GSPC", "name": "S&P 500", "short": "S&P"},
    {"symbol": "^ndq", "yahoo": "^IXIC", "name": "나스닥 종합", "short": "나스닥"},
    {"symbol": "^dji", "yahoo": "^DJI", "name": "다우존스", "short": "다우"},
]

# SPDR 11개 섹터 ETF. 섹터 강약을 보는 가장 표준적인 대리지표다.
SECTORS = [
    {"symbol": "xlk.us", "yahoo": "XLK", "ticker": "XLK", "name": "기술"},
    {"symbol": "xlc.us", "yahoo": "XLC", "ticker": "XLC", "name": "커뮤니케이션"},
    {"symbol": "xly.us", "yahoo": "XLY", "ticker": "XLY", "name": "경기소비재"},
    {"symbol": "xlp.us", "yahoo": "XLP", "ticker": "XLP", "name": "필수소비재"},
    {"symbol": "xle.us", "yahoo": "XLE", "ticker": "XLE", "name": "에너지"},
    {"symbol": "xlf.us", "yahoo": "XLF", "ticker": "XLF", "name": "금융"},
    {"symbol": "xlv.us", "yahoo": "XLV", "ticker": "XLV", "name": "헬스케어"},
    {"symbol": "xli.us", "yahoo": "XLI", "ticker": "XLI", "name": "산업재"},
    {"symbol": "xlb.us", "yahoo": "XLB", "ticker": "XLB", "name": "소재"},
    {"symbol": "xlu.us", "yahoo": "XLU", "ticker": "XLU", "name": "유틸리티"},
    {"symbol": "xlre.us", "yahoo": "XLRE", "ticker": "XLRE", "name": "부동산"},
]

# 소스: 야후 차트 JSON.
# Stooq 는 쓰지 않는다. GitHub Actions IP 로 부르면 시세 CSV 대신
# "this site requires javascript to verify your browser" 봇 검사 페이지를
# 돌려준다(유가 수집기에서 실행 로그로 확인). 야후는 키 없이 서버에서 받힌다.
YAHOO_CHART = ("https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
               "?range=1y&interval=1d")
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,*/*;q=0.8",
}
TIMEOUT = 25
LOOKBACK = 120  # 차트와 이동평균에 쓸 최근 거래일 수


def fetch_series(spec):
    """야후 차트 JSON -> [{'d': 'YYYY-MM-DD', 'c': float}, ...] (오름차순)."""
    sym = spec["yahoo"] if isinstance(spec, dict) else spec
    resp = requests.get(
        YAHOO_CHART.format(sym=requests.utils.quote(sym, safe="")),
        headers=HEADERS, timeout=TIMEOUT,
    )
    resp.raise_for_status()
    result = ((resp.json().get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise ValueError(f"{sym}: result 없음")

    stamps = result.get("timestamp") or []
    closes = (((result.get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
    points = []
    for ts, close in zip(stamps, closes):
        if close is None:
            continue
        # 거래일은 뉴욕 기준이라 UTC 날짜로 찍으면 하루가 밀릴 수 있어
        # 장 마감 시각(현지 16시)을 포함하는 UTC 시각에서 날짜를 뽑는다.
        day = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
        points.append({"d": day, "c": float(close)})

    if len(points) < 25:
        raise ValueError(f"{sym}: 값이 너무 적음 ({len(points)})")
    return points[-LOOKBACK:]


def summarize(points):
    """종가와 1일·5일·20일 변화율."""
    closes = [p["c"] for p in points]
    last, prev = closes[-1], closes[-2]

    def pct_from(n):
        return round((last / closes[-1 - n] - 1) * 100, 2) if len(closes) > n else None

    return {
        "as_of_date": points[-1]["d"],
        "close": round(last, 2),
        "change": round(last - prev, 2),
        "change_pct": round((last / prev - 1) * 100, 2),
        "change_pct_5d": pct_from(5),
        "change_pct_20d": pct_from(20),
        "closes": [round(c, 2) for c in closes],
    }


def collect(items, key_name):
    out = []
    for item in items:
        try:
            points = fetch_series(item)
        except Exception as exc:  # 개별 심볼 실패는 그 항목만 건너뛴다
            print(f"skip {item['symbol']}: {exc}", file=sys.stderr)
            continue
        record = {k: v for k, v in item.items() if k not in ("symbol", "yahoo")}
        record[key_name] = item["symbol"]
        record.update(summarize(points))
        out.append(record)
    return out


def render_sector_chart(sectors):
    """섹터 등락률 가로 막대. 라벨은 티커(영문)로 둔다 — CI 러너에 한글
    폰트가 없어 한글 라벨은 두부(□)로 깨진다."""
    ordered = sorted(sectors, key=lambda s: s["change_pct"])
    labels = [s["ticker"] for s in ordered]
    values = [s["change_pct"] for s in ordered]
    colors = [UP_COLOR if v >= 0 else DOWN_COLOR for v in values]

    fig, ax = plt.subplots(figsize=(6.4, 4.0), dpi=200)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    ax.barh(labels, values, color=colors, height=0.68, linewidth=0)
    ax.axvline(0, color="#6B7891", linewidth=0.9)

    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#C6CEDB")
    ax.tick_params(colors="#3D4A63", labelsize=9, length=0)
    ax.set_xlabel("Daily change (%)", color="#6B7891", fontsize=9)
    ax.grid(axis="x", color="#D6DCE6", linewidth=0.6)
    ax.set_axisbelow(True)

    pad = (max(values) - min(values)) * 0.12 or 0.2
    ax.set_xlim(min(values) - pad, max(values) + pad)
    for y, v in enumerate(values):
        ax.text(v + (pad * 0.12 if v >= 0 else -pad * 0.12), y, f"{v:+.2f}",
                va="center", ha="left" if v >= 0 else "right",
                fontsize=8.5, color="#3D4A63")

    OUT_CHART_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_CHART_DIR / "sectors.png", transparent=True,
                bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)


def render_index_chart(indices):
    """3대 지수 최근 흐름을 시작점 100으로 정규화해 한 축에 겹쳐 그린다."""
    fig, ax = plt.subplots(figsize=(6.4, 2.6), dpi=200)
    fig.patch.set_alpha(0)
    ax.set_facecolor("none")

    palette = ["#B06A15", "#2F6F62", "#3D4A63"]
    for idx, color in zip(indices, palette):
        closes = idx["closes"]
        base = closes[0]
        ax.plot(range(len(closes)), [c / base * 100 for c in closes],
                color=color, linewidth=1.5, label=idx["short_en"])

    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("bottom", "left"):
        ax.spines[spine].set_color("#C6CEDB")
    ax.tick_params(colors="#3D4A63", labelsize=8.5, length=0)
    ax.set_xticks([])
    ax.set_ylabel("Indexed to 100", color="#6B7891", fontsize=8.5)
    ax.grid(axis="y", color="#D6DCE6", linewidth=0.6)
    ax.set_axisbelow(True)
    leg = ax.legend(frameon=False, fontsize=8.5, loc="upper left")
    for text in leg.get_texts():
        text.set_color("#3D4A63")

    OUT_CHART_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_CHART_DIR / "indices.png", transparent=True,
                bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)


def main():
    indices = collect(INDICES, "symbol")
    sectors = collect(SECTORS, "symbol")

    if not indices or len(sectors) < 6:
        print(f"insufficient data (indices={len(indices)}, sectors={len(sectors)}), "
              "leaving existing data in place", file=sys.stderr)
        return 0

    # 차트 범례는 영문으로 (한글 폰트 부재)
    for idx in indices:
        idx["short_en"] = {"S&P 500": "S&P 500", "나스닥 종합": "Nasdaq",
                           "다우존스": "Dow"}.get(idx["name"], idx["name"])

    as_of = max(i["as_of_date"] for i in indices)

    render_sector_chart(sectors)
    render_index_chart(indices)

    # closes 배열은 차트를 그리고 나면 필요 없다 — JSON을 가볍게 유지한다.
    for row in indices + sectors:
        row.pop("closes", None)
        row.pop("short_en", None)

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "as_of_date": as_of,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "indices": indices,
                "sectors": sectors,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {OUT_JSON.name} for {as_of} "
          f"({len(indices)} indices, {len(sectors)} sectors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
