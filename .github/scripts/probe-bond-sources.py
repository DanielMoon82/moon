#!/usr/bin/env python3
"""Probe candidate sources for Korean benchmark bond yields.

Same reason as the portal probe: no documented public feed, and this sandbox
has no outbound network. Fetch the candidates from a runner and print what
comes back, so the parser is written against the real response instead of a
guess. Writes nothing. Delete once fetch-bonds.py is settled.

Looking for: 국고채 만기별, 회사채 등급별(AA-/BBB-), CD·CP 등 단기물.
"""
import re
import sys

import requests

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
}
TIMEOUT = 20


def txt(s, n=600):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))[:n]


def probe_naver_marketindex():
    """네이버 금융 시장지표 — 국내 금리 묶음이 한 페이지에 있다."""
    print("\n### 네이버 시장지표 (국내금리)")
    url = "https://finance.naver.com/marketindex/"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.encoding = "euc-kr"
        html = r.text
    except Exception as exc:  # noqa: BLE001
        print(f"  실패: {exc}")
        return
    print(f"  [{r.status_code}] {len(html)}자")
    i = html.find("국내금리")
    if i == -1:
        i = html.find("interest")
    if i != -1:
        print(f"  '국내금리' 주변 원문: {html[i - 200:i + 2200]!r}")
    else:
        print("  국내금리 영역을 못 찾음")


def probe_naver_daily(code, label):
    """만기별 일별 시세 페이지."""
    url = f"https://finance.naver.com/marketindex/interestDailyQuote.naver?marketindexCd={code}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.encoding = "euc-kr"
        html = r.text
    except Exception as exc:  # noqa: BLE001
        print(f"  [실패] {label} ({code}): {exc}")
        return
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)[:4]
    print(f"  [{r.status_code}] {label} ({code}) {len(html)}자")
    for row in rows:
        cells = [txt(c, 40).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if cells:
            print(f"      {cells}")


def probe_kofia():
    """금융투자협회 채권정보센터 — 최종호가수익률의 원본 기관."""
    print("\n### 금융투자협회 채권정보센터")
    for url in ("https://www.kofiabond.or.kr/index.html",
                "https://www.kofiabond.or.kr/websquare/websquare.html?w2xPath=/wq/main/main.xml"):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            print(f"  [{r.status_code}] {url}  {len(r.text)}자")
            print(f"    본문: {txt(r.text, 300)!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [실패] {url}: {exc}")


def probe_ecos():
    """한국은행 ECOS. 키가 필요하지만 샘플키로 형식만 확인해 본다."""
    print("\n### 한국은행 ECOS (키 필요 여부 확인)")
    url = ("https://ecos.bok.or.kr/api/StatisticSearch/sample/json/kr/1/5/"
           "817Y002/D/20260901/20260905/010190000")
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        print(f"  [{r.status_code}] {r.text[:400]!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"  [실패] {exc}")


def main():
    probe_naver_marketindex()
    print("\n### 네이버 만기별 일별 시세")
    for code, label in (("IRR_GOVT03Y", "국고채 3년"),
                        ("IRR_GOVT05Y", "국고채 5년"),
                        ("IRR_CORP03Y", "회사채 3년 AA-"),
                        ("IRR_CD91", "CD 91일"),
                        ("IRR_CALL", "콜금리")):
        probe_naver_daily(code, label)
    probe_kofia()
    probe_ecos()
    return 0


if __name__ == "__main__":
    sys.exit(main())
