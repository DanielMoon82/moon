#!/usr/bin/env python3
"""사이트에 걸린 바깥 링크가 실제로 열리는지 본다. 아무것도 쓰지 않는다."""
import re, sys, requests
UA = {"User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
      "Accept-Language": "ko-KR,ko;q=0.9"}
html = open("index.html", encoding="utf-8").read()
urls = sorted(set(re.findall(r'href="(https?://[^"]+)"', html)))
print(f"바깥 링크 {len(urls)}개\n")
for u in urls:
    try:
        r = requests.get(u, headers=UA, timeout=20, allow_redirects=True)
        note = ""
        if r.status_code == 403: note = "  (봇 차단일 가능성 — 사람은 열릴 수 있음)"
        elif r.status_code >= 400: note = "  ← 문제"
        print(f"  {r.status_code}  {u[:70]}{note}")
    except Exception as exc:
        print(f"  ---  {u[:70]}  실패: {str(exc)[:60]}")
