#!/usr/bin/env python3
"""임시 프로브: 쿠키를 챙겨 거래소 채권 자료를 받아 본다.

400 의 본문이 답을 줬다 — 'LOGOUT' 이다. 거래소 통계 API 는 화면을 먼저
들러 세션 쿠키를 받아야 응답한다. 메인 위젯(MDCMAIN00101)은 그게 없어도
되기에 그것만 되고 나머지는 다 400 이었던 것이다.

쿠키만 챙기면 되니 브라우저는 필요 없다. 화면을 한 번 GET 해서 쿠키를
받고, 같은 쿠키로 POST 한다.

bld 는 화면 소스에서 캔 것이라 확실하다.
  장외 채권수익률   dbms/MDC/STAT/standard/MDCSTAT11401
  상장채권 상세검색 dbms/MDC/STAT/standard/MDCSTAT10801
"""
import http.cookiejar
import json
import urllib.parse
import urllib.request
from datetime import date, timedelta

API = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
PAGE = "https://data.krx.co.kr/contents/MDC/STAT/standard/MDCSTAT114.jsp"
HOME = "https://data.krx.co.kr/contents/MDC/MAIN/main/index.cmd"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

d = date.today()
while d.weekday() >= 5:
    d -= timedelta(days=1)
DD = d.strftime("%Y%m%d")
PREV = (d - timedelta(days=1 if d.weekday() else 3)).strftime("%Y%m%d")


def say(s=""):
    print(s, flush=True)


# 쿠키를 담아 두는 통을 만든다. 이게 이번 핵심이다.
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.addheaders = [("User-Agent", UA)]

say("=" * 72)
say("먼저 화면을 들러 쿠키를 받는다")
for url in (HOME, PAGE):
    try:
        with opener.open(url, timeout=25) as r:
            say(f"  [{r.status}] {url[:80]} — {len(r.read())}바이트")
    except Exception as exc:  # noqa: BLE001
        say(f"  실패 {url[:60]} — {type(exc).__name__}: {str(exc)[:100]}")
say(f"  받은 쿠키: {[c.name for c in jar]}")


def post(params):
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Referer": PAGE,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })
    try:
        with opener.open(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


BLD = "dbms/MDC/STAT/standard/MDCSTAT11401"
BASE = {"share": "1", "money": "1", "csvxls_isNo": "false", "locale": "ko_KR"}
TRIES = [
    ("장외수익률 · 오늘", {"bld": BLD, "trdDd": DD, **BASE}),
    ("장외수익률 · 전 영업일", {"bld": BLD, "trdDd": PREV, **BASE}),
    ("장외수익률 · 날짜 없이", {"bld": BLD, **BASE}),
    ("상장채권 상세검색", {"bld": "dbms/MDC/STAT/standard/MDCSTAT10801",
                    "bndTpCd": "", "isuCd": "", **BASE}),
]
for name, params in TRIES:
    say("=" * 72)
    say(f"{name}")
    say(f"  보낸 값: {params}")
    code, raw = post(params)
    say(f"  [{code}] {len(raw)}바이트")
    if code != 200:
        say(f"  {raw[:400]}")
        continue
    try:
        data = json.loads(raw)
    except ValueError:
        say(f"  JSON 아님 — {raw[:300]}")
        continue
    hit = False
    for k, v in data.items():
        if isinstance(v, list) and v:
            say(f"  ✅ {k} 에 {len(v)}줄")
            say(f"     칸 이름: {list(v[0])}")
            for row in v[:5]:
                say("     " + json.dumps(row, ensure_ascii=False)[:300])
            hit = True
            break
    if not hit:
        say(f"  빈손 — 열쇠 {list(data)[:8]} · {raw[:300]}")

say("# 끝")
