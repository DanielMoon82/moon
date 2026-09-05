#!/usr/bin/env python3
"""Probe 5차 — 전체 메뉴(gnb.xml)를 열어 CMA 화면을 찾는다.

4차에서 알아낸 것
  - main.xml 과 main.js 에서 실제 화면 경로 62개를 얻었다. 회사공시(compann)
    아래에 금리 화면들이 있다: DISCustDpsUseRate(고객예탁금 이용료율),
    DISCompCdtTrdIntRate(신용거래 이자율), DISCompDpsBndMrtIntRate 등.
  - 그런데 그 화면들을 직접 받으면 전부 오류로 튕겼다. main.xml 은 같은
    리퍼러로 열렸으니 리퍼러 문제만은 아니다. 왜 튕기는지부터 본다.
  - 목록에 /wq/com/gnb.xml 이 있다. 전체 메뉴라 여기에 CMA 화면이 있을 것이다.

아무것도 쓰지 않는다.
"""
import re
import sys

import requests

TIMEOUT = 25
BASE = "https://dis.kofia.or.kr"
ENTRY = BASE + "/websquare/index.jsp?w2xPath="
S = requests.Session()
S.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": ENTRY + "/wq/main/main.xml",
})


def get(url, **kw):
    try:
        r = S.get(url, timeout=TIMEOUT, **kw)
        return r
    except Exception as exc:  # noqa: BLE001
        print(f"    실패: {exc}", flush=True)
        return None


def main():
    print("### 1. 하위 화면이 왜 튕기는지 그대로 본다", flush=True)
    for p in ("/wq/compann/DISCustDpsUseRate.xml",
              "/wq/compann/DISCompCdtTrdIntRate.xml",
              "/wq/com/gnb.xml"):
        r = get(BASE + p)
        if r is not None:
            print(f"  [{p}] {r.status_code} {r.headers.get('content-type','?')} "
                  f"{len(r.text)}자 -> {r.url}", flush=True)

    print("\n### 2. index.jsp 를 먼저 거친 뒤 다시 받아 본다", flush=True)
    for p in ("/wq/compann/DISCustDpsUseRate.xml",):
        pre = get(ENTRY + p)
        print(f"  [index.jsp {p}] {pre.status_code if pre else '-'} "
              f"{len(pre.text) if pre else 0}자", flush=True)
        S.headers["Referer"] = ENTRY + p
        r = get(BASE + p)
        if r is not None:
            print(f"  [다시 {p}] {r.status_code} {len(r.text)}자 -> {r.url}", flush=True)
            if r.status_code == 200 and "error" not in r.url:
                svc = sorted(set(re.findall(r"pfmSvcName[^A-Za-z0-9_]{0,8}([A-Za-z0-9_]{4,})", r.text)))
                print(f"      서비스={svc}", flush=True)

    print("\n### 3. 전체 메뉴(gnb.xml)", flush=True)
    S.headers["Referer"] = ENTRY + "/wq/main/main.xml"
    r = get(BASE + "/wq/com/gnb.xml")
    if r is None or r.status_code != 200:
        print("  못 받음", flush=True)
        return 0
    body = r.text
    print(f"  {len(body)}자", flush=True)
    # 메뉴는 보통 '이름'과 'w2xPath' 가 붙어 다닌다. 둘 다 뽑아 나란히 본다.
    paths = re.findall(r"(/wq/[A-Za-z0-9_/.\-]+\.xml)", body)
    print(f"  경로 {len(set(paths))}개", flush=True)
    for p in sorted(set(paths)):
        print(f"    {p}", flush=True)
    print("\n  --- CMA 가 나오는 자리 ---", flush=True)
    hits = 0
    for m in re.finditer(r"CMA|씨엠에이|종합자산관리", body):
        s = max(0, m.start() - 300)
        print("    ..." + re.sub(r"\s+", " ", body[s:m.start() + 300]), flush=True)
        hits += 1
        if hits >= 6:
            break
    if not hits:
        print("    (없음)", flush=True)
        print(f"\n  앞부분 2000자:\n{body[:2000]}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
