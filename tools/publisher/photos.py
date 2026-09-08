#!/usr/bin/env python3
"""글에 사진을 끼워 넣는다.

본문에는 사진이 들어갈 자리가 먼저 잡혀 있다. 홈페이지 글은
<div class="slot"> 로, 나머지 세 채널은 [사진 N] 으로 표시해 둔다.
여기서 하는 일은 두 가지다.

  1. 넣을 사진을 posts/images/ 에 규격대로 저장한다.
     EXIF 를 통째로 떨구고(촬영 기기·시각·GPS), 방향값으로만 돌아가
     있는 사진은 화소를 실제로 돌려 둔다. 그러지 않으면 브라우저에
     따라 누워서 나온다.
  2. 네 벌 본문의 자리 표시를 실제 <img> 로 바꾼다.

네이버만 예외다. 스마트에디터는 글자를 타이핑해서 넣기 때문에 사진을
코드로 끼워 넣을 수 없다. 그래서 네이버 원고에는 어느 파일을 어디에
넣어야 하는지만 적어 둔다.
"""
import base64
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
IMAGE_DIR = ROOT / "posts" / "images"
EXPORT_DIR = ROOT / "blog-exports"
SITE_BASE = "https://danielmoon82.github.io/moon/posts/images"

MAX_WIDTH = 1800       # 이보다 넓을 이유가 없다. 파일만 커진다.
JPEG_QUALITY = 82

SLOT_RE = re.compile(
    r'[ \t]*<div class="slot">\s*<b>photo (\d+)</b>\s*<span>(.*?)</span>\s*</div>',
    re.S)
MARK_RE = re.compile(r'\[사진 (\d+)\]\s*([^\n<]*)')


def _meta(slug):
    import json
    path = EXPORT_DIR / slug / "meta.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def stem(slug):
    """이미지 파일 이름의 앞부분. 홈페이지 글 파일 이름을 따른다."""
    site = _meta(slug).get("site", "")
    return Path(site).stem if site else slug


def image_path(slug, n):
    return IMAGE_DIR / f"{stem(slug)}-{n:02d}.jpg"


def slots(slug):
    """자리 표시를 번호 순으로 읽어 온다. 캡션이 곧 alt 텍스트가 된다."""
    site = _meta(slug).get("site", "")
    out = []
    if site and (ROOT / site).exists():
        text = (ROOT / site).read_text(encoding="utf-8")
        for m in SLOT_RE.finditer(text):
            n = int(m.group(1))
            caption = re.sub(r"\s+", " ", re.sub(r"<br\s*/?>", " ", m.group(2))).strip()
            out.append({"n": n, "caption": caption,
                        "ready": image_path(slug, n).exists()})
    # 번호가 아니라 본문에 나온 순서대로 준다. 나중에 자리를 하나 끼워
    # 넣어도 목록이 글 흐름과 어긋나지 않는다.
    return out


def save(slug, n, raw):
    """사진 한 장을 규격대로 저장한다."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        raise SystemExit("Pillow 가 필요합니다:  pip install pillow")

    import io
    img = Image.open(io.BytesIO(raw))
    # EXIF 방향값을 화소에 반영하고, 그 값 자체는 버린다.
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if img.width > MAX_WIDTH:
        height = round(img.height * MAX_WIDTH / img.width)
        img = img.resize((MAX_WIDTH, height), Image.LANCZOS)

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    path = image_path(slug, n)
    # exif 인자를 주지 않으면 메타데이터가 하나도 따라가지 않는다.
    img.save(path, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return path


def _fill_site(slug, text):
    def repl(m):
        n = int(m.group(1))
        if not image_path(slug, n).exists():
            return m.group(0)
        caption = re.sub(r"<br\s*/?>", " ", m.group(2))
        caption = re.sub(r"\s+", " ", caption).strip()
        name = image_path(slug, n).name
        return (f'  <figure>\n'
                f'    <img src="./images/{name}" alt="{caption}">\n'
                f'    <figcaption>{caption}</figcaption>\n'
                f'  </figure>')
    return SLOT_RE.sub(repl, text)


def _fill_html(slug, text):
    """티스토리·블로거용. 자리 표시가 들어 있는 <p> 통째로 바꾼다."""
    def repl(m):
        n = int(m.group(1))
        if not image_path(slug, n).exists():
            return m.group(0)
        caption = m.group(2).strip()
        url = f"{SITE_BASE}/{image_path(slug, n).name}"
        return (f'<p><img src="{url}" alt="{caption}" '
                f'style="max-width:100%;height:auto;" /></p>')
    # 자리 표시를 감싼 점선 상자 <p> 를 통째로 잡는다.
    box = re.compile(r'<p style="padding:20px;border:1px dashed[^>]*>\s*'
                     r'\[사진 (\d+)\]\s*([^<]*?)\s*</p>', re.S)
    return box.sub(repl, text)


def _fill_naver(slug, text):
    """네이버는 사진을 코드로 못 넣는다. 어느 파일인지만 적어 둔다."""
    def repl(m):
        n = int(m.group(1))
        path = image_path(slug, n)
        if not path.exists():
            return m.group(0)
        return f"[사진 {n} → posts/images/{path.name}] {m.group(2).strip()}"
    return MARK_RE.sub(repl, text)


def apply(slug, log=print):
    """네 벌 본문의 자리 표시를 실제 사진으로 바꾼다."""
    meta = _meta(slug)
    done = 0

    jobs = [
        (meta.get("site", ""), _fill_site, "홈페이지"),
        (f"blog-exports/{slug}/티스토리.html", _fill_html, "티스토리"),
        (f"blog-exports/{slug}/블로거.html", _fill_html, "블로거(사본)"),
        (meta.get("blogger", ""), _fill_html, "블로거"),
        (f"blog-exports/{slug}/네이버블로그.txt", _fill_naver, "네이버"),
    ]
    for rel, fn, label in jobs:
        if not rel:
            continue
        path = ROOT / rel
        if not path.exists():
            log(f"{label}: 파일이 없어 건너뜁니다 ({rel})")
            continue
        text = path.read_text(encoding="utf-8")
        filled = fn(slug, text)
        if filled == text:
            log(f"{label}: 바뀐 자리가 없습니다")
            continue
        path.write_text(filled, encoding="utf-8")
        done += 1
        log(f"{label}: 반영했습니다 ({rel})")

    missing = [s["n"] for s in slots(slug) if not s["ready"]]
    if missing:
        log("아직 사진이 없는 자리: " + ", ".join(str(n) for n in missing))
    log("네이버는 에디터에서 사진을 직접 끌어다 넣어야 합니다. "
        "원고에 어느 파일인지 적어 두었습니다.")
    return done


EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}


def bulk(slug, folder, log=print):
    """폴더 안의 사진을 이름 순으로 자리에 하나씩 넣는다.

    휴대폰 사진은 파일 이름이 찍은 순서다. 글의 자리도 대체로 그
    순서를 따라가므로 이렇게만 해도 대부분 맞는다. 틀린 자리는
    대시보드에서 그 자리만 다시 고르면 된다."""
    files = sorted(p for p in Path(folder).iterdir()
                   if p.suffix.lower() in EXTS)
    if not files:
        log(f"{folder} 에서 사진을 찾지 못했습니다.")
        return 0
    targets = slots(slug)
    if len(files) != len(targets):
        log(f"사진 {len(files)}장, 자리 {len(targets)}개 — 개수가 다릅니다. "
            f"앞에서부터 짝을 지어 넣고 남는 쪽은 둡니다.")
    done = 0
    for f, slot in zip(files, targets):
        save(slug, slot["n"], f.read_bytes())
        log(f"  {slot['n']:02d} ← {f.name}   {slot['caption'][:44]}")
        done += 1
    log(f"{done}장 넣었습니다. 자리가 어긋난 게 있으면 대시보드에서 그 자리만 다시 고르세요.")
    return done


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    slug = sys.argv[1]
    args = sys.argv[2:]

    if "--import" in args:
        folder = args[args.index("--import") + 1]
        bulk(slug, folder)

    for s in slots(slug):
        mark = "있음" if s["ready"] else "없음"
        print(f"  {s['n']:02d} [{mark}] {s['caption'][:60]}")

    if "--apply" in args or "--import" in args:
        print()
        apply(slug)
    return 0


if __name__ == "__main__":
    sys.exit(main())
