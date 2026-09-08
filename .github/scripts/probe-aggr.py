#!/usr/bin/env python3
"""임시 프로브: 거래소 채권 자료의 bld 이름을 찾는다.

앞 프로브가 API 모양을 확정해 줬다.
  POST https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd
  바디  bld=dbms/MDC/MAIN/MDCMAIN00101
  답    {"output":[...]}

메뉴 이름과 jsp 이름이 이렇게 짝지어 있었다.
  장외 채권수익률   MDCSTAT114.jsp
  상장채권 상세검색 MDCSTAT108.jsp
  상장채권 발행정보 MDCSTAT109.jsp

bld 는 보통 jsp 이름 뒤에 두 자리가 더 붙는다(MDCMAIN00101 처럼).
브라우저가 필요 없으니 후보를 여럿 던져 보고 답이 오는 것을 고른다.

결과는 로그로 낸다.
"""
import json
import urllib.parse
import urllib.request
from datetime import date, timedelta

URL = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
REF = ("https://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd"
       "?menuId=MDC0201")

# 직전 영업일을 쓴다. 오늘 자료는 장중엔 아직 없을 수 있다.
d = date.today()
while d.weekday() >= 5:
    d -= timedelta(days=1)
TODAY = d.strftime("%Y%m%d")
PREV = (d - timedelta(days=1 if d.weekday() else 3)).strftime("%Y%m%d")

BASE = {"share": "1", "money": "1", "csvxls_isNo": "false"}

CANDIDATES = [
    # 장외 채권수익률 — 처음 찾던 것
    ("장외수익률 11401", {"bld": "dbms/MDC/STAT/standard/MDCSTAT11401",
                        "trdDd": TODAY, **BASE}),
    ("장외수익률 11401(전일)", {"bld": "dbms/MDC/STAT/standard/MDCSTAT11401",
                            "trdDd": PREV, **BASE}),
    ("장외수익률 11402", {"bld": "dbms/MDC/STAT/standard/MDCSTAT11402",
                        "trdDd": TODAY, **BASE}),
    ("장외수익률 114", {"bld": "dbms/MDC/STAT/standard/MDCSTAT114",
                      "trdDd": TODAY, **BASE}),
    # 상장채권 상세검색
    ("상장채권 10801", {"bld": "dbms/MDC/STAT/standard/MDCSTAT10801",
                      "trdDd": TODAY, **BASE}),
    ("상장채권 10802", {"bld": "dbms/MDC/STAT/standard/MDCSTAT10802",
                      "trdDd": TODAY, **BASE}),
    # 상장채권 발행정보
    ("발행정보 10901", {"bld": "dbms/MDC/STAT/standard/MDCSTAT10901",
                      "trdDd": TODAY, **BASE}),
    # 채권 전종목 시세 — 메뉴에 '채권 > 종목시세' 가 있었다
    ("채권 전종목시세 11001", {"bld": "dbms/MDC/STAT/standard/MDCSTAT11001",
                          "trdDd": TODAY, **BASE}),
    ("채권 전종목시세 11101", {"bld": "dbms/MDC/STAT/standard/MDCSTAT11101",
                          "trdDd": TODAY, **BASE}),
    ("채권 전종목시세 11201", {"bld": "dbms/MDC/STAT/standard/MDCSTAT11201",
                          "trdDd": TODAY, **BASE}),
    ("채권 전종목시세 11301", {"bld": "dbms/MDC/STAT/standard/MDCSTAT11301",
                          "trdDd": TODAY, **BASE}),
]


def ask(params):
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
        "Referer": REF,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", "replace")


print(f"# 기준일 {TODAY} · 그 전 영업일 {PREV}", flush=True)
for name, params in CANDIDATES:
    print("=" * 72, flush=True)
    print(f"{name}  bld={params['bld']}", flush=True)
    try:
        raw = ask(params)
        try:
            data = json.loads(raw)
        except ValueError:
            print(f"  JSON 아님 — {raw[:300]}", flush=True)
            continue
        # 자료가 담긴 열쇠를 찾는다. 거래소는 output 말고 다른 이름도 쓴다.
        rows = None
        for k, v in data.items():
            if isinstance(v, list) and v:
                rows = (k, v)
                break
        if not rows:
            print(f"  빈손 — 열쇠 {list(data)[:8]} · {raw[:250]}", flush=True)
            continue
        k, v = rows
        print(f"  ✅ {k} 에 {len(v)}줄", flush=True)
        print(f"     칸 이름: {list(v[0])}", flush=True)
        for row in v[:4]:
            print("     " + json.dumps(row, ensure_ascii=False)[:300], flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"  실패 {type(exc).__name__}: {str(exc)[:150]}", flush=True)

print("# 끝", flush=True)
