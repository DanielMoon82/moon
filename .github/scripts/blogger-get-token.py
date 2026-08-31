#!/usr/bin/env python3
"""One-time helper: get a Blogger refresh token on your own machine.

Run this locally (not in CI) - it opens a browser for Google's consent
screen and prints the refresh token to paste into GitHub Secrets.

    python3 blogger-get-token.py <CLIENT_ID> <CLIENT_SECRET>

Requires the OAuth client to be of type "데스크톱 앱 / Desktop app" so that
http://localhost is an allowed redirect. Full setup: blogger-posts/README.md
"""
import http.server
import secrets
import sys
import threading
import urllib.parse
import webbrowser

import requests

PORT = 8731
REDIRECT_URI = f"http://localhost:{PORT}/"
SCOPE = "https://www.googleapis.com/auth/blogger"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

received = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        received.update({k: v[0] for k, v in params.items()})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        done = "code" in received
        msg = "인증 완료. 이 창을 닫고 터미널로 돌아가세요." if done else "인증 실패. 터미널을 확인하세요."
        self.wfile.write(f"<html><body style='font-family:sans-serif;padding:40px'><h3>{msg}</h3></body></html>".encode())

    def log_message(self, *args):
        pass


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    client_id, client_secret = sys.argv[1], sys.argv[2]
    state = secrets.token_urlsafe(16)

    server = http.server.HTTPServer(("localhost", PORT), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()

    auth_url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })
    print("브라우저에서 구글 로그인 후 권한을 허용하세요.")
    print("창이 안 열리면 아래 주소를 직접 여세요:\n" + auth_url + "\n")
    webbrowser.open(auth_url)

    server.serve_forever_timeout = None
    import time
    for _ in range(300):  # up to 5 minutes
        if received:
            break
        time.sleep(1)

    if received.get("state") != state:
        print("state 불일치 - 다시 시도하세요.", file=sys.stderr)
        return 1
    if "code" not in received:
        print(f"인증 코드를 못 받았습니다: {received}", file=sys.stderr)
        return 1

    resp = requests.post(TOKEN_URL, data={
        "code": received["code"],
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=30)

    if resp.status_code != 200:
        print(f"토큰 교환 실패 ({resp.status_code}): {resp.text[:400]}", file=sys.stderr)
        return 1

    token = resp.json().get("refresh_token")
    if not token:
        print("refresh_token이 없습니다. 구글 계정의 기존 권한을 해제한 뒤 다시 시도하세요.", file=sys.stderr)
        print(resp.text[:400], file=sys.stderr)
        return 1

    print("\n" + "=" * 60)
    print("BLOGGER_REFRESH_TOKEN =")
    print(token)
    print("=" * 60)
    print("이 값을 GitHub 저장소 Secrets에 등록하세요 (외부에 공유하지 마세요).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
