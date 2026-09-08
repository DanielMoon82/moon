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
# 브라우저로 직접 로그인해서 받아 둔 쿠키가 여기 쌓인다. 저장소에 올리지 않는다.
SESSION_DIR = ROOT / ".publish-session"
# 어느 블로그에 올리는지. 주소일 뿐이라 저장소에 둔다.
TARGETS_PATH = ROOT / "data" / "blog-targets.json"

NAV_TIMEOUT_MS = 45_000


def targets():
    """data/blog-targets.json 에 적어 둔 발행 대상 주소."""
    if not TARGETS_PATH.exists():
        return {}
    try:
        data = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {k: str(v).strip() for k, v in data.items()
            if not k.startswith("_") and isinstance(v, str)}


def env(name, required=True):
    """환경변수 → 저장소에 적어 둔 기본값 순으로 찾는다.

    블로그 주소 같은 건 매번 넣어 줄 이유가 없어서 기본값을 둔다.
    비밀값은 여기 들어오지 않는다 — 그건 .publish-session/ 에만 있다."""
    value = os.environ.get(name, "").strip() or targets().get(name, "")
    if required and not value:
        sys.exit(f"missing required setting: {name}")
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


def session_path(channel):
    return SESSION_DIR / f"{channel}.json"


def has_session(channel):
    """저장해 둔 로그인 쿠키가 있는지."""
    path = session_path(channel)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return bool(data.get("cookies") or data.get("origins"))


def save_session(channel, storage_state):
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    path = session_path(channel)
    path.write_text(
        json.dumps(storage_state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    # 쿠키 파일이다. 같은 계정으로 로그인한 것과 같으니 권한을 좁혀 둔다.
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def clear_session(channel):
    path = session_path(channel)
    if path.exists():
        path.unlink()
        return True
    return False


# 사람이 직접 로그인할 때 쓰는 값. 봇처럼 보이면 로그인 화면에서 막힌다.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def new_context(playwright, channel=None, headless=True):
    """브라우저를 띄운다.

    channel 을 주면 그 채널의 저장된 로그인 쿠키를 넣고 시작한다. 그래서
    비밀번호를 코드에 두지 않고도 발행할 수 있다.
    """
    browser = playwright.chromium.launch(
        headless=headless,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    kwargs = dict(
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        user_agent=UA,
        viewport={"width": 1440, "height": 960},
    )
    if channel and has_session(channel):
        kwargs["storage_state"] = str(session_path(channel))
    context = browser.new_context(**kwargs)
    context.set_default_timeout(NAV_TIMEOUT_MS)
    return browser, context


def blocked_message(service):
    return (
        f"{service} 로그인 세션이 없거나 만료됐습니다. 대시보드를 열어 "
        f"'{service} 로그인' 버튼을 누르고 브라우저에서 직접 로그인해 주세요.\n"
        f"    python3 tools/publisher/server.py\n"
        f"(세션은 있는데 막힌 경우라면 publish-debug/ 에 그 시점 화면이 남아 있습니다.)"
    )
