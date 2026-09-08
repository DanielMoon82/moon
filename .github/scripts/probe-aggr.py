#!/usr/bin/env python3
"""임시 프로브: 거래소가 400 을 주며 뭐라고 하는지 읽는다.

앞 프로브가 두 가지를 확정했다.
  · 그냥 POST 로도 된다. 쿠키가 필요 없다(MDCMAIN00101 로 확인).
  · bld 이름은 내가 맞게 찍었다. 화면 소스에 그대로 박혀 있었다.
      장외 채권수익률   MDCSTAT11401(전종목) · MDCSTAT11402(개별추이)
      상장채권 상세검색 MDCSTAT10801

그러면 400 은 딸려 보낼 값이 빠져서다. 그런데 나는 400 의 본문을 안 읽고
버렸다. 거기 무엇이 빠졌는지 적혀 있을 텐데 그걸 놓쳤다.

이번엔 두 가지를 한다.
  · 400 이 와도 본문을 읽어 그대로 찍는다.
  · 화면의 입력칸 이름을 통째로 훑는다. 보낼 값 이름이 거기 있다.
"""
import json
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta

API = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

d = date.today()
while d.weekday() >= 5:
    d -= timedelta(days=1)
DD = d.strftime("%Y%m%d")
PREV = (d - timedelta(days=1 if d.weekday() else 3)).strftime("%Y%m%d")


def say(s=""):
    print(s, flush=True)


def post(params, ref="https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd"):
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(API, data=body, headers={
        "User-Agent": UA, "Referer": ref,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        # 여기가 중요하다. 400 의 본문에 뭐가 빠졌는지 적혀 있다.
        return e.code, e.read().decode("utf-8", "replace")


# ── 1. 화면의 입력칸 이름을 훑는다
say("=" * 72)
say("장외 채권수익률 화면의 입력칸 이름")
try:
    req = urllib.request.Request(
        "https://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT114.jsp",
        headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        html = r.read().decode("utf-8", "replace")
    names = sorted(set(re.findall(r'name=["\']([A-Za-z_][A-Za-z0-9_]{2,30})["\']', html)))
    ids = sorted(set(re.findall(r'id=["\']([A-Za-z_][A-Za-z0-9_]{2,30})["\']', html)))
    say(f"  name= {names[:40]}")
    say(f"  id=   {ids[:40]}")
    for m in re.findall(r'\{[^{}]*bld[^{}]{0,400}\}', html)[:4]:
        say(f"  덩어리: {m[:400]}")
except Exception as exc:  # noqa: BLE001
    say(f"  실패 {type(exc).__name__}: {str(exc)[:140]}")

# ── 2. 400 이 뭐라고 하는지 읽는다
BLD = "dbms/MDC/STAT/standard/MDCSTAT11401"
TRIES = [
    ("맨 이름만", {"bld": BLD}),
    ("+ 조회일자", {"bld": BLD, "trdDd": DD}),
    ("+ locale", {"bld": BLD, "trdDd": DD, "locale": "ko_KR"}),
    ("+ 전종목 구분", {"bld": BLD, "trdDd": DD, "locale": "ko_KR",
                   "inqCondTpCd": "1", "share": "1", "money": "1",
                   "csvxls_isNo": "false"}),
    ("basDd 로", {"bld": BLD, "basDd": DD, "locale": "ko_KR"}),
    ("전일자로", {"bld": BLD, "trdDd": PREV, "locale": "ko_KR"}),
    ("상장채권 10801", {"bld": "dbms/MDC/STAT/standard/MDCSTAT10801",
                    "locale": "ko_KR", "share": "1", "money": "1",
                    "csvxls_isNo": "false"}),
]
for name, params in TRIES:
    say("=" * 72)
    say(f"{name}  {params}")
    code, raw = post(params, "https://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT114.jsp")
    say(f"  [{code}] {len(raw)}바이트")
    say(f"  {raw[:700]}")
    if code == 200:
        try:
            data = json.loads(raw)
            for k, v in data.items():
                if isinstance(v, list) and v:
                    say(f"  ✅ {k} 에 {len(v)}줄 · 칸 {list(v[0])}")
                    for row in v[:3]:
                        say("     " + json.dumps(row, ensure_ascii=False)[:280])
                    break
        except ValueError:
            pass

say("# 끝")
