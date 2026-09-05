#!/usr/bin/env python3
"""Fetch Korean benchmark bond yields into data/bonds.json.

무엇을 담는가
  국고채 만기별, 회사채 등급별, CD·CP 등 단기물의 '시장 기준금리'다.
  증권사별 발행 회사채 내역은 공시로 흩어져 있어 매일 받아올 공개 피드가
  없다. 채권 사이트들이 쓰는 것도 아래와 같은 시장 기준금리다.

어디서 받는가 (러너에서 직접 확인한 결과)
  한국은행 ECOS 통계표 817Y002 '시장금리(일별)'.
  - 항목 코드는 하드코딩하지 않고 이름으로 찾는다. 코드를 박아 두면
    한국은행이 항목을 바꿨을 때 엉뚱한 계열을 조용히 가져오게 된다.
  - 키 없이 쓰는 sample 키는 한 번에 10건까지만 응답한다(확인함).
    ECOS_API_KEY 를 넣으면 그 제한이 풀린다. 무료로 바로 발급된다.
  실패하면 네이버 금융 일별 시세로 핵심 4종만이라도 채운다(키 불필요).

실패해도 기존 파일은 남긴다. 조금 지난 금리가 빈 표보다 낫다.
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_JSON = ROOT / "data" / "bonds.json"

KST = timezone(timedelta(hours=9))
TIMEOUT = 20
ECOS = "https://ecos.bok.or.kr/api"
STAT = "817Y002"          # 1.3.2.1 시장금리(일별)
KEY = os.environ.get("ECOS_API_KEY", "").strip() or "sample"
SAMPLE = KEY == "sample"
ROWS = 10 if SAMPLE else 40   # sample 키는 한 번에 10건까지

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; moon-bond-bot/1.0)"}

# 화면에 이 순서로 나간다. 이름은 ECOS 항목명과 정확히 맞춘다.
GROUPS = [
    ("국고채", [
        ("국고채(1년)", "1년"),
        ("국고채(2년)", "2년"),
        ("국고채(3년)", "3년"),
        ("국고채(10년)", "10년"),
        ("국고채(20년)", "20년"),
        ("국고채(30년)", "30년"),
    ]),
    ("회사채", [
        ("회사채(3년, AA-)", "AA- 3년"),
        ("회사채(3년, BBB-)", "BBB- 3년"),
        ("산금채(1년)", "산금채 1년"),
    ]),
    ("단기", [
        ("CD(91일)", "CD 91일"),
        ("CP(91일)", "CP 91일"),
        ("통안증권(91일)", "통안 91일"),
        ("콜금리(1일, 은행증권금융차입)", "콜 1일"),
    ]),
]

# ECOS 가 죽었을 때 최소한 이만큼은 채운다. 키가 필요 없다.
NAVER_FALLBACK = [
    ("국고채", "IRR_GOVT03Y", "3년"),
    ("회사채", "IRR_CORP03Y", "AA- 3년"),
    ("단기", "IRR_CD91", "CD 91일"),
    ("단기", "IRR_CALL", "콜 1일"),
]


def ecos_item_codes():
    """항목명 -> 코드. sample 키 제한 때문에 10개씩 끊어 받는다."""
    codes = {}
    for start in range(1, 121, 10):
        url = f"{ECOS}/StatisticItemList/{KEY}/json/kr/{start}/{start + ROWS - 1}/{STAT}"
        try:
            rows = (requests.get(url, headers=HEADERS, timeout=TIMEOUT).json()
                    .get("StatisticItemList") or {}).get("row") or []
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"항목 목록 조회 실패: {exc}") from exc
        if not rows:
            break
        for r in rows:
            name, code = r.get("ITEM_NAME"), r.get("ITEM_CODE")
            if name and code:
                codes[name.strip()] = code
    if not codes:
        raise ValueError("항목 목록이 비어 있음")
    return codes


def ecos_series(code):
    """최근 값들을 [(YYYY-MM-DD, 금리)] 오름차순으로."""
    end = datetime.now(KST)
    start = end - timedelta(days=45)
    url = (f"{ECOS}/StatisticSearch/{KEY}/json/kr/1/{ROWS}/{STAT}/D/"
           f"{start:%Y%m%d}/{end:%Y%m%d}/{code}")
    payload = requests.get(url, headers=HEADERS, timeout=TIMEOUT).json()
    rows = (payload.get("StatisticSearch") or {}).get("row") or []
    if not rows:
        msg = (payload.get("RESULT") or {}).get("MESSAGE", "")
        raise ValueError(msg[:80] or "값 없음")
    out = []
    for r in rows:
        t, v = r.get("TIME"), r.get("DATA_VALUE")
        if not t or v in (None, "", "-"):
            continue
        try:
            out.append((f"{t[:4]}-{t[4:6]}-{t[6:8]}", round(float(v), 3)))
        except ValueError:
            continue
    out.sort()
    if not out:
        raise ValueError("숫자로 읽을 값이 없음")
    return out


def naver_series(code):
    """네이버 일별 시세. ECOS 가 안 될 때만 쓴다."""
    r = requests.get("https://finance.naver.com/marketindex/interestDailyQuote.naver",
                     params={"marketindexCd": code}, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    r.encoding = "euc-kr"
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S):
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) >= 2 and re.match(r"^\d{4}\.\d{2}\.\d{2}$", cells[0]):
            try:
                out.append((cells[0].replace(".", "-"), round(float(cells[1]), 3)))
            except ValueError:
                continue
    out.sort()
    if not out:
        raise ValueError("표를 읽지 못함")
    return out


def entry(label, series):
    last_date, last = series[-1]
    prev = series[-2][1] if len(series) > 1 else None
    item = {"label": label, "value": last, "date": last_date,
            "history": [v for _, v in series[-10:]]}
    if prev is not None:
        # 금리는 bp 로 읽는 게 관행이라 변화폭도 그렇게 쓸 수 있게 둘 다 담는다.
        item["change"] = round(last - prev, 3)
        item["change_bp"] = round((last - prev) * 100)
    return item


def main():
    print(f"ECOS 키: {'사용자 키' if not SAMPLE else 'sample (한 번에 10건 제한)'}")
    groups, failures, source = [], [], None

    try:
        codes = ecos_item_codes()
        print(f"항목 코드 {len(codes)}개 확보")
        for gname, items in GROUPS:
            got = []
            for ecos_name, label in items:
                code = codes.get(ecos_name)
                if not code:
                    failures.append(f"{ecos_name}: 항목명을 찾지 못함")
                    continue
                try:
                    got.append(entry(label, ecos_series(code)))
                    print(f"  [ok] {gname} {label}: {got[-1]['value']} ({got[-1]['date']})")
                except Exception as exc:  # noqa: BLE001
                    failures.append(f"{ecos_name}: {exc}")
            if got:
                groups.append({"name": gname, "items": got})
        if groups:
            source = "한국은행 ECOS"
    except Exception as exc:  # noqa: BLE001
        failures.append(f"ECOS: {exc}")

    if not groups:
        print("ECOS 실패 — 네이버로 대체", file=sys.stderr)
        by_group = {}
        for gname, code, label in NAVER_FALLBACK:
            try:
                by_group.setdefault(gname, []).append(entry(label, naver_series(code)))
                print(f"  [ok] {gname} {label} <- 네이버")
            except Exception as exc:  # noqa: BLE001
                failures.append(f"네이버 {code}: {exc}")
        groups = [{"name": g, "items": v} for g, v in by_group.items()]
        if groups:
            source = "네이버 금융"

    if failures:
        print("  [warn] " + " | ".join(failures[:8]), file=sys.stderr)

    if not groups:
        print("모든 소스 실패 — 기존 파일 유지", file=sys.stderr)
        return 0

    as_of = max(i["date"] for g in groups for i in g["items"])
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(
        json.dumps({
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "as_of": as_of,
            "source": source,
            "groups": groups,
        }, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    n = sum(len(g["items"]) for g in groups)
    print(f"{OUT_JSON.relative_to(ROOT)} 기록 — {as_of} 기준 {n}개 ({source})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
