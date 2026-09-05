#!/usr/bin/env python3
"""Probe 3차 — 메뉴를 부르는 방법을 disCommon.js 에서 읽어낸다.

2차에서 알아낸 것
  - 리퍼러를 붙이면 /wq/...xml 화면 정의가 열린다(main.xml 142KB).
  - /proframeWeb/XMLSERVICES/ 는 살아 있고, 없는 서비스 이름을 보내도
    200 에 헤더를 되돌려 준다. 그래서 이름을 찍어 맞히는 건 의미가 없다.
  - 메뉴는 disCommon.js 의 callGnb / callSnb / callDisService 가 부른다.

그래서 이번엔 그 함수들을 그대로 찍어 보고, 메뉴 목록을 받아 CMA 화면의
경로와 서비스 아이디를 찾는다. 아무것도 쓰지 않는다.
"""
import re
import sys

import requests

TIMEOUT = 25
BASE = "https://dis.kofia.or.kr"
S = requests.Session()
S.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": BASE + "/websquare/index.jsp?w2xPath=/wq/main/main.xml",
})


def func(js, name):
    """function name( ... ) { ... } 를 중괄호 균형으로 잘라낸다."""
    m = re.search(r"function\s+" + name + r"\s*\([^)]*\)\s*\{", js)
    if not m:
        return None
    i, depth = m.end(), 1
    while i < len(js) and depth:
        depth += (js[i] == "{") - (js[i] == "}")
        i += 1
    return js[m.start():i]


def main():
    print("### 1. disCommon.js 의 메뉴 호출부")
    js = S.get(BASE + "/js/com/disCommon.js", timeout=TIMEOUT).text
    print(f"  {len(js)}자")
    for name in ("callGnb", "callSnb", "callDisService", "callService", "goMenu"):
        body = func(js, name)
        print(f"\n  --- {name} ---")
        print("  " + (body[:1600] if body else "(없음)").replace("\n", "\n  "))

    print("\n### 2. js 안에 박힌 URL 과 서비스 이름")
    urls = sorted(set(re.findall(r"[\"']((?:/|https?://)[A-Za-z0-9_/.\-]+\.(?:do|jsp|json|xml))[\"']", js)))
    print(f"  URL: {urls[:30]}")
    print(f"  pfmSvcName 후보: {sorted(set(re.findall(r'pfmSvcName[^A-Za-z0-9_]+([A-Za-z0-9_]{4,})', js)))[:30]}")

    print("\n### 3. 메뉴를 실제로 받아 본다")
    for url in ("/menu/getGnbMenu.do", "/menu/getSnbMenu.do", "/common/getMenu.do",
                "/websquare/menu.jsp"):
        try:
            r = S.post(BASE + url, data={"divisionId": "MDIS01", "menuId": ""}, timeout=TIMEOUT)
            print(f"  [{url}] {r.status_code} {len(r.text)}자 {r.text[:300]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [{url}] 실패: {exc}")

    print("\n### 4. 프레임 응답을 끝까지 본다 (앞서 잘려서 결과 본문을 못 봤다)")
    body = ('<?xml version="1.0" encoding="utf-8"?><message>'
            '<proframeHeader><pfmAppName>FS-DIS2</pfmAppName>'
            '<pfmSvcName>nonexistent_service_xyz</pfmSvcName><pfmFnName>select</pfmFnName>'
            '</proframeHeader><systemHeader></systemHeader>'
            '<DISCondFuncDTO><tmpV30>0</tmpV30></DISCondFuncDTO></message>')
    r = S.post(BASE + "/proframeWeb/XMLSERVICES/", data=body.encode("utf-8"),
               headers={"Content-Type": "application/xml; charset=UTF-8"}, timeout=TIMEOUT)
    print(f"  {r.status_code} {len(r.text)}자")
    print("  " + r.text[:1500].replace("\n", "\n  "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
