#!/usr/bin/env python3
"""Fetch daily OHLCV + investor net-buying data for a fixed watchlist of KRX
tickers and write it to data/stocks-kr.json (plus a mini chart PNG per
ticker under data/stocks/) for the site to read client-side.

Run on a schedule by .github/workflows/fetch-stocks.yml. On any failure
(network, KRX schema change, no trading data yet) this leaves the last
known-good data in place and exits 0, so the site never shows a broken
banner because of a flaky upstream source.
"""
import io
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import requests
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
FLOW_RETRIES = 3
FLOW_RETRY_DELAY = 5
FLOW_PAGES = 4  # ~10 rows/page; need >= PERIOD_DAYS trading days

FRGN_URL = "https://finance.naver.com/item/frgn.naver"
FRGN_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; moon-stock-bot/1.0)"}


def fetch_investor_net_volume(code):
    """Net buy/sell VOLUME (shares, not KRW) by institutions/foreigners, from
    Naver Finance's investor-trend page. KRX's own official API for this
    (get_market_trading_value_by_date) is blocked outright for GitHub
    Actions' IP ranges (verified: every retry returns an empty body), while
    Naver Finance is reachable — it's the same source pykrx itself uses for
    OHLCV. Table columns are matched by header keywords rather than a fixed
    index/position, since Naver's markup isn't a stable contract.
    """
    frames = []
    for page in range(1, FLOW_PAGES + 1):
        resp = requests.get(
            FRGN_URL, params={"code": code, "page": page}, headers=FRGN_HEADERS, timeout=10
        )
        resp.raise_for_status()
        resp.encoding = "euc-kr"
        tables = pd.read_html(io.StringIO(resp.text))

        target = None
        for t in tables:
            cols = ["".join(str(c).split()) for c in t.columns]
            has_date = any("날짜" in c for c in cols)
            has_inst = any("기관" in c and "순매매" in c for c in cols)
            has_frgn = any(c.startswith("외국인") and "순매매" in c for c in cols)
            if has_date and has_inst and has_frgn:
                target = t.copy()
                target.columns = cols
                break
        if target is None or target.empty:
            if page == 1:
                diag = " | ".join(",".join(str(c) for c in t.columns) for t in tables) or "(no tables at all)"
                print(f"debug {code} p1: status={resp.status_code} len={len(resp.text)} tables={len(tables)} cols=[{diag}] head={resp.text[:200]!r}", file=sys.stderr)
            break
        frames.append(target)

    if not frames:
        raise ValueError(f"no investor-flow table found for {code}")

    df = pd.concat(frames, ignore_index=True)
    date_col = next(c for c in df.columns if "날짜" in c)
    inst_col = next(c for c in df.columns if "기관" in c and "순매매" in c)
    frgn_col = next(c for c in df.columns if c.startswith("외국인") and "순매매" in c)

    df = df[[date_col, inst_col, frgn_col]].dropna()
    df[date_col] = pd.to_datetime(df[date_col], format="%Y.%m.%d", errors="coerce")
    for c in (inst_col, frgn_col):
        df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
    df = df.dropna(subset=[date_col, inst_col, frgn_col])
    if df.empty:
        raise ValueError(f"investor-flow table parsed empty for {code}")

    df = df.set_index(date_col).sort_index()
    df = df[~df.index.duplicated(keep="first")]  # overshooting the last page repeats rows
    return df.rename(columns={inst_col: "기관순매매량", frgn_col: "외국인순매매량"})


def fetch_one(code):
    """Price/volume can be an in-progress intraday row (this job runs every
    15min during market hours). Investor net-buying is only posted once
    confirmed after market close, so it's tracked separately and may
    legitimately lag the price row by one trading day while the market is
    open — that's a data-source limitation, not a bug.
    """
    today = datetime.now(KST).date()
    fromdate = (today - timedelta(days=120)).strftime("%Y%m%d")
    todate = today.strftime("%Y%m%d")

    ohlcv = stock.get_market_ohlcv_by_date(fromdate, todate, code).dropna(subset=["종가"])
    if ohlcv.empty or len(ohlcv) < 2:
        raise ValueError(f"no OHLCV rows for {code}")

    last = ohlcv.iloc[-1]
    prev = ohlcv.iloc[-2]
    close = int(last["종가"])
    prev_close = int(prev["종가"])
    change = close - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0

    result = {
        "code": code,
        "close": close,
        "change": change,
        "change_pct": round(change_pct, 2),
        "volume": int(last["거래량"]),
        "as_of_date": ohlcv.index[-1].strftime("%Y-%m-%d"),
        "foreign_net_volume": None,
        "institution_net_volume": None,
        "flow_as_of_date": None,
        "period": {"days": 0, "foreign_net_volume_sum": None, "institution_net_volume_sum": None},
        "chart": f"stocks/{code}.png",
    }

    flow = None
    for attempt in range(1, FLOW_RETRIES + 1):
        try:
            flow = fetch_investor_net_volume(code)
            break
        except Exception as exc:  # flaky upstream: retry a few times before giving up
            print(f"flow attempt {attempt}/{FLOW_RETRIES} failed for {code}: {exc}", file=sys.stderr)
            flow = None
            if attempt < FLOW_RETRIES:
                time.sleep(FLOW_RETRY_DELAY)
    if flow is None:
        print(f"flow unavailable for {code} after {FLOW_RETRIES} attempts, keeping price-only", file=sys.stderr)
    else:
        flow_last = flow.iloc[-1]
        period_df = flow.tail(PERIOD_DAYS)
        result.update({
            "foreign_net_volume": int(flow_last["외국인순매매량"]),
            "institution_net_volume": int(flow_last["기관순매매량"]),
            "flow_as_of_date": flow.index[-1].strftime("%Y-%m-%d"),
            "period": {
                "days": len(period_df),
                "foreign_net_volume_sum": int(period_df["외국인순매매량"].sum()),
                "institution_net_volume_sum": int(period_df["기관순매매량"].sum()),
            },
        })

    render_chart(ohlcv.tail(CHART_LOOKBACK_DAYS), code)
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
