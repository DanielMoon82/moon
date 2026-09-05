#!/usr/bin/env python3
"""blog-exports/<slug>/네이버블로그.txt 를 네이버 블로그에 발행한다.

네이버는 블로그 글쓰기 공개 API를 제공하지 않는다. 그래서 브라우저로
로그인해 스마트에디터에 본문을 넣는 방식을 쓴다.

필요한 secret:
  NAVER_ID, NAVER_PW

주의: 네이버 로그인은 캡차·기기 등록·2단계 인증으로 자동 로그인을 막는
경우가 많다. 이 코드는 그걸 우회하지 않으므로, 막히면 실패로 끝나고
publish-debug/ 에 스크린샷을 남긴다. 그 상태가 계속되면 blog-exports/ 의
붙여넣기 파일을 쓰는 편이 확실하다.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blog_publish_common import (  # noqa: E402
    EXPORT_DIR, blocked_message, dump_failure, env, load_state, mark_published,
    new_context, parse_export_header, pending_slugs, save_state,
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


def login(page, naver_id, naver_pw):
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.fill(ID_INPUT, naver_id)
    page.fill(PW_INPUT, naver_pw)
    page.click(LOGIN_BUTTON)
    page.wait_for_load_state("networkidle")

    if "nidlogin" in page.url or "deviceConfirm" in page.url:
        dump_failure(page, "naver-login")
        sys.exit(blocked_message("네이버"))


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
    naver_id = env("NAVER_ID")
    naver_pw = env("NAVER_PW")
    only = env("ONLY_SLUG", required=False)

    slugs = pending_slugs(CHANNEL, EXPORT_FILE, only)
    if not slugs:
        print("네이버: 발행할 새 글이 없습니다")
        return 0

    from playwright.sync_api import sync_playwright

    state = load_state()
    failures = []
    with sync_playwright() as pw:
        browser, context = new_context(pw)
        page = context.new_page()
        try:
            login(page, naver_id, naver_pw)
            for slug in slugs:
                meta, body = read_export(slug)
                try:
                    url = write_post(page, naver_id, meta, body)
                    mark_published(state, CHANNEL, slug, url)
                    print(f"네이버 발행 완료: {slug} -> {url}")
                except Exception as exc:
                    dump_failure(page, f"naver-{slug}")
                    failures.append(f"{slug}: {exc}")
        finally:
            save_state(state)
            context.close()
            browser.close()

    if failures:
        print("네이버 발행 실패:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
