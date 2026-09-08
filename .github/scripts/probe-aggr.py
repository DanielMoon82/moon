#!/usr/bin/env python3
"""임시 프로브(마지막): menuId 를 캐서 제대로 된 순서로 부른다.

쿠키(JSESSIONID)를 받아도 여전히 LOGOUT 이다. 세션만으로는 부족하고
메뉴 경로를 거쳐야 그 화면이 세션에 등록되는 구조로 보인다.
거래소 메인에 이런 글이 있었다(잘려 있었다).
  gotoMenu('/contents/MDC/STAT/standard/MDCSTAT114.jsp/contents/MDC/MDI/
            mdiLoader/index.cmd?menuId=MD...')

그 menuId 만 있으면 순서가 완성된다.
  1. 메인을 들러 쿠키를 받는다
  2. mdiLoader/index.cmd?menuId=... 를 들러 메뉴를 연다
  3. 그다음 getJsonData 를 부른다

한 번에 끝내려고 캐기와 부르기를 같은 실행에 묶었다.
"""
import http.cookiejar
import json
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta

BASE = "https://data.krx.co.kr"
API = f"{BASE}/comm/bldAttendant/getJsonData.cmd"
HOME = f"{BASE}/contents/MDC/MAIN/main/index.cmd"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

d = date.today()
while d.weekday() >= 5:
    d -= timedelta(days=1)
DD = d.strftime("%Y%m%d")
PREV = (d - timedelta(days=1 if d.weekday() else 3)).strftime("%Y%m%d")


def say(s=""):
    print(s, flush=True)


jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.addheaders = [("User-Agent", UA)]

# ── 1. 메인에서 menuId 를 캔다
say("=" * 72)
say("메인에서 menuId 캐기")
html = ""
try:
    with opener.open(HOME, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    say(f"  메인 {len(html)}바이트 · 쿠키 {[c.name for c in jar]}")
except Exception as exc:  # noqa: BLE001
    say(f"  실패 {type(exc).__name__}: {str(exc)[:120]}")

# MDCSTAT 이름 옆에 붙은 menuId 를 짝지어 뽑는다.
pairs = re.findall(r"(MDCSTAT\d{3})\.jsp[^']*?menuId=([A-Za-z0-9]+)", html)
say(f"  찾은 짝 {len(pairs)}개")
for stat, menu in pairs[:20]:
    say(f"    {stat} → menuId={menu}")
want = {s: m for s, m in pairs}
say(f"  장외 채권수익률(MDCSTAT114) menuId = {want.get('MDCSTAT114', '(못 찾음)')}")
say(f"  상장채권 상세검색(MDCSTAT108) menuId = {want.get('MDCSTAT108', '(못 찾음)')}")

# 못 찾으면 menuId 만이라도 통째로 훑어 본다.
if not pairs:
    ids = sorted(set(re.findall(r"menuId=([A-Za-z0-9]{8,20})", html)))
    say(f"  화면에 있는 menuId {len(ids)}개: {ids[:30]}")


def post(params, ref):
    body = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Referer": ref,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    })
    try:
        with opener.open(req, timeout=25) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


# ── 2. 메뉴를 열고 나서 부른다
for stat, bld in (("MDCSTAT114", "dbms/MDC/STAT/standard/MDCSTAT11401"),
                  ("MDCSTAT108", "dbms/MDC/STAT/standard/MDCSTAT10801")):
    say("=" * 72)
    menu = want.get(stat)
    say(f"{stat}  bld={bld}  menuId={menu or '(없음)'}")
    ref = HOME
    if menu:
        loader = f"{BASE}/contents/MDC/MDI/mdiLoader/index.cmd?menuId={menu}"
        try:
            with opener.open(loader, timeout=30) as r:
                say(f"  메뉴 열기 [{r.status}] {len(r.read())}바이트")
            ref = loader
        except Exception as exc:  # noqa: BLE001
            say(f"  메뉴 열기 실패 {type(exc).__name__}: {str(exc)[:100]}")

    for label, extra in (("오늘", {"trdDd": DD}),
                         ("전 영업일", {"trdDd": PREV})):
        params = {"bld": bld, "share": "1", "money": "1",
                  "csvxls_isNo": "false", "locale": "ko_KR", **extra}
        code, raw = post(params, ref)
        say(f"  [{code}] {label} — {len(raw)}바이트")
        if code != 200:
            say(f"     {raw[:200]}")
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            say(f"     JSON 아님 {raw[:200]}")
            continue
        for k, v in data.items():
            if isinstance(v, list) and v:
                say(f"     ✅ {k} 에 {len(v)}줄 · 칸 {list(v[0])}")
                for row in v[:5]:
                    say("        " + json.dumps(row, ensure_ascii=False)[:300])
                break
        else:
            say(f"     빈손 — {list(data)[:6]} {raw[:200]}")

say("# 끝")
