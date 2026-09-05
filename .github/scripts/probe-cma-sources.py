#!/usr/bin/env python3
"""Probe 2차 — 금융투자협회 전자공시의 실제 진입 경로를 따라간다.

1차에서 알아낸 것
  - dis.kofia.or.kr 루트는 150자짜리 껍데기다. 링크가 없어 긁을 게 없다.
  - 내가 찍은 /wq/...xml 경로는 전부 사이트의 오류 페이지(1580자)를 돌려준다.
    경로가 틀렸거나, 세션·리퍼러 없이 직접 받으면 막히는 것이다.

그래서 이번엔 껍데기 본문을 통째로 찍어 어디로 가라는지 보고, 세션을 유지한
채 리퍼러를 붙여 따라간다. 아무것도 쓰지 않는다.
"""
import re
import sys

import requests

TIMEOUT = 25
UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}
BASE = "https://dis.kofia.or.kr"
S = requests.Session()
S.headers.update(UA)


def dump(tag, url, limit=1200, **kw):
    try:
        r = S.get(url, timeout=TIMEOUT, **kw)
    except Exception as exc:  # noqa: BLE001
        print(f"  [{tag}] 실패: {exc}")
        return None
    body = r.text
    print(f"  [{tag}] {r.status_code} {r.headers.get('content-type','?')} {len(body)}자 -> {r.url}")
    print(f"      {body[:limit]!r}")
    return body


def main():
    print("### 1. 껍데기 본문을 통째로 본다")
    root = dump("root", BASE + "/")
    dump("index.jsp", BASE + "/websquare/index.jsp")

    print("\n### 2. 껍데기가 가리키는 곳을 따라간다")
    nexts = set()
    for body in (root or "",):
        nexts |= set(re.findall(r"""(?:location(?:\.href)?\s*=|url=|action=|src=)\s*["']?([^"'\s>;]+)""", body, re.I))
    print(f"  후보: {sorted(nexts)}")
    for n in sorted(nexts)[:6]:
        url = n if n.startswith("http") else BASE + ("" if n.startswith("/") else "/") + n
        dump(n, url, limit=1500)

    print("\n### 3. 메인 화면을 세션·리퍼러를 붙여 받아 본다")
    entry = BASE + "/websquare/index.jsp?w2xPath=/wq/main/main.xml"
    main_html = dump("main.jsp", entry, limit=1500)
    ref = {"Referer": entry}
    for p in ("/wq/main/main.xml", "/wq/com/main.xml", "/websquare/websquare.html"):
        dump("ref:" + p, BASE + p, limit=800, headers=ref)

    print("\n### 4. 화면 경로가 본문 어디엔가 있는지 (자바스크립트 포함)")
    seen = set(re.findall(r"(/wq/[A-Za-z0-9_/.\-]+\.xml)", (main_html or "") + (root or "")))
    print(f"  본문에서 찾은 경로: {sorted(seen)[:20]}")
    for js in re.findall(r'src=["\']([^"\']+\.js)["\']', (main_html or ""))[:6]:
        url = js if js.startswith("http") else BASE + ("" if js.startswith("/") else "/") + js
        body = dump("js:" + js, url, limit=300, headers=ref)
        if body:
            hits = sorted(set(re.findall(r"(/wq/[A-Za-z0-9_/.\-]+\.xml)", body)))
            cma = [h for h in hits if "cma" in h.lower()]
            print(f"      경로 {len(hits)}개, CMA 관련 {cma}")

    print("\n### 5. 데이터 엔드포인트가 살아 있는지 (오류 모양으로 판단)")
    for svc in ("DISCmaRtSrchSO", "DISFundCMAList", "nonexistent_service_xyz"):
        try:
            r = S.post(BASE + "/proframeWeb/XMLSERVICES/",
                       data=('<?xml version="1.0" encoding="utf-8"?><message>'
                             '<proframeHeader><pfmAppName>FS-DIS2</pfmAppName>'
                             f'<pfmSvcName>{svc}</pfmSvcName><pfmFnName>select</pfmFnName>'
                             '</proframeHeader><systemHeader></systemHeader>'
                             '<DISCondFuncDTO><tmpV30>0</tmpV30></DISCondFuncDTO></message>'
                             ).encode("utf-8"),
                       headers={"Content-Type": "application/xml; charset=UTF-8"},
                       timeout=TIMEOUT)
            print(f"  [{svc}] {r.status_code} {len(r.text)}자 {r.text[:300]!r}")
        except Exception as exc:  # noqa: BLE001
            print(f"  [{svc}] 실패: {exc}")

    print("\n### 6. 협회 종합통계 껍데기")
    dump("freesis", "https://freesis.kofia.or.kr/", limit=900)
    return 0


if __name__ == "__main__":
    sys.exit(main())
