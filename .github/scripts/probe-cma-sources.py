#!/usr/bin/env python3
"""Probe 4차 — 화면 정의를 훑어 CMA 화면과 서비스 이름을 찾는다.

3차에서 알아낸 것
  - 서비스 이름이 틀리면 pfmResponseCode COMS9009 에
    "proframe application name [FS-DIS2] [이름] is not found." 가 온다.
    즉 맞고 틀림을 구분할 수 있는 신호가 있다. 내가 찍었던 두 이름도 오답이었다.
  - disCommon.js 에는 메뉴 함수가 없다. 다른 파일에 있다.
  - main.xml(142KB)은 리퍼러만 붙이면 열린다.

그래서 메인 화면 정의와 그 스크립트에서 화면 경로를 모아 따라 들어가며
CMA 라는 말이 나오는 화면을 찾고, 거기 적힌 서비스 이름을 그대로 읽는다.
아무것도 쓰지 않는다.
"""
import re
import sys

import requests

TIMEOUT = 25
BASE = "https://dis.kofia.or.kr"
LIMIT = 45          # 남의 서버다. 받는 횟수를 묶어 둔다.
S = requests.Session()
S.headers.update({
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": BASE + "/websquare/index.jsp?w2xPath=/wq/main/main.xml",
})

PATH_RE = re.compile(r"(/wq/[A-Za-z0-9_/.\-]+\.xml)")
JS_RE = re.compile(r"(/js/[A-Za-z0-9_/.\-]+\.js)")
SVC_RE = re.compile(r"pfmSvcName[^A-Za-z0-9_]{0,8}([A-Za-z0-9_]{4,})")


def fetch(path):
    try:
        r = S.get(BASE + path, timeout=TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    if r.status_code != 200 or "error.html" in r.url or "web-firewall" in r.text:
        return None, f"{r.status_code} 막힘/오류"
    return r.text, None


def main():
    print("### 1. 메인 화면 정의와 스크립트에서 경로를 모은다")
    seeds = ["/wq/main/main.xml"]
    texts = {}
    for p in seeds:
        body, err = fetch(p)
        print(f"  [{p}] {'%d자' % len(body) if body else err}")
        if body:
            texts[p] = body

    for js in sorted({j for t in texts.values() for j in JS_RE.findall(t)})[:6]:
        body, err = fetch(js)
        print(f"  [{js}] {'%d자' % len(body) if body else err}")
        if body:
            texts[js] = body

    paths = sorted({p for t in texts.values() for p in PATH_RE.findall(t)})
    print(f"\n  모은 화면 경로 {len(paths)}개")
    for p in paths[:60]:
        print(f"    {p}")

    print(f"\n### 2. 경로를 따라가며 CMA 를 찾는다 (최대 {LIMIT}개)")
    # 이름만 봐도 그럴듯한 것부터 본다.
    def score(p):
        low = p.lower()
        return (0 if "cma" in low else 1,
                0 if any(k in low for k in ("cominfo", "finpro", "suik", "rate", "prod")) else 1,
                p)

    seen, found, calls = set(), [], 0
    for p in sorted(paths, key=score):
        if calls >= LIMIT:
            break
        if p in seen or p in texts:
            continue
        seen.add(p)
        calls += 1
        body, err = fetch(p)
        if not body:
            continue
        has_cma = "CMA" in body or "cma" in body.lower()
        svcs = sorted(set(SVC_RE.findall(body)))
        more = PATH_RE.findall(body)
        if has_cma or svcs:
            print(f"  [{p}] {len(body)}자 CMA={has_cma} 서비스={svcs[:8]} 하위경로={len(set(more))}")
        if has_cma:
            found.append((p, svcs, body))

    print(f"\n### 3. CMA 가 나온 화면 {len(found)}개")
    for p, svcs, body in found[:6]:
        print(f"\n  --- {p} 서비스={svcs} ---")
        for m in re.finditer(r"CMA", body):
            s = max(0, m.start() - 160)
            print("    ..." + re.sub(r"\s+", " ", body[s:m.start() + 160]))
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
