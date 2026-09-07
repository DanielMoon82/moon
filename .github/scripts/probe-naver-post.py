#!/usr/bin/env python3
"""Probe — 참고할 네이버 블로그 글을 받아 본문을 뽑는다.

어투와 형식을 따라 하려면 실제 글을 읽어야 한다. 컨테이너와 WebFetch 는
네이버를 막아서 러너에서 받는다. 네이버 블로그는 주소 형태가 여러 가지라
되는 것을 찾을 때까지 차례로 시도한다. 아무것도 쓰지 않는다.

1차에서 알아낸 것
  - m.blog.naver.com/{id}/{logNo} 가 200 으로 열린다(213KB).
    제목은 "독일 바이에른 알프스의 보석 아이브제 호수 Eibsee".
  - 다만 본문을 1,407자만 건졌다. se-main-container 를 닫는 </div> 를
    중첩된 안쪽 div 가 먼저 먹어서 잘렸다. 스마트에디터 ONE 은 문단이
    se-text-paragraph, 사진이 se-image 로 나뉘므로 그 조각들을 직접 모은다.
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

        # 본문 영역을 통째로 자르지 않는다. 중첩 div 때문에 닫는 태그를 못 믿는다.
        # 대신 문단·사진 조각을 순서대로 모아 글의 흐름을 그대로 재현한다.
        i = r.text.find("se-main-container")
        chunk = r.text[i:] if i != -1 else r.text
        parts = re.findall(
            r'(?is)<(p|h[1-6])[^>]*class="[^"]*se-text-paragraph[^"]*"[^>]*>(.*?)</\1>'
            r'|(?is)(<div[^>]*class="[^"]*se-module-image[^"]*")',
            chunk)
        lines, imgs = [], 0
        for tag, inner, img in parts:
            if img:
                imgs += 1
                lines.append(f"[사진 {imgs}]")
                continue
            t = to_text(inner)
            lines.append(t if t else "")      # 빈 문단도 살린다. 줄바꿈 습관이 보인다.
        text = "\n".join(lines).strip()
        if len(text) < 300:
            print(f"  본문이 너무 짧다. 조각 {len(parts)}개, 앞부분: {text[:200]!r}")
            continue
        print(f"\n----- 본문 {len(text)}자 · 문단 {len(parts)}개 · 사진 {imgs}장 -----")
        print(text[:7000])
        return 0
    print("\n모두 실패")
    return 0


if __name__ == "__main__":
    sys.exit(main())
