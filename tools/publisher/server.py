#!/usr/bin/env python3
"""내 컴퓨터에서 띄우는 발행 대시보드.

    python3 tools/publisher/server.py

브라우저가 열리면 채널마다 [로그인] 과 [발행] 버튼이 있다. 로그인 버튼을
누르면 진짜 브라우저 창이 떠서 직접 로그인하게 되고, 그때 받은 세션이
.publish-session/ 에 저장된다. 그다음부터는 발행 버튼만 누르면 된다.

세션 파일은 저장소에 올라가지 않는다(.gitignore). 비밀번호는 어디에도
저장하지 않는다.
"""
import base64
import binascii
import json
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
from blog_publish_common import (  # noqa: E402
    SESSION_DIR, clear_session, has_session, session_path, targets,
)
import login as login_mod  # noqa: E402
import photos as photos_mod  # noqa: E402

PORT = int(os.environ.get("PUBLISHER_PORT", "8765"))
EXPORT_DIR = ROOT / "blog-exports"
CONFIG_PATH = SESSION_DIR / "config.json"
SCRIPTS = ROOT / ".github" / "scripts"

CHANNELS = [
    {"id": "site", "label": "홈페이지", "kind": "git"},
    {"id": "naver", "label": "네이버 블로그", "kind": "cookie"},
    {"id": "tistory", "label": "티스토리", "kind": "cookie"},
    {"id": "blogger", "label": "구글 블로거", "kind": "oauth"},
]
EXPORT_FILES = {"naver": "네이버블로그.txt", "tistory": "티스토리.html",
                "blogger": "블로거.html"}


# ------------------------------------------------------------------ 설정
def load_config():
    """저장소에 적어 둔 기본 주소 위에, 이 컴퓨터에서 바꾼 값을 덮는다."""
    cfg = dict(targets())
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return cfg


def save_config(cfg):
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")


# ------------------------------------------------------------- 작업 실행
class Job:
    """한 번에 하나만 돌린다. 로그인 창 두 개가 동시에 뜨면 헷갈린다."""

    def __init__(self):
        self.lock = threading.Lock()
        self.label = ""
        self.lines = []
        self.running = False
        self.ok = None

    def log(self, text):
        for line in str(text).rstrip("\n").splitlines() or [""]:
            self.lines.append(line)

    def start(self, label, fn):
        if not self.lock.acquire(blocking=False):
            return False
        self.label, self.lines, self.running, self.ok = label, [], True, None

        def run():
            try:
                self.ok = bool(fn(self.log))
            except Exception as exc:  # 실패해도 대시보드는 살아 있어야 한다
                self.log(f"오류: {exc}")
                self.ok = False
            finally:
                self.running = False
                self.lock.release()

        threading.Thread(target=run, daemon=True).start()
        return True

    def snapshot(self):
        return {"label": self.label, "running": self.running,
                "ok": self.ok, "log": self.lines[-400:]}


JOB = Job()


def run_script(script, log, extra_env=None):
    env = dict(os.environ)
    env.update(extra_env or {})
    env.setdefault("PYTHONUNBUFFERED", "1")
    proc = subprocess.Popen(
        [sys.executable, str(SCRIPTS / script)],
        cwd=str(ROOT), env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    for line in proc.stdout:
        log(line.rstrip("\n"))
    return proc.wait() == 0


def publish_site(log, slug):
    """홈페이지는 깃허브 페이지다. 커밋해서 밀면 그게 발행이다."""
    meta = read_meta(slug)
    paths = [p for p in (meta.get("site"), f"blog-exports/{slug}",
                         meta.get("blogger")) if p and (ROOT / p).exists()]
    if not paths:
        log("올릴 파일을 찾지 못했습니다.")
        return False
    branch = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                            cwd=str(ROOT), capture_output=True, text=True
                            ).stdout.strip()
    for cmd in (["git", "add", *paths],
                ["git", "commit", "-m", f"post: {meta.get('title') or slug}"],
                ["git", "push", "-u", "origin", branch]):
        log("$ " + " ".join(cmd))
        res = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        log((res.stdout + res.stderr).strip())
        if res.returncode != 0:
            # 올릴 변경이 없으면 commit 이 1 로 끝난다. 그건 실패가 아니다.
            if cmd[1] == "commit" and "nothing to commit" in (res.stdout + res.stderr):
                log("바뀐 내용이 없어 커밋은 건너뜁니다.")
                continue
            return False
    log("홈페이지에 반영했습니다. 깃허브 페이지 갱신까지 1~2분 걸립니다.")
    return True


def publish_channel(log, channel, slug):
    cfg = load_config()
    if channel == "site":
        return publish_site(log, slug)
    if channel == "naver":
        return run_script("publish-to-naver.py", log, {"ONLY_SLUG": slug})
    if channel == "tistory":
        blog = cfg.get("TISTORY_BLOG_NAME", "")
        if not blog:
            log("티스토리 블로그 주소를 먼저 설정해 주세요 (대시보드 위쪽 설정 칸).")
            return False
        return run_script("publish-to-tistory.py", log,
                          {"ONLY_SLUG": slug, "TISTORY_BLOG_NAME": blog})
    if channel == "blogger":
        meta = read_meta(slug)
        stem = Path(meta.get("blogger", "")).stem
        if not stem:
            log("이 글에는 블로거용 파일이 연결돼 있지 않습니다 (meta.json 의 blogger).")
            return False
        return run_script("publish-to-blogger.py", log, {"ONLY_SLUG": stem})
    log(f"모르는 채널입니다: {channel}")
    return False


# ------------------------------------------------------------------ 상태
def read_meta(slug):
    path = EXPORT_DIR / slug / "meta.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def published_state():
    out = {}
    for name, key in (("blog-published.json", None), ("blogger-published.json", "blogger")):
        path = ROOT / "data" / name
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if key:
            out[key] = set(data.keys()) if isinstance(data, dict) else set()
        else:
            for channel, posts in data.items():
                out[channel] = set(posts.keys())
    return out


def build_state():
    cfg = load_config()
    done = published_state()

    channels = []
    for spec in CHANNELS:
        cid = spec["id"]
        if cid == "site":
            ready, when = True, ""
        elif cid == "blogger":
            path = session_path("blogger")
            ready = path.exists()
            when = _mtime(path) if ready else ""
        else:
            ready = has_session(cid)
            when = _mtime(session_path(cid)) if ready else ""
        channels.append({**spec, "ready": ready, "saved_at": when})

    posts = []
    if EXPORT_DIR.exists():
        for path in sorted(EXPORT_DIR.iterdir(), reverse=True):
            if not path.is_dir():
                continue
            meta = read_meta(path.name)
            blogger_stem = Path(meta.get("blogger", "")).stem
            posts.append({
                "slug": path.name,
                "title": meta.get("title") or path.name,
                "date": meta.get("date", ""),
                "note": meta.get("note", ""),
                "has": {c: (path / f).exists() for c, f in EXPORT_FILES.items()},
                "site_file": meta.get("site", ""),
                "published": {
                    "naver": path.name in done.get("naver", set()),
                    "tistory": path.name in done.get("tistory", set()),
                    "blogger": bool(blogger_stem) and blogger_stem in done.get("blogger", set()),
                },
            })
    return {"channels": channels, "posts": posts, "config": cfg,
            "job": JOB.snapshot()}


def _mtime(path):
    from datetime import datetime
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except OSError:
        return ""


# ------------------------------------------------------------------ 서버
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        raw = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "dashboard.html").read_bytes(),
                       "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._json(build_state())
        elif self.path == "/api/job":
            self._json(JOB.snapshot())
        elif self.path.startswith("/api/photos"):
            from urllib.parse import parse_qs, urlparse
            slug = (parse_qs(urlparse(self.path).query).get("slug") or [""])[0]
            self._json({"slots": photos_mod.slots(slug)})
        elif self.path.startswith("/api/photo-file"):
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            slug = (q.get("slug") or [""])[0]
            try:
                n = int((q.get("n") or ["0"])[0])
            except ValueError:
                return self._send(400, b"bad n", "text/plain")
            path = photos_mod.image_path(slug, n)
            if not path.exists():
                return self._send(404, b"not found", "text/plain")
            self._send(200, path.read_bytes(), "image/jpeg")
        elif self.path.startswith("/api/session-export"):
            # 깃허브 액션에서도 올리려면 이 값을 secret 에 넣어야 한다.
            # 127.0.0.1 에만 열려 있는 서버라 여기서만 꺼내 준다.
            from urllib.parse import parse_qs, urlparse
            channel = (parse_qs(urlparse(self.path).query).get("channel") or [""])[0]
            path = session_path(channel)
            if channel not in ("naver", "tistory") or not path.exists():
                return self._json({"error": "저장된 세션이 없습니다"}, 404)
            self._json({
                "secret": f"{channel.upper()}_SESSION_JSON",
                "value": path.read_text(encoding="utf-8"),
            })
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "본문을 읽지 못했습니다"}, 400)

        if self.path == "/api/config":
            cfg = load_config()
            cfg.update({k: v for k, v in data.items() if isinstance(v, str)})
            save_config(cfg)
            return self._json({"ok": True, "config": cfg})

        if self.path == "/api/logout":
            channel = data.get("channel", "")
            removed = clear_session(channel)
            return self._json({"ok": True, "removed": removed})

        if self.path == "/api/login":
            channel = data.get("channel", "")
            if channel in ("naver", "tistory"):
                started = JOB.start(
                    f"{channel} 로그인",
                    lambda log: login_mod.browser_login(channel, log))
            elif channel == "blogger":
                cfg = load_config()
                cid = data.get("client_id") or cfg.get("BLOGGER_CLIENT_ID", "")
                sec = data.get("client_secret") or cfg.get("BLOGGER_CLIENT_SECRET", "")
                url = data.get("blog_url") or cfg.get("BLOGGER_BLOG_URL", "")
                if not cid or not sec:
                    return self._json(
                        {"error": "구글 클라우드에서 만든 데스크톱 앱 클라이언트 "
                                  "ID·시크릿이 필요합니다."}, 400)
                cfg.update({"BLOGGER_CLIENT_ID": cid, "BLOGGER_BLOG_URL": url})
                save_config(cfg)
                started = JOB.start(
                    "블로거 인증",
                    lambda log: login_mod.blogger_login(cid, sec, url, log))
            else:
                return self._json({"error": f"모르는 채널: {channel}"}, 400)
            return self._json({"started": started})

        if self.path == "/api/photo":
            slug = data.get("slug", "")
            try:
                n = int(data.get("n", 0))
                raw = base64.b64decode(data.get("data", ""), validate=True)
            except (ValueError, binascii.Error):
                return self._json({"error": "사진을 읽지 못했습니다"}, 400)
            if not slug or not n or not raw:
                return self._json({"error": "글·자리 번호·사진이 모두 필요합니다"}, 400)
            try:
                path = photos_mod.save(slug, n, raw)
            except Exception as exc:
                return self._json({"error": str(exc)}, 400)
            return self._json({"ok": True, "file": path.name})

        if self.path == "/api/photos-apply":
            slug = data.get("slug", "")
            if not slug:
                return self._json({"error": "글을 골라 주세요"}, 400)
            started = JOB.start(f"{slug} 사진 반영",
                                lambda log: photos_mod.apply(slug, log) >= 0)
            return self._json({"started": started})

        if self.path == "/api/publish":
            slug = data.get("slug", "")
            targets = data.get("channels") or []
            if not slug or not targets:
                return self._json({"error": "글과 채널을 골라 주세요"}, 400)

            def work(log):
                results = []
                for channel in targets:
                    log(f"── {channel} ──────────────")
                    ok = publish_channel(log, channel, slug)
                    results.append(ok)
                    log(("완료" if ok else "실패") + f": {channel}")
                    log("")
                return all(results)

            started = JOB.start(f"{slug} 발행", work)
            return self._json({"started": started})

        self._json({"error": "not found"}, 404)

    def log_message(self, *args):
        pass


def main():
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}/"
    print(f"발행 대시보드: {url}")
    print("멈추려면 Ctrl+C 를 누르세요.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n닫았습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
