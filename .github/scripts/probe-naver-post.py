#!/usr/bin/env python3
"""Probe — 참고할 네이버 블로그 글을 받아 본문을 뽑는다.

어투와 형식을 따라 하려면 실제 글을 읽어야 한다. 컨테이너와 WebFetch 는
네이버를 막아서 러너에서 받는다. 네이버 블로그는 주소 형태가 여러 가지라
되는 것을 찾을 때까지 차례로 시도한다. 아무것도 쓰지 않는다.
"""
import html
import re
import sys

import requests

BLOG, LOG = "ejsj6251", "223957944696"
UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.google.com/",
}
CANDIDATES = [
    f"https://m.blog.naver.com/{BLOG}/{LOG}",
    f"https://m.blog.naver.com/PostView.naver?blogId={BLOG}&logNo={LOG}",
    f"https://blog.naver.com/PostView.naver?blogId={BLOG}&logNo={LOG}"
    "&redirect=Dlog&widgetTypeCall=true&directAccess=false",
    f"https://blog.naver.com/{BLOG}/{LOG}",
]


def to_text(raw):
    """태그를 걷어내고 사진 자리를 표시해 글의 짜임새가 보이게 한다."""
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<img[^>]*>", "\n[사진]\n", raw)
    raw = re.sub(r"(?i)<br[^>]*>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|h[1-6]|li|tr)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw)
    lines = [re.sub(r"[ \t ]+", " ", l).strip() for l in raw.splitlines()]
    out, blank = [], 0
    for l in lines:
        if not l:
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        out.append(l)
    return "\n".join(out).strip()


def main():
    for url in CANDIDATES:
        print(f"\n### {url}")
        try:
            r = requests.get(url, headers=UA, timeout=25, allow_redirects=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  실패: {str(exc)[:110]}")
            continue
        print(f"  {r.status_code} {len(r.text)}자 → {r.url[:110]}")
        if r.status_code != 200 or len(r.text) < 2000:
            continue

        title = re.search(r'(?i)<meta[^>]+property="og:title"[^>]+content="([^"]*)"', r.text)
        if title:
            print(f"  제목: {html.unescape(title.group(1))}")

        # 본문 영역만 잘라낸다. 스마트에디터 버전마다 이름이 다르다.
        body = None
        for pat in (r'(?is)<div[^>]+class="se-main-container"[^>]*>(.*?)</div>\s*</div>\s*</div>',
                    r'(?is)id="postViewArea"[^>]*>(.*?)</div>',
                    r'(?is)class="se_component_wrap[^"]*"[^>]*>(.*?)$'):
            m = re.search(pat, r.text)
            if m and len(m.group(1)) > 800:
                body = m.group(1)
                print(f"  본문 영역 찾음 ({len(body)}자 원본)")
                break
        text = to_text(body or r.text)
        if len(text) < 300:
            print(f"  본문이 너무 짧다. 앞부분: {text[:200]!r}")
            continue
        print(f"\n----- 본문 {len(text)}자 -----")
        print(text[:6000])
        return 0
    print("\n모두 실패")
    return 0


if __name__ == "__main__":
    sys.exit(main())
