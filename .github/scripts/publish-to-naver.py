#!/usr/bin/env python3
"""blog-exports/<slug>/네이버블로그.txt 를 네이버 블로그에 발행한다.

네이버는 블로그 글쓰기 공개 API를 제공하지 않는다. 그래서 브라우저로
로그인해 스마트에디터에 본문을 넣는 방식을 쓴다.

로그인은 이 스크립트가 하지 않는다. 네이버는 캡차·기기 등록·2단계 인증으로
자동 로그인을 막기 때문에, 사람이 대시보드에서 한 번 직접 로그인하고
그때 받은 쿠키를 .publish-session/naver.json 에 저장해 두는 방식을 쓴다.

    python3 tools/publisher/server.py     # 대시보드에서 '네이버 로그인'

쿠키가 없거나 만료됐으면 여기서 바로 멈춘다. 비밀번호를 다루지 않는다.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blog_publish_common import (  # noqa: E402
    EXPORT_DIR, blocked_message, dump_failure, env, has_session, load_state,
    mark_published, new_context, parse_export_header, pending_slugs,
    save_session, save_state,
)

CHANNEL = "naver"
EXPORT_FILE = "네이버블로그.txt"

LOGIN_URL = "https://nid.naver.com/nidlogin.login"
ID_INPUT = "#id"
PW_INPUT = "#pw"
LOGIN_BUTTON = "#log\\.login, button[type='submit']"

WRITE_URL = "https://blog.naver.com/{blog_id}?Redirect=Write"
EDITOR_FRAME = "iframe#mainFrame"
TITLE_AREA = ".se-documentTitle .se-text-paragraph, .se-placeholder"
BODY_AREA = ".se-component.se-text .se-text-paragraph"
PUBLISH_OPEN = ".publish_btn__m9KHH, button:has-text('발행')"
PUBLISH_CONFIRM = ".confirm_btn__WEaBq, button:has-text('발행')"
TAG_INPUT = "#tag-input, input[placeholder*='태그']"
CATEGORY_SELECT = "button.selectbox_button__jb1Dt, button[class*='category']"
CATEGORY_ITEM = "label:has-text('{name}'), li:has-text('{name}')"


def read_export(slug):
    """붙여넣기용 텍스트에서 제목·카테고리·태그·본문을 가른다."""
    text = (EXPORT_DIR / slug / EXPORT_FILE).read_text(encoding="utf-8")
    meta = parse_export_header(text, ["제목란", "카테고리", "태그란"])

    # [본문] 과 [태그란] 사이가 실제 본문이다.
    match = re.search(r"\[본문\]\s*(.*?)\s*\[태그란\]", text, re.S)
    body = match.group(1).strip() if match else ""
    if not meta.get("제목란") or not body:
        sys.exit(f"{slug}: 제목이나 본문을 찾지 못했습니다")
    return meta, body


def whoami(page):
    """저장된 쿠키로 로그인이 살아 있는지 보고, 살아 있으면 블로그 아이디를 준다.

    네이버는 로그인이 풀리면 어느 페이지를 열어도 nid.naver.com 으로 보낸다.
    그걸 판정에 쓴다."""
    page.goto("https://blog.naver.com/", wait_until="domcontentloaded")
    if "nid.naver.com" in page.url or "nidlogin" in page.url:
        return None
    # 로그인 상태면 내 블로그로 리다이렉트되면서 주소에 아이디가 붙는다.
    match = re.search(r"blog\.naver\.com/(?:PostList\.naver\?blogId=)?([A-Za-z0-9_-]+)",
                      page.url)
    if match and match.group(1) not in {"", "PostList.naver"}:
        return match.group(1)
    try:
        href = page.locator("a[href*='blog.naver.com/']").first.get_attribute("href")
        found = re.search(r"blog\.naver\.com/([A-Za-z0-9_-]+)", href or "")
        if found:
            return found.group(1)
    except Exception:
        pass
    return env("NAVER_BLOG_ID", required=False) or None


def select_category(page, frame, name):
    """카테고리를 고른다. 블로그마다 이름이 달라 못 찾을 수 있으므로,
    실패하면 기본 카테고리로 두고 발행을 계속한다."""
    if not name:
        return
    try:
        frame.locator(CATEGORY_SELECT).first.click(timeout=5000)
        frame.locator(CATEGORY_ITEM.format(name=name)).first.click(timeout=5000)
    except Exception:
        print(f"네이버: '{name}' 카테고리를 찾지 못해 기본값으로 발행합니다",
              file=sys.stderr)


def write_post(page, blog_id, meta, body):
    page.goto(WRITE_URL.format(blog_id=blog_id), wait_until="domcontentloaded")
    frame = page.frame_locator(EDITOR_FRAME)

    # 임시저장 글 복구 팝업이 뜨면 닫는다.
    try:
        frame.locator("button:has-text('취소')").click(timeout=5000)
    except Exception:
        pass

    frame.locator(TITLE_AREA).first.click()
    page.keyboard.type(meta["제목란"])

    frame.locator(BODY_AREA).first.click()
    for line in body.splitlines():
        page.keyboard.type(line)
        page.keyboard.press("Enter")

    frame.locator(PUBLISH_OPEN).first.click()

    select_category(page, frame, meta.get("카테고리"))

    tags = meta.get("태그란", "")
    for tag in [t.lstrip("#").strip() for t in tags.split() if t.strip()]:
        try:
            frame.locator(TAG_INPUT).fill(tag)
            page.keyboard.press("Enter")
        except Exception:
            break  # 태그 입력란을 못 찾으면 태그 없이 발행한다

    frame.locator(PUBLISH_CONFIRM).last.click()
    page.wait_for_load_state("networkidle")
    return page.url


def main():
    only = env("ONLY_SLUG", required=False)

    if not has_session(CHANNEL):
        print(blocked_message("네이버"), file=sys.stderr)
        return 1

    slugs = pending_slugs(CHANNEL, EXPORT_FILE, only)
    if not slugs:
        print("네이버: 발행할 새 글이 없습니다")
        return 0

    from playwright.sync_api import sync_playwright

    state = load_state()
    failures = []
    with sync_playwright() as pw:
        browser, context = new_context(pw, channel=CHANNEL)
        page = context.new_page()
        try:
            blog_id = whoami(page)
            if not blog_id:
                dump_failure(page, "naver-session")
                print(blocked_message("네이버"), file=sys.stderr)
                return 1
            for slug in slugs:
                meta, body = read_export(slug)
                try:
                    url = write_post(page, blog_id, meta, body)
                    mark_published(state, CHANNEL, slug, url)
                    print(f"네이버 발행 완료: {slug} -> {url}")
                except Exception as exc:
                    dump_failure(page, f"naver-{slug}")
                    failures.append(f"{slug}: {exc}")
        finally:
            save_state(state)
            # 발행하면서 갱신된 쿠키를 되돌려 놓는다. 안 하면 세션이 빨리 죽는다.
            try:
                save_session(CHANNEL, context.storage_state())
            except Exception:
                pass
            context.close()
            browser.close()

    if failures:
        print("네이버 발행 실패:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
