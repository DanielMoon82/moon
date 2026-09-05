#!/usr/bin/env python3
"""Probe 7차 — 전자공시에 CMA 항목이 아예 있는지 못박는다.

6차에서 알아낸 것
  - 화면은 껍데기고 진짜 내용은 /wq/<구역>/inc/<이름>.xml 에 있다.
  - 왼쪽 메뉴는 /wq/com/snb.xml 이다(gnb.xml 은 상단 메뉴였다).
  - DTO 메타 145개 중 이름에 CMA 가 들어간 것이 하나도 없다.
    대신 DISCustDpsUseRateListDTO(증권사별 고객예탁금 이용료율)가 있다.
    전자공시가 CMA 금리를 공시하지 않을 가능성이 크다는 뜻이다.

그래서 이번엔 (1) 전체 메뉴를 열어 CMA 항목이 있는지 못박고,
(2) inc 파일에서 실제 호출 방법을 읽어 (3) 그대로 불러 결과를 본다.
증권사별 금리표가 실제로 나오는지 확인하려는 것이다. 아무것도 쓰지 않는다.
"""
import re
import sys

import requests

TIMEOUT = 30
BASE = "https://dis.kofia.or.kr"
S = requests.Session()
S.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": BASE + "/websquare/index.jsp?w2xPath=/wq/main/main.xml",
})


def get(path):
    try:
        r = S.get(BASE + path, timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        print(f"  [{path}] 실패: {exc}")
        return ""
    print(f"  [{path}] {r.status_code} {len(r.text)}자")
    return r.text if r.status_code == 200 else ""


def main():
    print("### 1. 왼쪽 메뉴 전체 (snb.xml) 에 CMA 가 있는가")
    snb = get("/wq/com/snb.xml")
    if snb:
        hits = re.findall(r"[^<>]{0,40}(?:CMA|종합자산관리|씨엠에이)[^<>]{0,40}", snb, re.I)
        print(f"  CMA 언급: {hits if hits else '(없음)'}")
        names = sorted(set(re.findall(r'label="([^"]{2,30})"', snb)))
        print(f"  메뉴 이름 {len(names)}개: {names[:60]}")
        for m in re.finditer(r"(?:이자율|금리|이용료)", snb):
            s = max(0, m.start() - 200)
            print("    ..." + re.sub(r"\s+", " ", snb[s:m.start() + 120]))

    print("\n### 2. 실제 내용 파일에서 호출 방법을 읽는다")
    inc = get("/wq/compann/inc/DISCustDpsUseRate.xml")
    if inc:
        svcs = sorted(set(re.findall(r"[\"']([A-Za-z0-9_]*(?:SO|SVC)\d*)[\"']", inc)))
        dtos = sorted(set(re.findall(r"(DIS[A-Za-z0-9_]*DTO)", inc)))
        subs = sorted(set(re.findall(r'id="(sub[A-Za-z0-9_]*)"', inc)))
        print(f"  서비스 후보={svcs}\n  DTO={dtos}\n  submission={subs}")
        for key in ("pfmSvcName", "callProframe", "action=", "wframe"):
            for m in list(re.finditer(re.escape(key), inc))[:3]:
                s = max(0, m.start() - 250)
                print(f"    [{key}] ..." + re.sub(r"\s+", " ", inc[s:m.start() + 350]))

    print("\n### 3. 읽어낸 서비스를 실제로 불러 본다")
    for svc in sorted(set(re.findall(r"[\"']([A-Za-z0-9_]*SO)[\"']", inc or ""))):
        body = ('<?xml version="1.0" encoding="utf-8"?><message>'
                '<proframeHeader><pfmAppName>FS-DIS2</pfmAppName>'
                f'<pfmSvcName>{svc}</pfmSvcName><pfmFnName>select</pfmFnName>'
                '</proframeHeader><systemHeader></systemHeader>'
                '<DISCondFuncDTO><tmpV30>0</tmpV30></DISCondFuncDTO></message>')
        try:
            r = S.post(BASE + "/proframeWeb/XMLSERVICES/", data=body.encode("utf-8"),
                       headers={"Content-Type": "application/xml; charset=UTF-8"},
                       timeout=TIMEOUT)
            found = "is not found" not in r.text
            print(f"  [{svc}] {r.status_code} {len(r.text)}자 존재={found}")
            if found:
                print("    " + r.text[:1200].replace("\n", "\n    "))
        except Exception as exc:  # noqa: BLE001
            print(f"  [{svc}] 실패: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
