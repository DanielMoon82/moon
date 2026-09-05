#!/usr/bin/env python3
"""Probe 6차 — 메타 파일에서 CMA 서비스와 DTO 를 찾는다.

5차에서 알아낸 것 (4차의 판단을 뒤집는다)
  - /wq/compann/*.xml 은 사실 정상으로 열린다(200 application/xml). 다만
    1,700자짜리 껍데기고 내용은 자바스크립트가 채운다. 4차에서 '튕겼다'고
    본 건 내 걸러내기가 잘못된 것이었다.
  - gnb.xml(27KB)에도 CMA 는 없고 경로도 2개뿐이다. 메뉴는 /js/menu/gnb.js 와
    /js/menu/service.js 가 만든다.
  - 화면들이 공통으로 부르는 파일이 보인다:
      /js/com/callProframe.js   프레임 호출을 만드는 곳
      /js/meta/disMetaDtoInfo.js, /js/meta/disMeta.js   DTO 메타 정보
      /js/menu/service.js       메뉴와 서비스 대응
    서비스 이름과 DTO 모양이 여기 적혀 있을 것이다.

아무것도 쓰지 않는다.
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

FILES = [
    "/js/menu/service.js",
    "/js/menu/gnb.js",
    "/js/meta/disMeta.js",
    "/js/meta/disMetaDtoInfo.js",
    "/js/com/callProframe.js",
]


def get(path):
    try:
        r = S.get(BASE + path, timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        print(f"  [{path}] 실패: {exc}")
        return ""
    print(f"  [{path}] {r.status_code} {len(r.text)}자")
    return r.text if r.status_code == 200 else ""


def contexts(body, pattern, width=260, limit=8):
    out = []
    for m in re.finditer(pattern, body, re.I):
        s = max(0, m.start() - width)
        out.append(re.sub(r"\s+", " ", body[s:m.start() + width]))
        if len(out) >= limit:
            break
    return out


def main():
    print("### 1. 메타·메뉴 파일을 받는다")
    bodies = {p: get(p) for p in FILES}

    print("\n### 2. 각 파일에서 CMA 가 나오는 자리")
    for p, body in bodies.items():
        if not body:
            continue
        hits = contexts(body, r"CMA|종합자산관리|씨엠에이")
        print(f"\n  --- {p} : {len(hits)}건 ---")
        for h in hits:
            print(f"    ...{h}")

    print("\n### 3. 파일에 적힌 서비스 이름 (DIS로 시작하는 것)")
    for p, body in bodies.items():
        if not body:
            continue
        names = sorted(set(re.findall(r"\b(DIS[A-Za-z0-9_]{4,})\b", body)))
        cma = [n for n in names if "cma" in n.lower()]
        print(f"  {p}: 총 {len(names)}개, CMA 관련 {cma}")
        if p.endswith("service.js") or p.endswith("disMetaDtoInfo.js"):
            print(f"    앞 40개: {names[:40]}")

    print("\n### 4. 껍데기 화면 하나를 통째로 (구조 파악용)")
    body = get("/wq/compann/DISCustDpsUseRate.xml")
    print(body[:1800])
    return 0


if __name__ == "__main__":
    sys.exit(main())
