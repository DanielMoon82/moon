#!/usr/bin/env python3
"""Fetch daily OHLCV + investor net-buying data for a fixed watchlist of KRX
tickers and write it to data/stocks-kr.json (plus a mini chart PNG per
ticker under data/stocks/) for the site to read client-side.

Run on a schedule by .github/workflows/fetch-stocks.yml. On any failure
(network, KRX schema change, no trading data yet) this leaves the last
known-good data in place and exits 0, so the site never shows a broken
banner because of a flaky upstream source.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pykrx import stock

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_JSON = ROOT / "data" / "stocks-kr.json"
OUT_CHART_DIR = ROOT / "data" / "stocks"

KST = timezone(timedelta(hours=9))

WATCHLIST = [
    {"code": "005930", "name": "삼성전자"},
    {"code": "000660", "name": "SK하이닉스"},
    {"code": "005380", "name": "현대차"},
]

PERIOD_DAYS = 20
CHART_LOOKBACK_DAYS = 60
UP_COLOR = "#E5484D"
DOWN_COLOR = "#3B82F6"


def fetch_one(code):
    today = datetime.now(KST).date()
    fromdate = (today - timedelta(days=120)).strftime("%Y%m%d")
    todate = today.strftime("%Y%m%d")

    ohlcv = stock.get_market_ohlcv_by_date(fromdate, todate, code)
    flow = stock.get_market_trading_value_by_date(fromdate, todate, code)
    if ohlcv.empty or len(ohlcv) < 2:
        raise ValueError(f"no OHLCV rows for {code}")

    df = ohlcv.join(flow[["기관합계", "외국인합계"]], how="left").dropna(subset=["종가"])
    if len(df) < 2:
        raise ValueError(f"not enough joined rows for {code}")

    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = int(last["종가"])
    prev_close = int(prev["종가"])
    change = close - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0

    period_df = df.tail(PERIOD_DAYS)

    result = {
        "code": code,
        "close": close,
        "change": change,
        "change_pct": round(change_pct, 2),
        "volume": int(last["거래량"]),
        "foreign_net_value": int(last["외국인합계"]) if "외국인합계" in df.columns else None,
        "institution_net_value": int(last["기관합계"]) if "기관합계" in df.columns else None,
        "as_of_date": df.index[-1].strftime("%Y-%m-%d"),
        "period": {
            "days": len(period_df),
            "foreign_net_value_sum": int(period_df["외국인합계"].sum()) if "외국인합계" in df.columns else None,
            "institution_net_value_sum": int(period_df["기관합계"].sum()) if "기관합계" in df.columns else None,
        },
        "chart": f"stocks/{code}.png",
    }

    chart_df = df.tail(CHART_LOOKBACK_DAYS)
    render_chart(chart_df, code)
    return result


def render_chart(df, code):
    OUT_CHART_DIR.mkdir(parents=True, exist_ok=True)
    closes = df["종가"].tolist()
    volumes = df["거래량"].tolist()
    prev_closes = [None] + closes[:-1]
    vol_colors = [
        UP_COLOR if (p is not None and c >= p) else DOWN_COLOR if p is not None else "#9AA5B8"
        for c, p in zip(closes, prev_closes)
    ]

    fig, (ax_price, ax_vol) = plt.subplots(
        2, 1, figsize=(4.4, 1.9), dpi=200, sharex=True,
        gridspec_kw={"height_ratios": [3, 1], "hspace": 0.08},
    )
    fig.patch.set_alpha(0)
    for ax in (ax_price, ax_vol):
        ax.set_facecolor("none")
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.margins(x=0.02)

    line_color = UP_COLOR if closes[-1] >= closes[0] else DOWN_COLOR
    x = range(len(closes))
    ax_price.plot(x, closes, color=line_color, linewidth=1.4)
    ax_price.fill_between(x, closes, min(closes), color=line_color, alpha=0.08)

    ax_vol.bar(x, volumes, color=vol_colors, width=0.8, linewidth=0)

    out_path = OUT_CHART_DIR / f"{code}.png"
    fig.savefig(out_path, transparent=True, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)


def main():
    stocks = []
    for item in WATCHLIST:
        try:
            data = fetch_one(item["code"])
        except Exception as exc:  # network/schema failure: skip this ticker only
            print(f"skip {item['code']} ({item['name']}): {exc}", file=sys.stderr)
            continue
        data["name"] = item["name"]
        stocks.append(data)

    if not stocks:
        print("no tickers fetched, leaving existing data in place", file=sys.stderr)
        return 0

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps(
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "as_of_date": stocks[0]["as_of_date"],
                "stocks": stocks,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(stocks)} tickers to {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
