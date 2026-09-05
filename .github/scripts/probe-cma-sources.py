#!/usr/bin/env python3
"""Probe: 증권사별 CMA 금리를 어디서 받아올 수 있는지 확인한다.

아무것도 쓰지 않는다. 로그만 남긴다. 응답을 직접 보고 파서를 쓰기 위한 것이다.
금융투자협회 전자공시(dis.kofia.or.kr)가 CMA 수익률을 회사별로 모아 공시한다.
WebSquare 로 만든 사이트라 화면 정의 XML 안에 실제 서비스 이름이 들어 있다.
그래서 서비스 이름을 찍지 않고 화면 정의에서 찾아낸다.
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


def show(tag, resp, body=None):
    text = body if body is not None else resp.text
    print(f"  [{tag}] {resp.status_code} {resp.headers.get('content-type','?')} "
          f"{len(text)}자")
    return text


def step_root():
    print("### 1. dis.kofia.or.kr 루트에서 화면 경로 수집")
    try:
        r = requests.get(BASE + "/websquare/index.jsp", headers=UA, timeout=TIMEOUT)
        html = show("root", r)
    except Exception as exc:  # noqa: BLE001
        print(f"  실패: {exc}")
        return []
    paths = sorted(set(re.findall(r"[\"'](/wq/[A-Za-z0-9_/]+\.xml)[\"']", html)))
    print(f"  화면 경로 {len(paths)}개: {paths[:15]}")
    return paths


CANDIDATE_XML = [
    # 메뉴에서 못 찾을 때를 대비한 후보. 맞는지는 응답을 보고 판단한다.
    "/wq/fundann/DISFundCMAList.xml",
    "/wq/com/finpro/DISFinProCMA.xml",
    "/wq/finpro/DISFinProCMAList.xml",
    "/wq/cominfo/DISCmaList.xml",
]


def step_screens(paths):
    print("\n### 2. CMA 가 들어간 화면 정의에서 서비스 이름 찾기")
    hits = [p for p in paths if "cma" in p.lower()] or CANDIDATE_XML
    print(f"  볼 화면: {hits}")
    found = []
    for p in hits:
        try:
            r = requests.get(BASE + p, headers=UA, timeout=TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{p}] 실패: {exc}")
            continue
        body = show(p, r)
        if r.status_code != 200 or len(body) < 200:
            continue
        svc = sorted(set(re.findall(r"pfmSvcName[\"'>\s:=]+([A-Za-z0-9_]+)", body)))
        app = sorted(set(re.findall(r"pfmAppName[\"'>\s:=]+([A-Za-z0-9_\-]+)", body)))
        dto = sorted(set(re.findall(r"<([A-Za-z]*(?:DTO|Dto)[A-Za-z]*)", body)))
        print(f"    pfmAppName={app} pfmSvcName={svc}")
        print(f"    DTO={dto[:10]}")
        for s in svc:
            found.append((p, app[0] if app else "FS-DIS2", s))
        if not svc:
            print(f"    앞부분: {body[:400]!r}")
    return found


PROFRAME = BASE + "/proframeWeb/XMLSERVICES/"
ENVELOPE = """<?xml version="1.0" encoding="utf-8"?>
<message>
  <proframeHeader>
    <pfmAppName>{app}</pfmAppName>
    <pfmSvcName>{svc}</pfmSvcName>
    <pfmFnName>select</pfmFnName>
  </proframeHeader>
  <systemHeader></systemHeader>
  <DISCondFuncDTO><tmpV30>0</tmpV30><tmpV1></tmpV1></DISCondFuncDTO>
</message>"""


def step_call(found):
    print("\n### 3. 찾은 서비스를 실제로 불러 본다")
    if not found:
        print("  부를 서비스가 없다")
        return
    seen = set()
    for path, app, svc in found:
        if svc in seen:
            continue
        seen.add(svc)
        try:
            r = requests.post(
                PROFRAME, data=ENVELOPE.format(app=app, svc=svc).encode("utf-8"),
                headers={**UA, "Content-Type": "application/xml; charset=UTF-8"},
                timeout=TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{svc}] 실패: {exc}")
            continue
        body = show(svc, r)
        print(f"    {body[:700]!r}")


def step_freesis():
    print("\n### 4. 협회 종합통계(freesis) 도 되는지")
    for url in ("https://freesis.kofia.or.kr/",
                "https://freesis.kofia.or.kr/meta/getMetaDataList.do"):
        try:
            r = requests.get(url, headers=UA, timeout=TIMEOUT)
            show(url, r)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{url}] 실패: {exc}")


def main():
    paths = step_root()
    found = step_screens(paths)
    step_call(found)
    step_freesis()
    return 0


if __name__ == "__main__":
    sys.exit(main())
