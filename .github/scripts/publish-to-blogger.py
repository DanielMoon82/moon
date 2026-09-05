#!/usr/bin/env python3
"""Publish (and update) posts in blogger-posts/ to Google Blogger.

Each post is an HTML file with a small front matter block:

    ---
    title: 글 제목
    labels: 영화, 영화리뷰
    search_description: 검색 결과에 표시될 설명
    status: LIVE
    ---
    <p>본문 HTML…</p>

State lives in data/blogger-published.json so a post is created once and
updated in place afterwards - reruns don't produce duplicates. Run by
.github/workflows/publish-blogger.yml with these secrets:

    BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET,
    BLOGGER_REFRESH_TOKEN, BLOGGER_BLOG_ID
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent.parent
POSTS_DIR = ROOT / "blogger-posts"
STATE_PATH = ROOT / "data" / "blogger-published.json"

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://www.googleapis.com/blogger/v3"
DEFAULT_BLOG_URL = "https://worldtraveler111.blogspot.com"
TIMEOUT = 30


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def parse_post(path):
    """Split '---' front matter from the HTML body."""
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise ValueError(f"{path.name}: missing front matter block")

    _, fm, body = raw.split("---", 2)
    meta = {}
    for line in fm.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"{path.name}: bad front matter line: {line!r}")
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()

    if not meta.get("title"):
        raise ValueError(f"{path.name}: front matter needs a title")

    return meta, body.strip()


def missing_credentials():
    return [
        k for k in ("BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN")
        if not os.environ.get(k)
    ]


def access_token():
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": os.environ["BLOGGER_CLIENT_ID"],
            "client_secret": os.environ["BLOGGER_CLIENT_SECRET"],
            "refresh_token": os.environ["BLOGGER_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=TIMEOUT,
    )
    if resp.status_code != 200:
        detail = resp.text[:300]
        hint = ""
        # OAuth 동의 화면이 '테스트' 상태면 리프레시 토큰이 7일 만에 죽는다.
        # 구글은 invalid_grant 만 돌려주고 이유를 말해 주지 않아서, 여기서 알려준다.
        if "invalid_grant" in detail:
            hint = (
                "\n\n리프레시 토큰이 만료됐거나 취소된 것으로 보입니다."
                "\n구글 클라우드 → API 및 서비스 → OAuth 동의 화면 의 게시 상태가"
                " '테스트' 이면 토큰이 7일 만에 만료됩니다."
                "\n'프로덕션'(앱 게시)으로 바꾼 뒤 토큰을 다시 발급받으세요."
                "\n자세한 절차: blogger-posts/README.md"
            )
        raise SystemExit(f"token refresh failed ({resp.status_code}): {detail}{hint}")
    return resp.json()["access_token"]


def resolve_blog_id(session):
    """Prefer an explicit id, else look the blog up by its URL so the only
    thing that has to be configured is the address itself."""
    blog_id = os.environ.get("BLOGGER_BLOG_ID", "").strip()
    if blog_id:
        return blog_id

    blog_url = os.environ.get("BLOGGER_BLOG_URL", "").strip() or DEFAULT_BLOG_URL
    resp = session.get(f"{API_BASE}/blogs/byurl", params={"url": blog_url}, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise SystemExit(
            f"could not resolve blog id for {blog_url} ({resp.status_code}): {resp.text[:300]}"
        )
    return resp.json()["id"]


def post_payload(meta, body):
    payload = {"title": meta["title"], "content": body}
    labels = [l.strip() for l in meta.get("labels", "").split(",") if l.strip()]
    if labels:
        payload["labels"] = labels
    if meta.get("search_description"):
        payload["customMetaData"] = meta["search_description"]
    return payload


def publish(session, blog_id, meta, body, existing):
    payload = post_payload(meta, body)
    is_draft = meta.get("status", "LIVE").strip().upper() == "DRAFT"

    if existing:
        url = f"{API_BASE}/blogs/{blog_id}/posts/{existing['post_id']}"
        resp = session.put(url, json=payload, timeout=TIMEOUT)
        action = "updated"
    else:
        url = f"{API_BASE}/blogs/{blog_id}/posts/"
        resp = session.post(url, json=payload, params={"isDraft": str(is_draft).lower()}, timeout=TIMEOUT)
        action = "created"

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"{action} failed ({resp.status_code}): {resp.text[:300]}")

    data = resp.json()
    return action, data.get("id"), data.get("url", "")


def main():
    # Until the OAuth secrets are configured this is a no-op rather than a
    # failure, so scheduled runs don't report red every day while setup is
    # still pending.
    absent = missing_credentials()
    if absent:
        print(
            "skipping: Blogger credentials not configured yet (" + ", ".join(absent) + ").\n"
            "See blogger-posts/README.md to finish setup."
        )
        return 0

    only = os.environ.get("ONLY_SLUG", "").strip()

    if not POSTS_DIR.exists():
        print(f"no {POSTS_DIR.name}/ directory, nothing to publish")
        return 0

    files = sorted(p for p in POSTS_DIR.glob("*.html"))
    if only:
        files = [p for p in files if p.stem == only]
        if not files:
            raise SystemExit(f"no post named {only}.html in {POSTS_DIR.name}/")
    if not files:
        print("no posts found, nothing to publish")
        return 0

    state = load_state()
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {access_token()}"
    blog_id = resolve_blog_id(session)

    changed = False
    failures = []
    for path in files:
        slug = path.stem
        try:
            meta, body = parse_post(path)
        except ValueError as exc:
            failures.append(str(exc))
            continue

        digest = hashlib.sha256(
            (meta["title"] + meta.get("labels", "") + body).encode("utf-8")
        ).hexdigest()
        existing = state.get(slug)

        if existing and existing.get("content_hash") == digest:
            print(f"skip {slug}: unchanged ({existing.get('url', '')})")
            continue

        try:
            action, post_id, url = publish(session, blog_id, meta, body, existing)
        except RuntimeError as exc:
            failures.append(f"{slug}: {exc}")
            continue

        state[slug] = {"post_id": post_id, "url": url, "content_hash": digest}
        changed = True
        print(f"{action} {slug}: {url}")

    if changed:
        save_state(state)

    if failures:
        for f in failures:
            print(f"ERROR {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
