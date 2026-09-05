#!/usr/bin/env python3
"""blog-exports/<slug>/티스토리.html 을 티스토리에 발행한다.

티스토리 Open API 는 종료되어 공개된 글쓰기 엔드포인트가 없다. 그래서
브라우저로 로그인해 에디터에 본문을 넣는 방식을 쓴다. 티스토리 로그인은
카카오계정을 거치므로 카카오 아이디·비밀번호가 필요하다.

필요한 secret:
  TISTORY_KAKAO_ID, TISTORY_KAKAO_PW, TISTORY_BLOG_NAME

화면 구조에 의존하는 코드다. 셀렉터가 안 맞으면 publish-debug/ 에 남는
스크린샷과 HTML을 보고 아래 상수를 고치면 된다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blog_publish_common import (  # noqa: E402
    EXPORT_DIR, blocked_message, dump_failure, env, load_state, mark_published,
    new_context, parse_export_header, pending_slugs, save_state,
)

CHANNEL = "tistory"
EXPORT_FILE = "티스토리.html"

LOGIN_URL = "https://www.tistory.com/auth/login"
KAKAO_BUTTON = "a[class*='kakao'], a:has-text('카카오계정으로 로그인')"
KAKAO_ID = "input[name='loginId'], input[name='email']"
KAKAO_PW = "input[name='password']"
KAKAO_SUBMIT = "button[type='submit']"

WRITE_URL = "https://{blog}.tistory.com/manage/newpost/"
TITLE_INPUT = "#post-title-inp, textarea[placeholder*='제목']"
MODE_BUTTON = "#editor-mode-layer-btn-open"
HTML_MODE = "#editor-mode-html"
CODEMIRROR = ".CodeMirror"
TAG_INPUT = "#tagText, input[placeholder*='태그']"
CATEGORY_BUTTON = "#category-btn"
CATEGORY_ITEM = "#category-list button:has-text('{name}')"
DONE_BUTTON = "#publish-layer-btn"
PUBLISH_BUTTON = "#publish-btn"


def read_export(slug):
    text = (EXPORT_DIR / slug / EXPORT_FILE).read_text(encoding="utf-8")
    meta = parse_export_header(text, ["제목", "태그", "카테고리"])
    # 안내용 머리말 주석을 걷어내고 본문만 남긴다.
    body = text.split("-->", 1)[1].strip() if "-->" in text else text
    if not meta.get("제목"):
        sys.exit(f"{slug}: 제목을 찾지 못했습니다")
    return meta, body


def login(page, kakao_id, kakao_pw):
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.click(KAKAO_BUTTON)
    page.wait_for_load_state("domcontentloaded")

    page.fill(KAKAO_ID, kakao_id)
    page.fill(KAKAO_PW, kakao_pw)
    page.click(KAKAO_SUBMIT)
    page.wait_for_load_state("networkidle")

    # 로그인이 됐다면 카카오 도메인을 벗어나 있어야 한다.
    if "accounts.kakao.com" in page.url or "/auth/login" in page.url:
        dump_failure(page, "tistory-login")
        sys.exit(blocked_message("티스토리(카카오)"))


def select_category(page, name):
    """카테고리를 고른다. 블로그마다 카테고리 이름이 달라 못 찾을 수 있으므로,
    실패하면 기본 카테고리로 두고 발행을 계속한다."""
    if not name:
        return
    try:
        page.click(CATEGORY_BUTTON, timeout=5000)
        page.click(CATEGORY_ITEM.format(name=name), timeout=5000)
    except Exception:
        print(f"티스토리: '{name}' 카테고리를 찾지 못해 기본값으로 발행합니다",
              file=sys.stderr)


def write_post(page, blog, meta, body):
    page.goto(WRITE_URL.format(blog=blog), wait_until="domcontentloaded")

    # '이어서 작성하시겠습니까' 안내가 뜨면 새로 쓰기를 고른다.
    try:
        page.click("button:has-text('취소')", timeout=4000)
    except Exception:
        pass

    page.fill(TITLE_INPUT, meta["제목"])

    # 에디터를 HTML 모드로 바꾼 뒤 본문을 통째로 넣는다.
    page.click(MODE_BUTTON)
    page.click(HTML_MODE)
    page.wait_for_selector(CODEMIRROR)
    page.evaluate(
        "(html) => { document.querySelector('.CodeMirror').CodeMirror.setValue(html); }",
        body,
    )

    select_category(page, meta.get("카테고리"))

    for tag in [t.strip() for t in meta.get("태그", "").split(",") if t.strip()]:
        page.fill(TAG_INPUT, tag)
        page.keyboard.press("Enter")

    page.click(DONE_BUTTON)
    page.wait_for_selector(PUBLISH_BUTTON)
    page.click(PUBLISH_BUTTON)
    page.wait_for_load_state("networkidle")
    return page.url


def main():
    blog = env("TISTORY_BLOG_NAME")
    kakao_id = env("TISTORY_KAKAO_ID")
    kakao_pw = env("TISTORY_KAKAO_PW")
    only = env("ONLY_SLUG", required=False)

    slugs = pending_slugs(CHANNEL, EXPORT_FILE, only)
    if not slugs:
        print("티스토리: 발행할 새 글이 없습니다")
        return 0

    from playwright.sync_api import sync_playwright

    state = load_state()
    failures = []
    with sync_playwright() as pw:
        browser, context = new_context(pw)
        page = context.new_page()
        try:
            login(page, kakao_id, kakao_pw)
            for slug in slugs:
                meta, body = read_export(slug)
                try:
                    url = write_post(page, blog, meta, body)
                    mark_published(state, CHANNEL, slug, url)
                    print(f"티스토리 발행 완료: {slug} -> {url}")
                except Exception as exc:
                    dump_failure(page, f"tistory-{slug}")
                    failures.append(f"{slug}: {exc}")
        finally:
            save_state(state)
            context.close()
            browser.close()

    if failures:
        print("티스토리 발행 실패:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
