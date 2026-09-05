#!/usr/bin/env python3
"""Probe 8차 — 남은 두 갈래를 동시에 확인한다.

7차까지로 못박은 것
  - 금융투자협회 전자공시에는 CMA 항목이 없다. DTO 메타 145개, 상단·좌측
    메뉴 어디에도 CMA 가 없다. 협회가 공시하는 건 증권사별 '고객예탁금
    이용료율'(DISCustDpsUseRateListDTO)이다. CMA 와 성격이 가깝지만 다르다.
  - 화면 XML 에는 서비스 이름이 없다. 화면별 자바스크립트가 부른다.

그래서 이번엔
  (가) 그 이용료율 화면의 자바스크립트를 찾아 실제 호출을 읽고 불러 본다.
       증권사별 표가 실제로 나오는지 봐야 대안으로 쓸지 판단할 수 있다.
  (나) 증권사 자사 페이지가 러너에서 열리기는 하는지 본다. 열리지도 않으면
       증권사별로 직접 긁는 길은 처음부터 없는 것이다.

아무것도 쓰지 않는다.
"""
import re
import sys

import requests

TIMEOUT = 20
BASE = "https://dis.kofia.or.kr"
S = requests.Session()
S.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": BASE + "/websquare/index.jsp?w2xPath=/wq/main/main.xml",
})

BROKERS = [
    ("미래에셋증권", "https://securities.miraeasset.com/"),
    ("삼성증권", "https://www.samsungpop.com/"),
    ("NH투자증권", "https://www.nhqv.com/"),
    ("한국투자증권", "https://securities.koreainvestment.com/"),
    ("KB증권", "https://www.kbsec.com/"),
    ("키움증권", "https://www.kiwoom.com/"),
    ("신한투자증권", "https://www.shinhansec.com/"),
    ("대신증권", "https://www.daishin.com/"),
    ("유진투자증권", "https://www.eugenefn.com/"),
    ("하나증권", "https://www.hanaw.com/"),
]


def main():
    print("### 가. 협회 '고객예탁금 이용료율' 화면의 호출부")
    js = ""
    for p in ("/js/compann/DISCustDpsUseRate.js",
              "/js/compann/inc/DISCustDpsUseRate.js",
              "/js/com/callProframe.js"):
        try:
            r = S.get(BASE + p, timeout=TIMEOUT)
            print(f"  [{p}] {r.status_code} {len(r.text)}자")
            if r.status_code == 200 and len(r.text) > 300:
                js += r.text
        except Exception as exc:  # noqa: BLE001
            print(f"  [{p}] 실패: {exc}")

    svcs = sorted(set(re.findall(r"[\"']([A-Za-z0-9_]{6,}(?:SO|SVC))[\"']", js)))
    print(f"  서비스 후보: {svcs[:20]}")
    for svc in svcs[:12]:
        body = ('<?xml version="1.0" encoding="utf-8"?><message>'
                '<proframeHeader><pfmAppName>FS-DIS2</pfmAppName>'
                f'<pfmSvcName>{svc}</pfmSvcName><pfmFnName>select</pfmFnName>'
                '</proframeHeader><systemHeader></systemHeader>'
                '<DISCondFuncDTO><tmpV30>0</tmpV30></DISCondFuncDTO></message>')
        try:
            r = S.post(BASE + "/proframeWeb/XMLSERVICES/", data=body.encode("utf-8"),
                       headers={"Content-Type": "application/xml; charset=UTF-8"},
                       timeout=TIMEOUT)
            exists = "is not found" not in r.text
            print(f"    [{svc}] 존재={exists} {len(r.text)}자")
            if exists:
                print("      " + r.text[:900].replace("\n", "\n      "))
        except Exception as exc:  # noqa: BLE001
            print(f"    [{svc}] 실패: {exc}")

    print("\n### 나. 증권사 자사 페이지가 러너에서 열리는가")
    ok = 0
    for name, url in BROKERS:
        try:
            r = requests.get(url, headers=S.headers, timeout=TIMEOUT, allow_redirects=True)
            note = ""
            low = r.text.lower()
            if "javascript" in low and len(r.text) < 3000:
                note = " (자바스크립트 확인 페이지로 보임)"
            print(f"  {name:<10} {r.status_code} {len(r.text):>7}자{note}")
            if r.status_code == 200 and len(r.text) > 3000:
                ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"  {name:<10} 실패: {str(exc)[:80]}")
    print(f"  열린 곳 {ok}/{len(BROKERS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
