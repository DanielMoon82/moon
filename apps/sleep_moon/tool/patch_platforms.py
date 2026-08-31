#!/usr/bin/env python3
"""flutter create 로 만들어진 플랫폼 스캐폴딩에 이 앱이 필요로 하는 설정을 등록한다.

손으로 쓴 gradle/pbxproj 를 저장소에 넣어 두면 플러터 버전이 올라갈 때마다
깨지기 때문에, 생성된 파일을 그때그때 패치하는 쪽을 택했다.
여러 번 실행해도 결과가 같다(멱등).

등록하는 것:
  안드로이드
    - 백그라운드 재생 권한 3종 + 알림 권한
    - audio_service 의 AudioService / MediaButtonReceiver
    - 안드로이드 11+ 에서 TTS 엔진을 찾기 위한 <queries> 항목
    - MainActivity 를 AudioServiceActivity 상속으로 교체
  iOS
    - UIBackgroundModes 에 audio 추가
"""

from __future__ import annotations

import argparse
import plistlib
import re
import sys
from pathlib import Path

ANDROID_NS = 'xmlns:android="http://schemas.android.com/apk/res/android"'
TOOLS_NS = 'xmlns:tools="http://schemas.android.com/tools"'

PERMISSIONS = [
    "android.permission.WAKE_LOCK",
    "android.permission.FOREGROUND_SERVICE",
    "android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK",
    "android.permission.POST_NOTIFICATIONS",
]

SERVICE_BLOCK = """
        <!-- 화면을 끄고 잠들어도 소리가 이어지도록 하는 재생 서비스 -->
        <service
            android:name="com.ryanheise.audioservice.AudioService"
            android:foregroundServiceType="mediaPlayback"
            android:exported="true"
            tools:ignore="Instantiatable">
            <intent-filter>
                <action android:name="android.media.browse.MediaBrowserService"/>
            </intent-filter>
        </service>

        <receiver
            android:name="com.ryanheise.audioservice.MediaButtonReceiver"
            android:exported="true"
            tools:ignore="Instantiatable">
            <intent-filter>
                <action android:name="android.intent.action.MEDIA_BUTTON"/>
            </intent-filter>
        </receiver>
"""

TTS_QUERY = """    <!-- 안드로이드 11+ 에서 기기의 한국어 TTS 엔진을 찾으려면 필요하다 -->
    <queries>
        <intent>
            <action android:name="android.speech.tts.TTS_SERVICE"/>
        </intent>
    </queries>
"""

TTS_INTENT = """        <intent>
            <action android:name="android.speech.tts.TTS_SERVICE"/>
        </intent>
"""


class Report:
    def __init__(self) -> None:
        self.changed = 0
        self.skipped = 0
        self.missing: list[str] = []

    def add(self, message: str) -> None:
        self.changed += 1
        print(f"  추가: {message}")

    def keep(self, message: str) -> None:
        self.skipped += 1
        print(f"  이미 등록됨: {message}")

    def absent(self, path: Path) -> None:
        self.missing.append(str(path))
        print(f"  건너뜀: {path} 없음")


def patch_manifest(path: Path, report: Report) -> None:
    if not path.exists():
        report.absent(path)
        return
    text = path.read_text(encoding="utf-8")
    original = text

    # 1. tools 네임스페이스 (service 의 tools:ignore 에 필요)
    if TOOLS_NS not in text:
        text = text.replace(ANDROID_NS, f"{ANDROID_NS}\n    {TOOLS_NS}", 1)
        report.add("tools 네임스페이스")
    else:
        report.keep("tools 네임스페이스")

    # 2. 권한. <manifest ...> 여는 태그 바로 뒤에 넣는다.
    open_tag = re.search(r"<manifest\b[^>]*>", text)
    if open_tag is None:
        print(f"  실패: {path} 에서 <manifest> 를 찾지 못했습니다", file=sys.stderr)
        return
    # 이름이 서로의 부분 문자열이라(FOREGROUND_SERVICE 는
    # FOREGROUND_SERVICE_MEDIA_PLAYBACK 안에 들어 있다) 속성째로 찾는다.
    pending = [p for p in PERMISSIONS if f'android:name="{p}"' not in text]
    for name in PERMISSIONS:
        if name not in pending:
            report.keep(f"권한 {name.rsplit('.', 1)[-1]}")
    if pending:
        lines = "".join(
            f'\n    <uses-permission android:name="{name}"/>' for name in pending
        )
        end = open_tag.end()
        text = text[:end] + lines + text[end:]
        for name in pending:
            report.add(f"권한 {name.rsplit('.', 1)[-1]}")

    # 3. 재생 서비스와 미디어 버튼 리시버
    if "com.ryanheise.audioservice.AudioService" not in text:
        text = text.replace("</application>", SERVICE_BLOCK + "    </application>", 1)
        report.add("AudioService / MediaButtonReceiver")
    else:
        report.keep("AudioService / MediaButtonReceiver")

    # 4. TTS 엔진 조회
    if "android.speech.tts.TTS_SERVICE" in text:
        report.keep("TTS 엔진 <queries>")
    elif "<queries>" in text:
        text = text.replace("<queries>", "<queries>\n" + TTS_INTENT.rstrip("\n"), 1)
        report.add("TTS 엔진 <queries> 항목")
    else:
        text = text.replace("</manifest>", TTS_QUERY + "</manifest>", 1)
        report.add("TTS 엔진 <queries> 블록")

    if text != original:
        path.write_text(text, encoding="utf-8")


def patch_main_activity(android_root: Path, report: Report) -> None:
    candidates = list((android_root / "app/src/main/kotlin").rglob("MainActivity.kt"))
    candidates += list((android_root / "app/src/main/java").rglob("MainActivity.kt"))
    candidates += list((android_root / "app/src/main/java").rglob("MainActivity.java"))
    if not candidates:
        report.absent(android_root / "app/src/main/**/MainActivity")
        return

    for path in candidates:
        text = path.read_text(encoding="utf-8")
        if "AudioServiceActivity" in text:
            report.keep(f"{path.name} 의 AudioServiceActivity 상속")
            continue
        patched = text.replace(
            "import io.flutter.embedding.android.FlutterActivity",
            "import com.ryanheise.audioservice.AudioServiceActivity",
        ).replace("FlutterActivity", "AudioServiceActivity")
        if "AudioServiceActivity" not in patched:
            print(f"  실패: {path} 를 자동으로 고치지 못했습니다", file=sys.stderr)
            continue
        path.write_text(patched, encoding="utf-8")
        report.add(f"{path.name} 를 AudioServiceActivity 상속으로 교체")


def patch_info_plist(path: Path, report: Report) -> None:
    if not path.exists():
        report.absent(path)
        return
    with path.open("rb") as handle:
        plist = plistlib.load(handle)

    modes = plist.get("UIBackgroundModes")
    if not isinstance(modes, list):
        modes = []
    if "audio" in modes:
        report.keep("UIBackgroundModes 의 audio")
        return
    modes.append("audio")
    plist["UIBackgroundModes"] = modes
    with path.open("wb") as handle:
        plistlib.dump(plist, handle, sort_keys=False)
    report.add("UIBackgroundModes 에 audio")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(Path(__file__).resolve().parent.parent),
        help="앱 폴더 (기본값: 이 스크립트의 상위 폴더)",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()
    report = Report()

    print("안드로이드")
    patch_manifest(root / "android/app/src/main/AndroidManifest.xml", report)
    patch_main_activity(root / "android", report)
    print("iOS")
    patch_info_plist(root / "ios/Runner/Info.plist", report)

    print()
    print(f"등록 완료: 새로 {report.changed}건, 이미 되어 있던 것 {report.skipped}건")
    if report.missing:
        print("플랫폼 폴더가 아직 없습니다. 먼저 아래를 실행하세요:")
        print("  flutter create . --platforms=android,ios "
              "--org com.moon --project-name sleep_moon")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
