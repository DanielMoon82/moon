#!/usr/bin/env python3
"""Turn data/stocks-kr.json into a daily closing-market report.

Writes, for the date the data is as of:
  posts/market-YYYY-MM-DD.html          홈페이지 기사 페이지
  blogger-posts/market-YYYY-MM-DD.html  블로거 자동 발행용 (front matter 포함)
  blog-exports/market-YYYY-MM-DD/…      네이버·티스토리 붙여넣기용
  data/latest-report.json               홈페이지가 최신 글을 가리키는 데 사용

Everything here is derived from the numbers in stocks-kr.json - no causes
or forecasts are invented, since this job has no news source to justify
them.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_PATH = ROOT / "data" / "stocks-kr.json"
LATEST_PATH = ROOT / "data" / "latest-report.json"
POSTS_DIR = ROOT / "posts"
BLOGGER_DIR = ROOT / "blogger-posts"
EXPORT_DIR = ROOT / "blog-exports"
SITE = "https://danielmoon82.github.io/moon"
KST = timezone(timedelta(hours=9))


def fmt_int(n):
    return f"{n:,}" if isinstance(n, int) else "-"


def fmt_signed(n, unit="주"):
    if not isinstance(n, int):
        return "-"
    return f"{'+' if n > 0 else ''}{n:,}{unit}"


def arrow(change):
    return "▲" if change > 0 else ("▼" if change < 0 else "―")


def flow_word(n):
    if not isinstance(n, int) or n == 0:
        return "보합"
    return "순매수" if n > 0 else "순매도"


def analyze(s):
    """Derive the indicators an analyst would actually cite, straight from
    the stored 20-day history. Returns None when history isn't available
    yet, so callers fall back to the plain factual sentence."""
    hist = [h for h in (s.get("history") or []) if isinstance(h.get("close"), int)]
    if len(hist) < 5:
        return None

    closes = [h["close"] for h in hist]
    volumes = [h["volume"] for h in hist]
    close = s["close"]

    ma5 = sum(closes[-5:]) / 5
    ma20 = sum(closes) / len(closes)
    hi, lo = max(closes), min(closes)
    band = hi - lo

    def streak(key):
        """Consecutive days at the end with the same flow direction."""
        vals = [h.get(key) for h in hist if isinstance(h.get(key), int)]
        if not vals:
            return 0, 0
        sign = 1 if vals[-1] > 0 else (-1 if vals[-1] < 0 else 0)
        if sign == 0:
            return 0, 0
        n = 0
        for v in reversed(vals):
            if (v > 0) == (sign > 0) and v != 0:
                n += 1
            else:
                break
        return sign, n

    f_sign, f_streak = streak("foreign")
    i_sign, i_streak = streak("institution")
    f_vals = [h["foreign"] for h in hist if isinstance(h.get("foreign"), int)]

    return {
        "ma5": ma5,
        "ma20": ma20,
        "vs_ma5": (close / ma5 - 1) * 100 if ma5 else 0.0,
        "vs_ma20": (close / ma20 - 1) * 100 if ma20 else 0.0,
        "high": hi,
        "low": lo,
        "range_pos": ((close - lo) / band * 100) if band else 50.0,
        "vol_ratio": (s["volume"] / (sum(volumes) / len(volumes))) if volumes else 1.0,
        "avg_volume": sum(volumes) / len(volumes),
        "foreign_streak": (f_sign, f_streak),
        "institution_streak": (i_sign, i_streak),
        "foreign_buy_days": sum(1 for v in f_vals if v > 0),
        "flow_days": len(f_vals),
        "days": len(hist),
    }


def trend_phrase(vs_ma20):
    if vs_ma20 >= 5:
        return "20일 이동평균을 크게 웃도는 자리"
    if vs_ma20 >= 1:
        return "20일 이동평균 위"
    if vs_ma20 > -1:
        return "20일 이동평균에 바짝 붙은 자리"
    if vs_ma20 > -5:
        return "20일 이동평균 아래"
    return "20일 이동평균을 크게 밑도는 자리"


def volume_phrase(ratio):
    if ratio >= 1.5:
        return f"20일 평균의 {ratio:.1f}배로 크게 늘었습니다"
    if ratio >= 1.15:
        return f"20일 평균보다 {(ratio - 1) * 100:.0f}% 많았습니다"
    if ratio >= 0.85:
        return "20일 평균과 비슷한 수준이었습니다"
    return f"20일 평균의 {ratio:.0%} 수준으로 줄었습니다"


def streak_phrase(label, sign, days):
    if not sign or days < 2:
        return None
    word = "순매수" if sign > 0 else "순매도"
    return f"{label}은 {days}거래일 연속 {word}"


def analysis_paragraphs(s, m):
    """Two paragraphs per ticker: where the price sits, then what the flow
    is doing. Interpretation stays inside what the numbers support."""
    close = s["close"]
    direction = "상승" if s["change"] > 0 else ("하락" if s["change"] < 0 else "보합")

    p1 = (
        f"{s['name']}는 {s['change_pct']:+.2f}% {direction}한 {fmt_int(close)}원에 거래를 마쳤습니다. "
        f"현재가는 {trend_phrase(m['vs_ma20'])}로, 20일 이동평균({fmt_int(round(m['ma20']))}원) 대비 "
        f"{m['vs_ma20']:+.1f}%, 5일 이동평균({fmt_int(round(m['ma5']))}원) 대비 {m['vs_ma5']:+.1f}% 수준입니다. "
        f"최근 {m['days']}거래일 저점 {fmt_int(m['low'])}원과 고점 {fmt_int(m['high'])}원이 만든 구간에서는 "
        f"위쪽으로 {m['range_pos']:.0f}% 지점에 위치해 있습니다. "
        f"거래량은 {fmt_int(s['volume'])}주로 {volume_phrase(m['vol_ratio'])}."
    )

    fnv, inv = s.get("foreign_net_volume"), s.get("institution_net_volume")
    if isinstance(fnv, int) and isinstance(inv, int):
        bits = [
            f"수급에서는 외국인이 {fmt_int(abs(fnv))}주 {flow_word(fnv)}, "
            f"기관이 {fmt_int(abs(inv))}주 {flow_word(inv)}했습니다."
        ]
        streaks = [
            phrase for phrase in (
                streak_phrase("외국인", *m["foreign_streak"]),
                streak_phrase("기관", *m["institution_streak"]),
            ) if phrase
        ]
        if streaks:
            bits.append(", ".join(streaks) + " 중입니다.")
        if m["flow_days"]:
            bits.append(
                f"최근 {m['flow_days']}거래일 가운데 외국인이 순매수한 날은 {m['foreign_buy_days']}일이며, "
                f"누적으로는 외국인 {fmt_signed(s['period'].get('foreign_net_volume_sum'))}, "
                f"기관 {fmt_signed(s['period'].get('institution_net_volume_sum'))}입니다."
            )
        if (fnv > 0) != (inv > 0):
            bits.append("두 주체가 서로 반대 방향으로 움직인 하루였습니다.")
        p2 = " ".join(bits)
    else:
        p2 = "수급 확정치는 아직 집계되지 않았습니다."

    return [p1, p2]


def overview_paragraph(stocks, metrics):
    """Opening read across the three names."""
    ups = [s["name"] for s in stocks if s["change"] > 0]
    strongest = max(stocks, key=lambda s: s["change_pct"])
    weakest = min(stocks, key=lambda s: s["change_pct"])

    above = [s["name"] for s, m in zip(stocks, metrics) if m and m["vs_ma20"] > 0]
    heavy = [s["name"] for s, m in zip(stocks, metrics) if m and m["vol_ratio"] >= 1.15]
    f_sell = [
        s["name"] for s in stocks
        if isinstance(s.get("foreign_net_volume"), int) and s["foreign_net_volume"] < 0
    ]

    parts = [
        f"{len(ups)}개 종목이 오르고 {len(stocks) - len(ups)}개가 내렸습니다. "
        f"상대적으로 가장 강했던 종목은 {strongest['name']}({strongest['change_pct']:+.2f}%), "
        f"가장 부진했던 종목은 {weakest['name']}({weakest['change_pct']:+.2f}%)입니다."
    ]
    if above:
        parts.append(f"20일 이동평균 위에서 마감한 종목은 {'·'.join(above)}입니다.")
    else:
        parts.append("세 종목 모두 20일 이동평균을 밑돌며 마감했습니다.")
    if heavy:
        parts.append(f"거래량이 평소보다 뚜렷하게 늘어난 종목은 {'·'.join(heavy)}였습니다.")
    if f_sell:
        parts.append(
            f"외국인은 {'·'.join(f_sell)}에서 순매도했습니다."
            if len(f_sell) < len(stocks) else "외국인은 세 종목 모두에서 순매도했습니다."
        )
    return " ".join(parts)


def checkpoints(stocks, metrics):
    """Concrete levels to watch tomorrow - all arithmetic from the data,
    no targets or recommendations."""
    items = []
    for s, m in zip(stocks, metrics):
        if not m:
            continue
        if m["vs_ma20"] >= 0:
            items.append(
                f"{s['name']}: 20일선 {fmt_int(round(m['ma20']))}원이 아래쪽 지지 여부를 가늠할 기준선입니다."
            )
        else:
            items.append(
                f"{s['name']}: 20일선 {fmt_int(round(m['ma20']))}원 회복 여부가 단기 흐름의 분기점입니다."
            )
    return items


def stock_sentence(s):
    """One factual paragraph per ticker: price move, volume, both flows,
    then the 20-day cumulative direction as context."""
    direction = "올라" if s["change"] > 0 else ("내려" if s["change"] < 0 else "보합으로")
    parts = [
        f"{s['name']}는 전 거래일 대비 {abs(s['change_pct']):.2f}% {direction} "
        f"{fmt_int(s['close'])}원에 마감했습니다. 거래량은 {fmt_int(s['volume'])}주였습니다."
    ]

    fnv, inv = s.get("foreign_net_volume"), s.get("institution_net_volume")
    if isinstance(fnv, int) and isinstance(inv, int):
        parts.append(
            f"수급은 외국인 {fmt_int(abs(fnv))}주 {flow_word(fnv)}, "
            f"기관 {fmt_int(abs(inv))}주 {flow_word(inv)}로 집계됐습니다."
        )

    period = s.get("period") or {}
    fsum, isum = period.get("foreign_net_volume_sum"), period.get("institution_net_volume_sum")
    days = period.get("days")
    if isinstance(fsum, int) and isinstance(isum, int) and days:
        parts.append(
            f"최근 {days}거래일 누적으로는 외국인 {fmt_signed(fsum)}, 기관 {fmt_signed(isum)}입니다."
        )
    return " ".join(parts)


def summary_line(stocks):
    up = [s["name"] for s in stocks if s["change"] > 0]
    down = [s["name"] for s in stocks if s["change"] < 0]
    flat = [s["name"] for s in stocks if s["change"] == 0]

    if len(up) == len(stocks):
        return "세 종목이 모두 상승 마감했습니다."
    if len(down) == len(stocks):
        return "세 종목이 모두 하락 마감했습니다."

    bits = []
    if up:
        bits.append(f"{'·'.join(up)}가 상승")
    if down:
        bits.append(f"{'·'.join(down)}가 하락")
    if flat:
        bits.append(f"{'·'.join(flat)}가 보합")
    return ", ".join(bits) + " 마감했습니다."


def table_rows_html(stocks):
    rows = []
    for s in stocks:
        rows.append(
            "<tr>"
            f"<td style=\"padding:8px;border-bottom:1px solid #e5e5e5;\">{s['name']}</td>"
            f"<td style=\"padding:8px;border-bottom:1px solid #e5e5e5;text-align:right;\">{fmt_int(s['close'])}원</td>"
            f"<td style=\"padding:8px;border-bottom:1px solid #e5e5e5;text-align:right;\">{arrow(s['change'])} {fmt_int(abs(s['change']))} ({s['change_pct']:+.2f}%)</td>"
            f"<td style=\"padding:8px;border-bottom:1px solid #e5e5e5;text-align:right;\">{fmt_int(s['volume'])}주</td>"
            f"<td style=\"padding:8px;border-bottom:1px solid #e5e5e5;text-align:right;\">{fmt_signed(s.get('foreign_net_volume'))}</td>"
            f"<td style=\"padding:8px;border-bottom:1px solid #e5e5e5;text-align:right;\">{fmt_signed(s.get('institution_net_volume'))}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def body_html(date, stocks):
    """Shared article body used by Blogger and Tistory."""
    metrics = [analyze(s) for s in stocks]
    intro = overview_paragraph(stocks, metrics) if any(metrics) else summary_line(stocks)

    blocks = []
    for s, m in zip(stocks, metrics):
        blocks.append(f"<h3>{s['name']} ({s['code']})</h3>")
        if m:
            blocks.extend(f"<p>{p}</p>" for p in analysis_paragraphs(s, m))
        else:
            blocks.append(f"<p>{stock_sentence(s)}</p>")
    paragraphs = "\n".join(blocks)

    checks = checkpoints(stocks, metrics)
    check_html = (
        "<h2>내일 확인할 지점</h2>\n<ul>\n"
        + "\n".join(f"  <li>{c}</li>" for c in checks)
        + "\n</ul>\n"
    ) if checks else ""
    charts = "\n".join(
        f'<div style="text-align:center;margin:18px 0;">'
        f'<img src="{SITE}/data/stocks/{s["code"]}.png" alt="{s["name"]} 최근 60거래일 주가·거래량" style="max-width:100%;height:auto;" />'
        f'<div style="font-size:0.85em;color:#777;">{s["name"]} 최근 60거래일 주가·거래량</div>'
        f"</div>"
        for s in stocks
    )
    return f"""<p>{date} 국내 증시 주요 3종목의 마감 결과를 정리했습니다. {summary_line(stocks)}</p>

<h2>총평</h2>
<p>{intro}</p>

<h2>한눈에 보기</h2>
<table style="width:100%;border-collapse:collapse;font-size:0.95em;">
  <thead>
    <tr>
      <th style="padding:8px;border-bottom:2px solid #ccc;text-align:left;">종목</th>
      <th style="padding:8px;border-bottom:2px solid #ccc;text-align:right;">종가</th>
      <th style="padding:8px;border-bottom:2px solid #ccc;text-align:right;">등락</th>
      <th style="padding:8px;border-bottom:2px solid #ccc;text-align:right;">거래량</th>
      <th style="padding:8px;border-bottom:2px solid #ccc;text-align:right;">외국인</th>
      <th style="padding:8px;border-bottom:2px solid #ccc;text-align:right;">기관</th>
    </tr>
  </thead>
  <tbody>
{table_rows_html(stocks)}
  </tbody>
</table>

<h2>종목별 분석</h2>
{paragraphs}

{check_html}
<h2>차트</h2>
{charts}

<p style="font-size:0.9em;color:#666;">본 글은 한국거래소·네이버금융 공개 데이터를 바탕으로 자동 정리된 기록이며, 투자 판단의 참고 자료일 뿐 매수·매도를 권유하지 않습니다.</p>
<p style="font-size:0.9em;color:#666;">매일 갱신되는 시황 배너는 <a href="{SITE}/#stocks" target="_blank" rel="noopener">야간비행 일지</a>에서 볼 수 있습니다.</p>"""


def write_homepage_article(date, stocks, slug):
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        f"<tr><td>{s['name']}</td><td class=\"num\">{fmt_int(s['close'])}원</td>"
        f"<td class=\"num {'up' if s['change'] > 0 else 'down' if s['change'] < 0 else ''}\">"
        f"{arrow(s['change'])} {fmt_int(abs(s['change']))} ({s['change_pct']:+.2f}%)</td>"
        f"<td class=\"num\">{fmt_int(s['volume'])}주</td>"
        f"<td class=\"num\">{fmt_signed(s.get('foreign_net_volume'))}</td>"
        f"<td class=\"num\">{fmt_signed(s.get('institution_net_volume'))}</td></tr>"
        for s in stocks
    )
    metrics = [analyze(s) for s in stocks]
    intro = overview_paragraph(stocks, metrics) if any(metrics) else summary_line(stocks)

    blocks = []
    for s, m in zip(stocks, metrics):
        blocks.append(f'<h3>{s["name"]} <span class="code">{s["code"]}</span></h3>')
        if m:
            blocks.extend(f"<p>{p}</p>" for p in analysis_paragraphs(s, m))
        else:
            blocks.append(f"<p>{stock_sentence(s)}</p>")
    paragraphs = "\n  ".join(blocks)

    checks = checkpoints(stocks, metrics)
    check_block = (
        "<h2>내일 확인할 지점</h2>\n  <ul class=\"checks\">\n    "
        + "\n    ".join(f"<li>{c}</li>" for c in checks)
        + "\n  </ul>"
    ) if checks else ""

    charts = "\n  ".join(
        f'<figure><img src="../data/stocks/{s["code"]}.png" alt="{s["name"]} 최근 60거래일 주가·거래량">'
        f'<figcaption>{s["name"]} · 최근 60거래일</figcaption></figure>'
        for s in stocks
    )

    html = f"""<title>{date} 마감 시황 — 야간비행 일지</title>
<meta name="description" content="{date} 삼성전자·SK하이닉스·현대차 마감 시황. 종가, 거래량, 외국인·기관 수급을 정리했습니다.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="{SITE}/posts/{slug}.html">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Hahmlet:wght@400;600;800&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@300;400;500;600&display=swap">

<style>
  :root{{
    --paper:#E7EBF1;--surface:#F4F6FA;--surface-2:#DCE2EC;
    --ink:#0F1729;--ink-2:#3D4A63;--ink-3:#6B7891;
    --line:#C6CEDB;--line-soft:#D6DCE6;--accent:#B06A15;--accent-bright:#C2761A;
    --up:#E5484D;--down:#3B82F6;
    --f-display:"Hahmlet",'Nanum Myeongjo',"Apple SD Gothic Neo",serif;
    --f-body:"IBM Plex Sans KR","Apple SD Gothic Neo","Malgun Gothic",sans-serif;
    --f-mono:"IBM Plex Mono","SFMono-Regular",Consolas,monospace;
    --pad:clamp(20px,5vw,64px);
  }}
  @media (prefers-color-scheme:dark){{
    :root:not([data-theme="light"]){{
      --paper:#0B1120;--surface:#121A2C;--surface-2:#1A2439;
      --ink:#E9EEF7;--ink-2:#A9B5C9;--ink-3:#72809A;
      --line:#26314A;--line-soft:#1D2739;--accent:#E8A33D;--accent-bright:#F0B45C;
    }}
  }}
  *{{box-sizing:border-box;}}
  body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--f-body);
    font-weight:300;font-size:16px;line-height:1.75;-webkit-font-smoothing:antialiased;}}
  a{{color:inherit;}}
  img{{max-width:100%;height:auto;}}
  .wrap{{max-width:760px;margin:0 auto;padding-inline:var(--pad);}}
  .nav{{position:sticky;top:0;z-index:20;background:color-mix(in srgb,var(--paper) 88%,transparent);
    backdrop-filter:saturate(180%) blur(12px);border-bottom:1px solid var(--line);}}
  .nav-in{{display:flex;align-items:center;justify-content:space-between;height:58px;}}
  .brand{{font-family:var(--f-display);font-weight:600;font-size:1rem;letter-spacing:-.02em;text-decoration:none;}}
  .back{{font-family:var(--f-mono);font-size:.72rem;color:var(--ink-3);text-decoration:none;}}
  .article{{padding-block:clamp(40px,7vw,72px) clamp(56px,9vw,96px);}}
  .eyebrow{{font-family:var(--f-mono);font-size:.68rem;letter-spacing:.16em;text-transform:uppercase;
    color:var(--accent);margin:0 0 14px;}}
  h1{{font-family:var(--f-display);font-weight:800;font-size:clamp(1.6rem,4.4vw,2.3rem);
    line-height:1.3;letter-spacing:-.03em;margin:0 0 16px;}}
  .byline{{font-family:var(--f-mono);font-size:.72rem;color:var(--ink-3);
    padding-bottom:24px;border-bottom:1px solid var(--line);margin-bottom:32px;}}
  h2{{font-family:var(--f-display);font-weight:600;font-size:1.25rem;letter-spacing:-.02em;margin:42px 0 14px;}}
  h3{{font-family:var(--f-display);font-weight:600;font-size:1.05rem;letter-spacing:-.02em;
    margin:30px 0 10px;padding-top:14px;border-top:1px solid var(--line-soft);}}
  h3 .code{{font-family:var(--f-mono);font-size:.7rem;font-weight:400;color:var(--ink-3);margin-left:6px;}}
  p{{margin:0 0 18px;color:var(--ink-2);}}
  ul.checks{{margin:0 0 18px;padding-left:20px;color:var(--ink-2);}}
  ul.checks li{{margin-bottom:8px;font-size:.94rem;}}
  table{{width:100%;border-collapse:collapse;font-size:.88rem;margin-bottom:8px;}}
  th{{font-family:var(--f-mono);font-size:.66rem;letter-spacing:.06em;text-transform:uppercase;
    color:var(--ink-3);text-align:right;padding:8px 6px;border-bottom:1px solid var(--line);}}
  th:first-child{{text-align:left;}}
  td{{padding:10px 6px;border-bottom:1px solid var(--line-soft);color:var(--ink-2);}}
  td.num{{font-family:var(--f-mono);text-align:right;font-variant-numeric:tabular-nums;}}
  td.up{{color:var(--up);}} td.down{{color:var(--down);}}
  .scroll{{overflow-x:auto;}}
  figure{{margin:22px 0;}}
  figure img{{display:block;border-radius:3px;background:var(--surface-2);}}
  figcaption{{margin-top:8px;font-family:var(--f-mono);font-size:.68rem;color:var(--ink-3);text-align:center;}}
  .note{{margin-top:34px;padding:16px 18px;border-left:3px solid var(--accent);
    background:var(--surface);border-radius:0 3px 3px 0;}}
  .note p{{margin:0;font-size:.85rem;color:var(--ink-3);}}
  .foot{{border-top:1px solid var(--line);background:var(--surface);padding-block:30px 38px;}}
  .foot p{{margin:0;font-size:.8rem;color:var(--ink-3);}}
</style>

<nav class="nav">
  <div class="wrap nav-in">
    <a class="brand" href="../index.html">야간비행 일지</a>
    <a class="back" href="../index.html#stocks">← 시황으로</a>
  </div>
</nav>

<main class="wrap article">
  <p class="eyebrow">Market</p>
  <h1>{date} 마감 시황</h1>
  <p class="byline">삼성전자 · SK하이닉스 · 현대차 · 종가 기준</p>

  <p>{summary_line(stocks)}</p>

  <h2>총평</h2>
  <p>{intro}</p>

  <h2>한눈에 보기</h2>
  <div class="scroll">
    <table>
      <thead><tr><th>종목</th><th>종가</th><th>등락</th><th>거래량</th><th>외국인</th><th>기관</th></tr></thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </div>

  <h2>종목별 분석</h2>
  {paragraphs}

  {check_block}

  <h2>차트</h2>
  {charts}

  <div class="note">
    <p>한국거래소·네이버금융 공개 데이터를 바탕으로 매일 자동 생성되는 기록입니다. 투자 판단의 참고 자료일 뿐, 매수·매도를 권유하지 않습니다.</p>
  </div>
</main>

<footer class="foot">
  <div class="wrap"><p>야간비행 일지 · 마감 시황은 장 종료 후 자동 갱신됩니다.</p></div>
</footer>
"""
    (POSTS_DIR / f"{slug}.html").write_text(html, encoding="utf-8")


def write_blogger_post(date, stocks, slug):
    BLOGGER_DIR.mkdir(parents=True, exist_ok=True)
    front = (
        "---\n"
        f"title: {date} 마감 시황 — 삼성전자·SK하이닉스·현대차 종가와 수급 정리\n"
        "labels: 주식, 마감시황, 삼성전자, SK하이닉스, 현대차, 증시\n"
        f"search_description: {date} 삼성전자·SK하이닉스·현대차의 종가, 거래량, 외국인·기관 수급을 정리한 마감 시황입니다.\n"
        "status: LIVE\n"
        "---\n"
    )
    (BLOGGER_DIR / f"{slug}.html").write_text(front + body_html(date, stocks) + "\n", encoding="utf-8")


def write_manual_exports(date, stocks, slug):
    out = EXPORT_DIR / slug
    out.mkdir(parents=True, exist_ok=True)

    metrics = [analyze(s) for s in stocks]
    intro = overview_paragraph(stocks, metrics) if any(metrics) else summary_line(stocks)

    lines = [
        "════════════════════════════════════════",
        "네이버 블로그용 (붙여넣기)",
        "════════════════════════════════════════",
        "",
        "[제목란]",
        f"{date} 마감 시황 | 삼성전자 SK하이닉스 현대차 종가 수급 분석",
        "",
        "[본문]",
        "",
        f"{date} 국내 증시 주요 3종목의 마감 결과를 정리했습니다. {intro}",
        "",
        "■ 한눈에 보기",
        "",
    ]
    for s in stocks:
        lines.append(
            f"{s['name']} : {fmt_int(s['close'])}원 {arrow(s['change'])} {fmt_int(abs(s['change']))} "
            f"({s['change_pct']:+.2f}%) / 거래량 {fmt_int(s['volume'])}주 / "
            f"외국인 {fmt_signed(s.get('foreign_net_volume'))} / 기관 {fmt_signed(s.get('institution_net_volume'))}"
        )

    lines += ["", "■ 종목별 분석", ""]
    for s, m in zip(stocks, metrics):
        lines.append(f"[{s['name']} {s['code']}]")
        if m:
            lines += analysis_paragraphs(s, m) + [""]
        else:
            lines += [stock_sentence(s), ""]

    checks = checkpoints(stocks, metrics)
    if checks:
        lines += ["■ 내일 확인할 지점", ""] + checks + [""]
    lines += [
        "▶ 차트 이미지 3장 첨부 (data/stocks/ 폴더의 005930.png, 000660.png, 005380.png)",
        "",
        "한국거래소·네이버금융 공개 데이터를 바탕으로 정리한 기록이며, 투자 판단의 참고 자료일 뿐 매수·매도를 권유하지 않습니다.",
        "",
        "[태그란]",
        "#마감시황 #주식시황 #삼성전자 #SK하이닉스 #현대차 #국내증시 #외국인수급 #기관수급 #주식정보 #증시마감",
    ]
    (out / "네이버블로그.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    tistory = (
        "<!--\n"
        "티스토리: 글쓰기 → 기본모드 → HTML 선택 후 아래 전체 붙여넣기\n"
        f"제목: {date} 마감 시황 | 삼성전자·SK하이닉스·현대차 종가와 수급\n"
        "태그: 마감시황, 주식시황, 삼성전자, SK하이닉스, 현대차, 국내증시, 외국인수급, 기관수급\n"
        "-->\n\n"
    )
    (out / "티스토리.html").write_text(tistory + body_html(date, stocks) + "\n", encoding="utf-8")


def main():
    if not DATA_PATH.exists():
        print("data/stocks-kr.json not found", file=sys.stderr)
        return 1

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    stocks = data.get("stocks") or []
    date = data.get("as_of_date")

    if not stocks or not date:
        print("no stock data yet, nothing to report", file=sys.stderr)
        return 0

    if any(not isinstance(s.get("close"), int) for s in stocks):
        print("incomplete price data, skipping report", file=sys.stderr)
        return 0

    slug = f"market-{date}"
    write_homepage_article(date, stocks, slug)
    write_blogger_post(date, stocks, slug)
    write_manual_exports(date, stocks, slug)

    LATEST_PATH.write_text(
        json.dumps(
            {
                "date": date,
                "url": f"posts/{slug}.html",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"generated report for {date} ({slug})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
