#!/usr/bin/env python3
"""Turn data/us-market.json into the daily US market report, in the four
shapes this repo publishes to:

  posts/us-market-YYYY-MM-DD.html          홈페이지 기사 페이지
  blogger-posts/us-market-YYYY-MM-DD.html  구글 블로거 자동 발행용 (front matter)
  blog-exports/<slug>/티스토리.html        티스토리 붙여넣기용
  blog-exports/<slug>/네이버블로그.txt     네이버 블로그 붙여넣기용

Every number in the prose comes from the JSON; nothing is hard-coded. Run by
.github/workflows/us-market-report.yml after the US close.
"""
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from article_shell import PAGE_CSS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_PATH = ROOT / "data" / "us-market.json"
POSTS_DIR = ROOT / "posts"
BLOGGER_DIR = ROOT / "blogger-posts"
EXPORT_DIR = ROOT / "blog-exports"
LATEST_PATH = ROOT / "data" / "latest-us-report.json"

SITE = "https://danielmoon82.github.io/moon"

# 섹터 성격 분류. 자금이 어디로 돌았는지(로테이션) 해석하는 근거다.
CYCLICAL = {"XLY", "XLF", "XLI", "XLB", "XLE"}
DEFENSIVE = {"XLP", "XLV", "XLU", "XLRE"}
GROWTH = {"XLK", "XLC"}

MIN_CHARS = 2000  # 본문 최소 글자 수 (요청 기준)


# 조사 선택. 종목·지수 이름이 데이터에서 오기 때문에 "S&P 500는", "소재(XLB)이"
# 같은 어색한 문장이 그대로 발행되지 않도록 받침을 보고 고른다.
_DIGIT_BATCHIM = {"0": True, "1": True, "2": False, "3": True, "4": False,
                  "5": False, "6": True, "7": True, "8": True, "9": False}
# 알파벳은 한국어로 읽었을 때의 끝소리 기준 (F=에프, L=엘, M=엠, N=엔, R=알, S=에스, X=엑스)
_ALPHA_BATCHIM = {c: c in "FLMNRSX" for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}


def has_batchim(word):
    """문자열 끝소리에 받침이 있는지. 괄호·기호는 건너뛰고 판단한다."""
    for ch in reversed(word):
        if "가" <= ch <= "힣":
            return (ord(ch) - 0xAC00) % 28 != 0
        if ch.isdigit():
            return _DIGIT_BATCHIM[ch]
        if ch.isalpha() and ch.upper() in _ALPHA_BATCHIM:
            return _ALPHA_BATCHIM[ch.upper()]
    return False  # 판단할 글자가 없으면 받침 없는 쪽으로


def josa(word, with_batchim, without_batchim):
    return word + (with_batchim if has_batchim(word) else without_batchim)


def eun(word):
    return josa(word, "은", "는")


def ga(word):
    return josa(word, "이", "가")


def euro(word):
    """으로/로. 받침 ㄹ 뒤에는 '로'가 붙는다."""
    for ch in reversed(word):
        if "가" <= ch <= "힣":
            return word + ("으로" if (ord(ch) - 0xAC00) % 28 not in (0, 8) else "로")
        if ch.isdigit() or (ch.isalpha() and ch.upper() in _ALPHA_BATCHIM):
            return word + ("으로" if has_batchim(word) else "로")
    return word + "로"


def pct(v):
    return f"{v:+.2f}%"


def arrow(v):
    return "▲" if v > 0 else "▼" if v < 0 else "-"


def cls(v):
    return "up" if v > 0 else "down" if v < 0 else ""


def num(v):
    return f"{v:,.2f}"


def avg(rows):
    return round(sum(r["change_pct"] for r in rows) / len(rows), 2) if rows else 0.0


def group(sectors, names):
    return [s for s in sectors if s["ticker"] in names]


def pick(indices, name):
    for i in indices:
        if i["name"] == name:
            return i
    return None


# ---------------------------------------------------------------- 본문 문장

def lede(date, indices, sectors):
    ups = [s for s in sectors if s["change_pct"] > 0]
    downs = [s for s in sectors if s["change_pct"] < 0]
    parts = [
        f"{i['name']} {num(i['close'])}({pct(i['change_pct'])})" for i in indices
    ]
    return (
        f"{date} 미국 증시는 {', '.join(parts)}로 마감했습니다. "
        f"11개 업종 가운데 {len(ups)}개가 오르고 {len(downs)}개가 내렸습니다. "
        f"아래에서 지수 마감 수치, 강세·약세 섹터, 자금이 어느 쪽으로 움직였는지, "
        f"그리고 국내 증시에서 이어서 볼 지점까지 순서대로 정리했습니다."
    )


def index_paragraph(indices):
    best = max(indices, key=lambda i: i["change_pct"])
    worst = min(indices, key=lambda i: i["change_pct"])
    spread = round(best["change_pct"] - worst["change_pct"], 2)

    lines = []
    for i in indices:
        spans = []
        if i.get("change_pct_5d") is not None:
            spans.append(f"최근 5거래일 {pct(i['change_pct_5d'])}")
        if i.get("change_pct_20d") is not None:
            spans.append(f"20거래일 {pct(i['change_pct_20d'])}")
        tail = f" {', '.join(spans)}입니다." if spans else ""
        lines.append(
            f"{eun(i['name'])} {euro(num(i['close']))} 전 거래일 대비 "
            f"{arrow(i['change'])} {num(abs(i['change']))}포인트({pct(i['change_pct'])}) "
            f"움직였습니다.{tail}"
        )

    if spread >= 0.5:
        lines.append(
            f"세 지수의 등락률 격차가 {spread:.2f}%포인트로 벌어졌습니다. "
            f"{ga(best['name'])} 가장 강했고 {ga(worst['name'])} 가장 약했는데, "
            f"이 정도 차이는 지수를 구성하는 업종의 성격이 서로 다르게 반응했다는 뜻입니다. "
            f"지수 하나만 보고 '올랐다·내렸다'로 정리하기 어려운 날입니다."
        )
    else:
        lines.append(
            f"세 지수의 등락률 격차는 {spread:.2f}%포인트로 크지 않았습니다. "
            f"특정 업종이 지수를 끌고 갔다기보다 시장 전체가 비슷한 방향으로 움직인 날에 가깝습니다."
        )
    return lines


def strong_paragraph(sectors):
    top = sorted(sectors, key=lambda s: -s["change_pct"])[:3]
    label = f"{top[0]['name']}({top[0]['ticker']})"
    lines = [
        f"이날 가장 강했던 업종은 {euro(label)} "
        f"{pct(top[0]['change_pct'])} 올랐습니다. "
        f"이어 {top[1]['name']}({top[1]['ticker']}) {pct(top[1]['change_pct'])}, "
        f"{top[2]['name']}({top[2]['ticker']}) {pct(top[2]['change_pct'])} 순이었습니다."
    ]
    lead = top[0]
    if lead.get("change_pct_20d") is not None:
        if lead["change_pct_20d"] > 0 and lead["change_pct"] > 0:
            lines.append(
                f"{lead['name']} 업종은 최근 20거래일 수익률도 {pct(lead['change_pct_20d'])}로 "
                f"플러스입니다. 하루 반등이 아니라 한 달 가까이 이어진 흐름의 연장선으로 볼 수 있습니다."
            )
        elif lead["change_pct_20d"] < 0:
            lines.append(
                f"다만 {lead['name']} 업종의 최근 20거래일 수익률은 {pct(lead['change_pct_20d'])}로 "
                f"여전히 마이너스입니다. 이날 상승은 그동안 눌렸던 자리에서 나온 반등 성격이 큽니다. "
                f"추세 전환으로 보려면 며칠 더 확인이 필요합니다."
            )
    return lines


def weak_paragraph(sectors):
    bottom = sorted(sectors, key=lambda s: s["change_pct"])[:3]
    label = f"{bottom[0]['name']}({bottom[0]['ticker']})"
    lines = [
        f"반대로 가장 약했던 업종은 {euro(label)} "
        f"{pct(bottom[0]['change_pct'])} 내렸습니다. "
        f"{bottom[1]['name']}({bottom[1]['ticker']}) {pct(bottom[1]['change_pct'])}, "
        f"{bottom[2]['name']}({bottom[2]['ticker']})도 {pct(bottom[2]['change_pct'])}로 부진했습니다."
    ]
    lag = bottom[0]
    if lag.get("change_pct_5d") is not None:
        if lag["change_pct_5d"] < 0:
            lines.append(
                f"{lag['name']} 업종은 최근 5거래일 기준으로도 {pct(lag['change_pct_5d'])}입니다. "
                f"하루 급락이 아니라 며칠에 걸쳐 자금이 빠지고 있는 쪽에 가깝습니다."
            )
        else:
            lines.append(
                f"{lag['name']} 업종의 최근 5거래일 수익률은 {pct(lag['change_pct_5d'])}로 "
                f"아직 플러스입니다. 이날 하락은 짧은 되돌림일 가능성이 있어, "
                f"5거래일 수익률이 마이너스로 꺾이는지가 다음 확인 지점입니다."
            )
    return lines


def rotation_paragraph(sectors):
    cyc, dfn, grw = group(sectors, CYCLICAL), group(sectors, DEFENSIVE), group(sectors, GROWTH)
    c, d, g = avg(cyc), avg(dfn), avg(grw)
    gap = round(c - d, 2)

    lines = [
        f"업종을 성격별로 묶어 보면 경기민감 업종(경기소비재·금융·산업재·소재·에너지) 평균이 "
        f"{pct(c)}, 방어 업종(필수소비재·헬스케어·유틸리티·부동산) 평균이 {pct(d)}, "
        f"기술·커뮤니케이션 평균이 {pct(g)}입니다."
    ]

    if gap >= 0.3:
        lines.append(
            f"경기민감 업종이 방어 업종을 {abs(gap):.2f}%포인트 앞섰습니다. "
            f"위험을 감수하는 쪽으로 자금이 기운 '위험선호(리스크온)' 구도입니다. "
            f"보통 경기 전망이 나쁘지 않다고 볼 때 나타나는 배열입니다."
        )
    elif gap <= -0.3:
        lines.append(
            f"방어 업종이 경기민감 업종을 {abs(gap):.2f}%포인트 앞섰습니다. "
            f"경기 변동에 덜 흔들리는 쪽으로 자금이 옮겨간 '위험회피(리스크오프)' 구도입니다. "
            f"지수가 올랐더라도 내용은 방어적이었다는 뜻이라, 지수 등락만 보면 놓치기 쉬운 대목입니다."
        )
    else:
        lines.append(
            f"두 그룹의 차이는 {abs(gap):.2f}%포인트로 뚜렷하지 않습니다. "
            f"특정 방향으로 자금이 쏠렸다기보다 관망에 가까운 날입니다."
        )

    if g - max(c, d) >= 0.3:
        lines.append(
            f"기술·커뮤니케이션이 나머지 업종을 앞선 것도 눈에 띕니다. "
            f"지수에서 차지하는 비중이 큰 업종이라, 이쪽이 강한 날은 나스닥과 S&P 500의 "
            f"등락률이 다우보다 커지는 경향이 있습니다."
        )
    elif min(c, d) - g >= 0.3:
        lines.append(
            f"반면 기술·커뮤니케이션은 상대적으로 뒤처졌습니다. "
            f"시가총액 비중이 큰 업종이 쉬어 가면 지수 상승 폭이 제한되기 쉽습니다."
        )
    return lines


def breadth_paragraph(sectors):
    ups = [s for s in sectors if s["change_pct"] > 0]
    downs = [s for s in sectors if s["change_pct"] < 0]
    best, worst = max(sectors, key=lambda s: s["change_pct"]), min(sectors, key=lambda s: s["change_pct"])
    spread = round(best["change_pct"] - worst["change_pct"], 2)
    mean = avg(sectors)

    lines = [
        f"11개 업종의 평균 등락률은 {pct(mean)}, 1위와 11위의 격차는 "
        f"{spread:.2f}%포인트였습니다. 상승 {len(ups)}개, 하락 {len(downs)}개입니다."
    ]

    if spread >= 2.0:
        lines.append(
            f"업종 간 격차가 {spread:.2f}%포인트까지 벌어진 날은 지수 등락률만으로 시장을 "
            f"요약하기 어렵습니다. 같은 날 어떤 업종은 크게 오르고 어떤 업종은 크게 내렸다는 뜻이고, "
            f"이런 장에서는 무엇을 들고 있었느냐에 따라 체감 수익률이 크게 갈립니다. "
            f"지수를 추종하는 자금보다 업종을 고르는 자금이 주도한 날로 보는 편이 맞습니다."
        )
    elif spread <= 0.8:
        lines.append(
            f"업종 간 격차가 {spread:.2f}%포인트로 좁습니다. 업종을 가리지 않고 비슷하게 움직였다는 "
            f"뜻으로, 개별 업종의 재료보다 금리나 지수 선물 같은 시장 전체 변수가 그날을 "
            f"지배했을 때 자주 나오는 모습입니다."
        )

    if len(ups) >= 9:
        lines.append(
            f"상승 업종이 {len(ups)}개로 대부분을 차지했습니다. 소수 대형주가 지수를 끌어올린 "
            f"상승이 아니라 시장 전반이 함께 오른 상승이라, 상승의 질이 좋은 편에 속합니다."
        )
    elif len(ups) <= 2:
        lines.append(
            f"상승 업종이 {len(ups)}개에 그쳤습니다. 지수가 어떻게 마감했든 내부적으로는 "
            f"파는 손이 우세했던 날입니다. 이런 날 지수가 버텼다면 시가총액 상위 몇 종목이 "
            f"떠받쳤을 가능성이 큽니다."
        )
    return lines


def trend_paragraph(sectors):
    """당일 순위와 5·20거래일 순위를 비교해 흐름이 이어지는지 본다."""
    has5 = [s for s in sectors if s.get("change_pct_5d") is not None]
    has20 = [s for s in sectors if s.get("change_pct_20d") is not None]
    if not has5 or not has20:
        return []

    w_best = max(has5, key=lambda s: s["change_pct_5d"])
    w_worst = min(has5, key=lambda s: s["change_pct_5d"])
    m_best = max(has20, key=lambda s: s["change_pct_20d"])
    today_best = max(sectors, key=lambda s: s["change_pct"])
    m_label = f"{m_best['name']}({m_best['ticker']})"

    lines = [
        f"기간을 넓혀 보면 최근 5거래일 1위는 {w_best['name']}({w_best['ticker']}) "
        f"{pct(w_best['change_pct_5d'])}, 꼴찌는 {w_worst['name']}({w_worst['ticker']}) "
        f"{pct(w_worst['change_pct_5d'])}입니다. 20거래일 기준으로는 "
        f"{ga(m_label)} {pct(m_best['change_pct_20d'])}로 앞서 있습니다."
    ]

    if today_best["ticker"] == w_best["ticker"]:
        lines.append(
            f"당일 1위와 5거래일 1위가 {today_best['name']}으로 같습니다. "
            f"하루 반등이 아니라 최근 며칠 이어져 온 주도 업종이라는 뜻이고, "
            f"이런 연속성은 다음 거래일에도 이어질 확률이 상대적으로 높습니다."
        )
    else:
        lines.append(
            f"당일 1위({today_best['name']})와 5거래일 1위({w_best['name']})가 다릅니다. "
            f"주도 업종이 바뀌는 중이거나, 그날 하루짜리 재료가 순위를 흔들었을 수 있습니다. "
            f"어느 쪽인지는 다음 거래일에 {ga(today_best['name'])} 상위권을 지키는지로 갈립니다."
        )

    if m_best["change_pct"] < 0:
        lines.append(
            f"한 달 기준 1위인 {m_best['name']} 업종이 이날은 {pct(m_best['change_pct'])}로 "
            f"쉬어 갔습니다. 많이 오른 업종에서 차익 실현이 나오는 흐름인지, "
            f"추세가 꺾이는 신호인지는 며칠 더 봐야 판단할 수 있습니다."
        )
    return lines


def korea_paragraph(sectors):
    tech = next((s for s in sectors if s["ticker"] == "XLK"), None)
    energy = next((s for s in sectors if s["ticker"] == "XLE"), None)
    fin = next((s for s in sectors if s["ticker"] == "XLF"), None)

    lines = []
    if tech:
        if tech["change_pct"] > 0:
            lines.append(
                f"국내 증시에서 먼저 볼 곳은 반도체입니다. 미국 기술 업종(XLK)이 "
                f"{pct(tech['change_pct'])}로 마감했는데, 이 업종의 방향은 다음 날 "
                f"삼성전자·SK하이닉스의 시초가에 그대로 반영되는 경우가 많습니다. "
                f"다만 지수를 그대로 따라가기보다, 외국인 순매수가 같이 들어오는지를 함께 봐야 합니다."
            )
        else:
            lines.append(
                f"국내 증시에서 먼저 볼 곳은 반도체입니다. 미국 기술 업종(XLK)이 "
                f"{pct(tech['change_pct'])}로 밀렸기 때문에, 삼성전자·SK하이닉스가 "
                f"약세로 출발할 가능성을 열어둘 필요가 있습니다. "
                f"이럴 때는 시초가 낙폭보다 장중에 외국인 매도가 이어지는지가 더 중요한 신호입니다."
            )
    if energy:
        lines.append(
            f"에너지 업종(XLE)은 {pct(energy['change_pct'])}였습니다. "
            f"국제 유가와 방향을 같이하는 업종이라, 정유·화학주와 항공주가 서로 반대로 움직이는 "
            f"날인지 가늠하는 데 참고가 됩니다."
        )
    if fin:
        lines.append(
            f"금융 업종(XLF)은 {pct(fin['change_pct'])}로 마감했습니다. "
            f"금리 방향에 민감한 업종이라, 국내 은행·증권주의 분위기를 미리 짚어 보는 용도로 씁니다."
        )
    lines.append(
        "다만 미국 업종 등락이 국내 종목으로 그대로 옮겨오지는 않습니다. "
        "환율, 국내 수급, 그날의 개별 공시가 방향을 바꾸는 경우가 흔합니다. "
        "미국장 마감은 출발선을 가늠하는 참고치로 두고, 실제 판단은 국내 장중 흐름과 "
        "외국인·기관 수급을 확인한 뒤에 하는 편이 안전합니다."
    )
    return lines


def checkpoints(indices, sectors):
    out = []
    top = max(sectors, key=lambda s: s["change_pct"])
    bottom = min(sectors, key=lambda s: s["change_pct"])
    top_label = f"{top['name']}({top['ticker']})"
    out.append(
        f"{ga(top_label)} {pct(top['change_pct'])}로 1위였습니다. "
        f"다음 거래일에도 상위권을 지키는지 — 하루짜리 반등과 이어지는 흐름은 여기서 갈립니다."
    )
    out.append(
        f"{bottom['name']}({bottom['ticker']}) {pct(bottom['change_pct'])}의 하락이 "
        f"멈추는지, 아니면 이틀 연속으로 이어지는지."
    )
    ups = len([s for s in sectors if s["change_pct"] > 0])
    out.append(
        f"이날 상승 업종은 11개 중 {ups}개였습니다. 이 숫자가 늘어나는지 줄어드는지가 "
        f"지수 등락보다 시장의 폭을 더 정확히 보여줍니다."
    )
    nasdaq, dow = pick(indices, "나스닥 종합"), pick(indices, "다우존스")
    if nasdaq and dow:
        gap = round(nasdaq["change_pct"] - dow["change_pct"], 2)
        out.append(
            f"나스닥과 다우의 등락률 차이는 {gap:+.2f}%포인트였습니다. "
            f"이 격차가 벌어지면 성장주와 가치주 중 한쪽으로 쏠리고 있다는 신호입니다."
        )
    return out


GLOSSARY = [
    ("섹터 ETF", "특정 업종에 속한 종목들을 묶어 놓은 상장지수펀드입니다. "
                 "개별 종목의 사정에 덜 흔들리기 때문에 업종 전체의 방향을 볼 때 씁니다. "
                 "이 글에서 쓴 XLK·XLF 같은 티커가 모두 여기에 해당합니다."),
    ("리스크온·리스크오프", "위험을 감수하고 경기민감 자산으로 가는 국면을 리스크온, "
                          "반대로 안전한 쪽으로 피하는 국면을 리스크오프라고 부릅니다. "
                          "지수가 아니라 업종 배열을 봐야 구분됩니다."),
    ("섹터 로테이션", "자금이 업종 사이를 옮겨 다니는 현상입니다. "
                    "지수는 제자리인데 어떤 업종은 크게 오르고 어떤 업종은 크게 내리는 날이 여기에 해당합니다."),
    ("5거래일·20거래일 수익률", "각각 최근 일주일과 한 달 정도의 흐름을 뜻합니다. "
                                "당일 등락률만 보면 하루짜리 소음에 휘둘리기 쉬워서, "
                                "같은 업종을 여러 기간으로 겹쳐 보면 추세인지 반등인지 구분하기 쉬워집니다."),
    ("시장의 폭", "오른 종목(업종)이 얼마나 많은지를 말합니다. "
                "소수 대형주만 올라 지수를 끌어올린 상승과, 대부분이 함께 오른 상승은 성격이 다릅니다."),
]


def plain_body(date, indices, sectors):
    """채널 공통 본문을 문단 리스트로 만든다. HTML/텍스트 양쪽이 이걸 쓴다."""
    return [
        ("리드", [lede(date, indices, sectors)]),
        ("지수 마감", index_paragraph(indices)),
        ("강세 섹터", strong_paragraph(sectors)),
        ("약세 섹터", weak_paragraph(sectors)),
        ("자금은 어디로 움직였나", rotation_paragraph(sectors)),
        ("시장의 폭과 업종 간 격차", breadth_paragraph(sectors)),
        ("하루가 아니라 흐름으로 보면", trend_paragraph(sectors)),
        ("국내 증시에서 볼 지점", korea_paragraph(sectors)),
    ]


# ---------------------------------------------------------------- 출력 공통

def index_rows_html(indices):
    return "\n".join(
        f"<tr><td>{i['name']}</td><td class=\"num\">{num(i['close'])}</td>"
        f"<td class=\"num {cls(i['change'])}\">{arrow(i['change'])} {num(abs(i['change']))} "
        f"({pct(i['change_pct'])})</td>"
        f"<td class=\"num\">{pct(i['change_pct_5d']) if i.get('change_pct_5d') is not None else '-'}</td>"
        f"<td class=\"num\">{pct(i['change_pct_20d']) if i.get('change_pct_20d') is not None else '-'}</td></tr>"
        for i in indices
    )


def sector_rows_html(sectors):
    return "\n".join(
        f"<tr><td>{s['name']}</td><td class=\"num\">{s['ticker']}</td>"
        f"<td class=\"num\">{num(s['close'])}</td>"
        f"<td class=\"num {cls(s['change_pct'])}\">{arrow(s['change_pct'])} {pct(s['change_pct'])}</td>"
        f"<td class=\"num\">{pct(s['change_pct_5d']) if s.get('change_pct_5d') is not None else '-'}</td>"
        f"<td class=\"num\">{pct(s['change_pct_20d']) if s.get('change_pct_20d') is not None else '-'}</td></tr>"
        for s in sorted(sectors, key=lambda x: -x["change_pct"])
    )


def body_html(date, indices, sectors, chart_prefix):
    sections = plain_body(date, indices, sectors)
    lead = sections[0][1][0]

    def paras(items):
        return "\n  ".join(f"<p>{t}</p>" for t in items)

    checks = "\n    ".join(f"<li>{c}</li>" for c in checkpoints(indices, sectors))
    glossary = "\n  ".join(
        f"<h3>{term}</h3>\n  <p>{desc}</p>" for term, desc in GLOSSARY
    )

    return f"""<p>{lead}</p>

  <h2>지수 마감</h2>
  {paras(sections[1][1])}
  <div class="scroll">
    <table>
      <thead><tr><th>지수</th><th>종가</th><th>등락</th><th>5거래일</th><th>20거래일</th></tr></thead>
      <tbody>
{index_rows_html(indices)}
      </tbody>
    </table>
  </div>
  <figure><img src="{chart_prefix}indices.png" alt="S&amp;P 500 나스닥 다우존스 최근 흐름 비교 차트">
  <figcaption>3대 지수 · 최근 흐름 (시작점 100 기준)</figcaption></figure>

  <h2>강세 섹터</h2>
  {paras(sections[2][1])}

  <h2>약세 섹터</h2>
  {paras(sections[3][1])}

  <h2>업종별 등락률</h2>
  <div class="scroll">
    <table>
      <thead><tr><th>업종</th><th>티커</th><th>종가</th><th>등락률</th><th>5거래일</th><th>20거래일</th></tr></thead>
      <tbody>
{sector_rows_html(sectors)}
      </tbody>
    </table>
  </div>
  <figure><img src="{chart_prefix}sectors.png" alt="미국 11개 업종 ETF 등락률 비교 막대 차트">
  <figcaption>11개 업종 ETF · 당일 등락률</figcaption></figure>

  <h2>자금은 어디로 움직였나</h2>
  {paras(sections[4][1])}

  <h2>시장의 폭과 업종 간 격차</h2>
  {paras(sections[5][1])}

  <h2>하루가 아니라 흐름으로 보면</h2>
  {paras(sections[6][1])}

  <h2>국내 증시에서 볼 지점</h2>
  {paras(sections[7][1])}

  <h2>다음 거래일 확인할 것</h2>
  <ul class="checks">
    {checks}
  </ul>

  <h2>용어 정리</h2>
  {glossary}

  <div class="note">
    <p>Stooq 공개 시세를 바탕으로 미국장 마감 후 자동 생성되는 기록입니다.
    지수·ETF 종가 기준이며, 투자 판단의 참고 자료일 뿐 매수·매도를 권유하지 않습니다.</p>
  </div>"""


def body_text(date, indices, sectors):
    """네이버 블로그처럼 HTML을 못 쓰는 곳에 넣을 평문."""
    lines = []
    for heading, items in plain_body(date, indices, sectors):
        if heading != "리드":
            lines += ["", f"■ {heading}", ""]
        lines += items

    lines += ["", "■ 업종별 등락률", ""]
    for s in sorted(sectors, key=lambda x: -x["change_pct"]):
        lines.append(f"{s['name']}({s['ticker']}) : {num(s['close'])} / 당일 {pct(s['change_pct'])}"
                     + (f" / 5거래일 {pct(s['change_pct_5d'])}" if s.get("change_pct_5d") is not None else ""))

    lines += ["", "■ 다음 거래일 확인할 것", ""] + checkpoints(indices, sectors)
    lines += ["", "■ 용어 정리", ""]
    for term, desc in GLOSSARY:
        lines.append(f"· {term} — {desc}")
    return lines


def char_count(date, indices, sectors):
    """본문 글자 수(공백 제외). 요청한 2천자 기준을 지키는지 확인용."""
    text = "".join(
        t for _, items in plain_body(date, indices, sectors) for t in items
    ) + "".join(checkpoints(indices, sectors)) + "".join(d for _, d in GLOSSARY)
    return len(re.sub(r"\s", "", text))


# ---------------------------------------------------------------- 채널별 출력

def seo_title(date, indices):
    lead = max(indices, key=lambda i: abs(i["change_pct"]))
    return f"{date} 미국증시 마감 시황 — {lead['name']} {pct(lead['change_pct'])}, 강세·약세 섹터 정리"


def seo_description(date, indices, sectors):
    top = max(sectors, key=lambda s: s["change_pct"])
    bottom = min(sectors, key=lambda s: s["change_pct"])
    idx = ", ".join(f"{i['name']} {pct(i['change_pct'])}" for i in indices)
    return (f"{date} 미국증시 마감. {idx}. "
            f"강세 {top['name']} {pct(top['change_pct'])}, 약세 {bottom['name']} "
            f"{pct(bottom['change_pct'])}. 11개 업종 등락률과 섹터 로테이션, "
            f"국내 증시 관전 포인트까지 정리했습니다.")


TAGS = ["미국증시", "미국주식", "마감시황", "해외주식", "S&P500", "나스닥", "다우존스",
        "섹터분석", "섹터로테이션", "증시전망", "주식공부", "미국장마감"]


def write_homepage_article(date, indices, sectors, slug):
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    title = seo_title(date, indices)
    desc = seo_description(date, indices, sectors)
    url = f"{SITE}/posts/{slug}.html"

    ld = json.dumps({
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": title,
        "description": desc,
        "datePublished": datetime.now(timezone.utc).isoformat(),
        "author": {"@type": "Person", "name": "야간비행 일지"},
        "publisher": {"@type": "Organization", "name": "야간비행 일지"},
        "mainEntityOfPage": url,
        "image": f"{SITE}/data/us/sectors.png",
        "keywords": ", ".join(TAGS),
    }, ensure_ascii=False, indent=2)

    html = f"""<meta charset="utf-8">
<title>{title} — 야간비행 일지</title>
<meta name="description" content="{desc}">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="{url}">
<meta property="og:type" content="article">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{SITE}/data/us/sectors.png">
<meta name="twitter:card" content="summary_large_image">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Hahmlet:wght@400;600;800&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@300;400;500;600&display=swap">
<script type="application/ld+json">
{ld}
</script>

{PAGE_CSS}

<nav class="nav">
  <div class="wrap nav-in">
    <a class="brand" href="../index.html">야간비행 일지</a>
    <a class="back" href="../index.html#stocks">← 시황으로</a>
  </div>
</nav>

<main class="wrap article">
  <p class="eyebrow">US Market</p>
  <h1>{date} 미국증시 마감 시황</h1>
  <p class="byline">S&amp;P 500 · 나스닥 · 다우존스 · 11개 업종 ETF · 종가 기준</p>

  {body_html(date, indices, sectors, "../data/us/")}
</main>

<footer class="foot">
  <div class="wrap"><p>야간비행 일지 · 미국장 마감 시황은 장 종료 후 자동 갱신됩니다.</p></div>
</footer>
"""
    (POSTS_DIR / f"{slug}.html").write_text(html, encoding="utf-8")


def write_blogger_post(date, indices, sectors, slug):
    BLOGGER_DIR.mkdir(parents=True, exist_ok=True)
    front = (
        "---\n"
        f"title: {seo_title(date, indices)}\n"
        f"labels: {', '.join(TAGS[:8])}\n"
        f"search_description: {seo_description(date, indices, sectors)}\n"
        "status: LIVE\n"
        "---\n"
    )
    body = body_html(date, indices, sectors, f"{SITE}/data/us/")
    (BLOGGER_DIR / f"{slug}.html").write_text(front + body + "\n", encoding="utf-8")


def write_manual_exports(date, indices, sectors, slug):
    out = EXPORT_DIR / slug
    out.mkdir(parents=True, exist_ok=True)

    tistory = (
        "<!--\n"
        "티스토리: 글쓰기 → 기본모드 → HTML 선택 후 아래 전체 붙여넣기\n"
        "카테고리: 주식·투자\n"
        "(위 카테고리가 블로그에 없으면 '투자' 또는 '재테크'로 바꾸세요)\n"
        f"제목: {seo_title(date, indices)}\n"
        f"태그: {', '.join(TAGS)}\n"
        "썸네일: data/us/sectors.png 를 대표 이미지로 지정\n"
        "-->\n\n"
    )
    (out / "티스토리.html").write_text(
        tistory + body_html(date, indices, sectors, f"{SITE}/data/us/") + "\n",
        encoding="utf-8")

    lines = [
        "════════════════════════════════════════",
        "네이버 블로그용 (붙여넣기)",
        "════════════════════════════════════════",
        "",
        "[카테고리]",
        "주식·재테크",
        "(위 카테고리가 없으면 '경제/비즈니스'를 쓰세요)",
        "",
        "[제목란]",
        f"{date} 미국증시 마감 시황 | 강세 약세 섹터 정리와 국내 증시 관전 포인트",
        "",
        "[본문]",
        "",
    ] + body_text(date, indices, sectors) + [
        "",
        "▶ 차트 이미지 2장 첨부 (data/us/ 폴더의 indices.png, sectors.png)",
        "",
        "Stooq 공개 시세를 바탕으로 정리한 기록이며, 투자 판단의 참고 자료일 뿐 "
        "매수·매도를 권유하지 않습니다.",
        "",
        "[태그란]",
        " ".join(f"#{t.replace('&', '').replace(' ', '')}" for t in TAGS),
    ]
    (out / "네이버블로그.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    if not DATA_PATH.exists():
        print("data/us-market.json not found", file=sys.stderr)
        return 1

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    indices = data.get("indices") or []
    sectors = data.get("sectors") or []
    date = data.get("as_of_date")

    if not indices or len(sectors) < 6 or not date:
        print("incomplete US market data, skipping report", file=sys.stderr)
        return 0

    # 미국 휴장일에는 us-market.json 이 직전 거래일 값을 그대로 들고 있다.
    # 그대로 돌리면 지난 리포트를 새 글인 양 다시 쓰게 되므로, 데이터 날짜가
    # 직전 영업일(한국 시각 기준 어제)이 아니면 건너뛴다.
    # --force 로 과거분을 다시 만들 수 있다.
    kst_today = datetime.now(timezone(timedelta(hours=9))).date()
    if (kst_today - datetime.strptime(date, "%Y-%m-%d").date()).days > 3 \
            and "--force" not in sys.argv:
        print(f"데이터가 {date} 기준이라 최근 미국장이 열리지 않았다고 보고 건너뜁니다.")
        return 0

    slug = f"us-market-{date}"
    count = char_count(date, indices, sectors)
    if count < MIN_CHARS:
        # 문구 템플릿을 줄이는 변경이 들어가면 여기서 잡힌다.
        print(f"WARNING: body is {count} chars, below the {MIN_CHARS} target",
              file=sys.stderr)

    write_homepage_article(date, indices, sectors, slug)
    write_blogger_post(date, indices, sectors, slug)
    write_manual_exports(date, indices, sectors, slug)

    LATEST_PATH.write_text(
        json.dumps({"date": date, "url": f"posts/{slug}.html",
                    "generated_at": datetime.now(timezone.utc).isoformat()},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")

    print(f"generated US report for {date} ({slug}), body {count} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
