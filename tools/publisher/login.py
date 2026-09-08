#!/usr/bin/env python3
"""브라우저 창을 띄워 사람이 직접 로그인하게 하고, 그 세션을 저장한다.

네이버도 카카오도 아이디·비밀번호 자동 입력을 막는다. 캡차, 새 기기 확인,
2단계 인증이 번갈아 나오기 때문에 코드로 뚫는 건 오래 못 간다. 그래서
로그인은 사람이 한 번 하고, 그때 받은 쿠키를 저장해 두었다가 발행할 때
재사용한다. 비밀번호는 이 저장소 어디에도 두지 않는다.

    python3 tools/publisher/login.py naver
    python3 tools/publisher/login.py tistory
    python3 tools/publisher/login.py blogger --client-id ... --client-secret ...
"""
import argparse
import http.server
import json
import secrets
import sys
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
from blog_publish_common import UA, save_session, session_path  # noqa: E402

# 로그인이 끝났는지 판정하는 쿠키. 이게 생기면 세션이 선 것이다.
CHANNELS = {
    "naver": {
        "label": "네이버",
        "url": "https://nid.naver.com/nidlogin.login?url=https%3A%2F%2Fblog.naver.com%2F",
        "cookies": {"NID_AUT", "NID_SES"},
    },
    "tistory": {
        "label": "티스토리",
        "url": "https://www.tistory.com/auth/login",
        "cookies": {"TSSESSION"},
    },
}

LOGIN_TIMEOUT_S = 15 * 60


def _has_login_cookies(context, wanted):
    names = {c["name"] for c in context.cookies()}
    return bool(wanted & names)


def browser_login(channel, on_log=print):
    """창을 띄우고, 로그인 쿠키가 생길 때까지 지켜본다."""
    spec = CHANNELS[channel]
    from playwright.sync_api import sync_playwright

    on_log(f"{spec['label']} 로그인 창을 엽니다. 창에서 직접 로그인해 주세요.")
    on_log("2단계 인증·기기 등록까지 마치면 자동으로 저장하고 창을 닫습니다.")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            locale="ko-KR", timezone_id="Asia/Seoul", user_agent=UA,
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.goto(spec["url"], wait_until="domcontentloaded")

        deadline = time.time() + LOGIN_TIMEOUT_S
        ok = False
        while time.time() < deadline:
            try:
                if _has_login_cookies(context, spec["cookies"]):
                    ok = True
                    break
            except Exception:
                # 사용자가 창을 닫으면 쿠키를 못 읽는다. 취소로 본다.
                on_log("창이 닫혔습니다. 로그인을 취소한 것으로 봅니다.")
                return False
            time.sleep(1.5)

        if not ok:
            on_log("시간 안에 로그인이 끝나지 않았습니다.")
            browser.close()
            return False

        # 쿠키가 뜨자마자 저장하면 리다이렉트 도중 값이라 반쪽일 수 있다.
        time.sleep(3)
        path = save_session(channel, context.storage_state())
        on_log(f"{spec['label']} 로그인을 저장했습니다: {path.relative_to(ROOT)}")
        context.close()
        browser.close()
    return True


# ---------------------------------------------------------------- Blogger
# 블로거는 쿠키가 아니라 OAuth 다. 구글 동의 화면을 거쳐 리프레시 토큰을 받고,
# 그걸 저장해 두면 이후로는 창을 띄우지 않고 API 로 바로 올린다.
OAUTH_PORT = 8731
REDIRECT_URI = f"http://localhost:{OAUTH_PORT}/"
SCOPE = "https://www.googleapis.com/auth/blogger"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def blogger_login(client_id, client_secret, blog_url="", on_log=print, open_browser=True):
    received = {}
    state = secrets.token_urlsafe(16)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            received.update({k: v[0] for k, v in params.items()})
            done = "code" in received
            msg = ("인증이 끝났습니다. 이 창을 닫고 대시보드로 돌아가세요."
                   if done else "인증에 실패했습니다. 대시보드를 확인하세요.")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                f"<html><body style='font-family:sans-serif;padding:48px'>"
                f"<h3>{msg}</h3></body></html>".encode("utf-8"))

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("localhost", OAUTH_PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    query = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })
    consent = f"{AUTH_URL}?{query}"
    on_log("구글 동의 화면을 엽니다. 블로그를 쓸 계정으로 로그인해 주세요.")
    on_log(consent)
    if open_browser:
        import webbrowser
        webbrowser.open(consent)

    deadline = time.time() + 300
    while "code" not in received and time.time() < deadline:
        time.sleep(1)
    server.shutdown()

    if "code" not in received:
        on_log("동의 화면에서 코드를 받지 못했습니다.")
        return False
    if received.get("state") != state:
        on_log("state 값이 맞지 않습니다. 중단합니다.")
        return False

    data = urllib.parse.urlencode({
        "code": received["code"],
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()
    try:
        with urllib.request.urlopen(
                urllib.request.Request(TOKEN_URL, data=data), timeout=30) as resp:
            token = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 구글은 400 본문에 진짜 이유를 적어 준다. 버리면 원인을 알 수 없다.
        on_log(f"토큰 교환 실패({exc.code}): {exc.read().decode('utf-8', 'replace')[:400]}")
        return False

    refresh = token.get("refresh_token")
    if not refresh:
        on_log("리프레시 토큰이 오지 않았습니다. 동의 화면에서 '계속'을 눌렀는지 확인하세요.")
        return False

    payload = {
        "BLOGGER_CLIENT_ID": client_id,
        "BLOGGER_CLIENT_SECRET": client_secret,
        "BLOGGER_REFRESH_TOKEN": refresh,
    }
    if blog_url:
        payload["BLOGGER_BLOG_URL"] = blog_url

    path = session_path("blogger")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    on_log(f"구글 블로거 인증을 저장했습니다: {path.relative_to(ROOT)}")
    on_log("OAuth 동의 화면이 '테스트' 상태면 토큰이 7일 만에 만료됩니다. "
           "'프로덕션'으로 게시해 두는 편이 낫습니다.")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("channel", choices=["naver", "tistory", "blogger"])
    ap.add_argument("--client-id", default="")
    ap.add_argument("--client-secret", default="")
    ap.add_argument("--blog-url", default="")
    args = ap.parse_args()

    if args.channel == "blogger":
        if not args.client_id or not args.client_secret:
            print("블로거는 --client-id 와 --client-secret 이 필요합니다.", file=sys.stderr)
            return 2
        ok = blogger_login(args.client_id, args.client_secret, args.blog_url)
    else:
        ok = browser_login(args.channel)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
