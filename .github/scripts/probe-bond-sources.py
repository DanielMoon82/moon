#!/usr/bin/env python3
"""Probe round 2 — read the real ECOS item codes for 시장금리(일별).

Round 1 confirmed ECOS answers with real data (국고채(1년) 3.458 on 2026-09-01)
and that Naver's daily-quote pages parse. What is still unknown is the exact
item code for each maturity/grade, and guessing those would silently fetch the
wrong series. This asks ECOS for the list. Writes nothing.
"""
import json
import sys

import requests

BASE = "https://ecos.bok.or.kr/api"
KEY = "sample"
TIMEOUT = 20


def main():
    # 817Y002 = 1.3.2.1 시장금리(일별)
    url = f"{BASE}/StatisticItemList/{KEY}/json/kr/1/100/817Y002"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        print(f"[{r.status_code}] {url}")
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        print(f"실패: {exc}")
        return 1

    rows = (data.get("StatisticItemList") or {}).get("row") or []
    if not rows:
        print(f"목록 없음: {json.dumps(data, ensure_ascii=False)[:500]}")
        return 1

    print(f"항목 {len(rows)}개")
    for row in rows:
        print(f"  {row.get('ITEM_CODE'):<12} {row.get('ITEM_NAME'):<28} "
              f"주기={row.get('CYCLE')} 시작={row.get('START_TIME')} 끝={row.get('END_TIME')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
