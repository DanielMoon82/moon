"""티스토리·네이버 자동 발행 공용 헬퍼.

두 서비스 모두 공개 글쓰기 API가 없어 브라우저를 직접 몰아서 발행한다.
상대 사이트의 화면 구조에 의존하므로, 로그인 화면이나 에디터가 바뀌면
셀렉터를 고쳐야 한다. 셀렉터를 모듈 상단 상수로 빼 둔 것도 그래서다.

주의: 두 서비스 모두 자동 로그인을 막는 장치(캡차, 기기 등록, 2단계 인증)를
두고 있다. 이 코드는 그걸 우회하지 않는다. 막히면 막힌 대로 실패하고,
그 시점의 스크린샷과 HTML을 publish-debug/ 에 남긴다.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
EXPORT_DIR = ROOT / "blog-exports"
STATE_PATH = ROOT / "data" / "blog-published.json"
DEBUG_DIR = ROOT / "publish-debug"

NAV_TIMEOUT_MS = 45_000


def env(name, required=True):
    value = os.environ.get(name, "").strip()
    if required and not value:
        sys.exit(f"missing required secret: {name}")
    return value


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("state file is corrupt, starting fresh", file=sys.stderr)
    return {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


def mark_published(state, channel, slug, url=None):
    state.setdefault(channel, {})[slug] = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "url": url or "",
    }


def already_published(state, channel, slug):
    return slug in state.get(channel, {})


def pending_slugs(channel, filename, only_slug=""):
    """아직 안 올린 export 슬러그를 오래된 순으로 돌려준다.

    같은 글을 두 번 올리지 않기 위해 data/blog-published.json 을 기준으로
    거른다. 이 파일은 발행 뒤 워크플로가 커밋한다.
    """
    if not EXPORT_DIR.exists():
        return []
    state = load_state()
    out = []
    for path in sorted(EXPORT_DIR.iterdir()):
        if not path.is_dir() or not (path / filename).exists():
            continue
        if only_slug and path.name != only_slug:
            continue
        if already_published(state, channel, path.name):
            continue
        out.append(path.name)
    return out


def parse_export_header(text, keys):
    """export 파일 머리말에서 제목·태그·카테고리를 뽑는다.

    티스토리 파일은 HTML 주석, 네이버 파일은 [제목란] 같은 대괄호 블록을
    쓴다. 양쪽 모두 "키: 값" 또는 대괄호 라벨 다음 줄을 값으로 본다.
    """
    found = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        for key in keys:
            if key in found:
                continue
            if stripped.startswith(f"{key}:"):
                found[key] = stripped.split(":", 1)[1].strip()
            elif stripped == f"[{key}]" and i + 1 < len(lines):
                for nxt in lines[i + 1:]:
                    if nxt.strip():
                        found[key] = nxt.strip()
                        break
    return found


def dump_failure(page, label):
    """실패 지점의 화면과 DOM을 남긴다. 셀렉터를 고칠 때 이게 유일한 단서다."""
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    base = DEBUG_DIR / f"{label}-{stamp}"
    try:
        page.screenshot(path=str(base.with_suffix(".png")), full_page=True)
        base.with_suffix(".html").write_text(page.content(), encoding="utf-8")
        print(f"saved failure artifacts: {base}.png / .html", file=sys.stderr)
    except Exception as exc:
        print(f"could not save failure artifacts: {exc}", file=sys.stderr)


def new_context(playwright):
    browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
    context = browser.new_context(
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        viewport={"width": 1440, "height": 960},
    )
    context.set_default_timeout(NAV_TIMEOUT_MS)
    return browser, context


def blocked_message(service):
    return (
        f"{service} 로그인에 실패했습니다. 캡차·기기 등록·2단계 인증 중 하나에 "
        f"막혔을 가능성이 큽니다. publish-debug/ 의 스크린샷을 확인하세요. "
        f"이 경로가 계속 막히면 blog-exports/ 의 붙여넣기 파일을 쓰는 편이 확실합니다."
    )
