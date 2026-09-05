#!/usr/bin/env python3
"""Probe round 3 — ECOS item codes (10 at a time) + Naver's available series.

Round 2 found the sample key caps a call at 10 rows, so the item list has to be
paged. Also lists which IRR codes Naver actually serves, since that is the
no-key fallback. Writes nothing.
"""
import re
import sys

import requests

TIMEOUT = 20
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; moon-bond-bot/1.0)"}


def ecos_items():
    print("### ECOS 817Y002 (시장금리 일별) 항목 목록")
    seen = 0
    for start in range(1, 101, 10):
        url = (f"https://ecos.bok.or.kr/api/StatisticItemList/sample/json/kr/"
               f"{start}/{start + 9}/817Y002")
        try:
            data = requests.get(url, timeout=TIMEOUT).json()
        except Exception as exc:  # noqa: BLE001
            print(f"  [실패] {start}~: {exc}")
            break
        rows = (data.get("StatisticItemList") or {}).get("row") or []
        if not rows:
            msg = (data.get("RESULT") or {}).get("MESSAGE", "")
            if msg:
                print(f"  ({start}~ 끝: {msg[:60]})")
            break
        for r in rows:
            seen += 1
            print(f"  {r.get('ITEM_CODE'):<12} {r.get('ITEM_NAME')}")
    print(f"  총 {seen}개\n")


def naver_codes():
    """시장지표 페이지에 걸린 금리 링크에서 실제 코드를 뽑는다."""
    print("### 네이버 시장지표에 실제로 있는 금리 코드")
    try:
        r = requests.get("https://finance.naver.com/marketindex/", headers=HEADERS, timeout=TIMEOUT)
        r.encoding = "euc-kr"
        html = r.text
    except Exception as exc:  # noqa: BLE001
        print(f"  실패: {exc}")
        return
    hits = sorted(set(re.findall(r"marketindexCd=(IRR_[A-Z0-9_]+)", html)))
    print(f"  {hits}")
    # 각 코드의 최근 한 줄이 실제로 읽히는지 확인
    for code in hits[:8]:
        try:
            q = requests.get(
                "https://finance.naver.com/marketindex/interestDailyQuote.naver",
                params={"marketindexCd": code}, headers=HEADERS, timeout=TIMEOUT)
            q.encoding = "euc-kr"
            rows = re.findall(r"<tr[^>]*>(.*?)</tr>", q.text, re.S)
            for row in rows:
                cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
                         for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
                if len(cells) >= 2 and re.match(r"\d{4}\.\d{2}\.\d{2}", cells[0]):
                    print(f"    {code:<16} 최근 {cells[:4]}")
                    break
        except Exception as exc:  # noqa: BLE001
            print(f"    {code}: 실패 {exc}")


def main():
    ecos_items()
    naver_codes()
    return 0


if __name__ == "__main__":
    sys.exit(main())
