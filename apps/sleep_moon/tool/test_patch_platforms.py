#!/usr/bin/env python3
"""patch_platforms.py 검증. 플러터가 만드는 것과 같은 모양의 스캐폴딩을
임시 폴더에 세워 두고 패치를 돌린 뒤 결과를 확인한다.

    python3 tool/test_patch_platforms.py
"""

from __future__ import annotations

import plistlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
NS = "{http://schemas.android.com/apk/res/android}"

MANIFEST = """<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <application
        android:label="sleep_moon"
        android:name="${applicationName}"
        android:icon="@mipmap/ic_launcher">
        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:launchMode="singleTop"
            android:theme="@style/LaunchTheme">
            <intent-filter>
                <action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/>
            </intent-filter>
        </activity>
        <meta-data
            android:name="flutterEmbedding"
            android:value="2" />
    </application>
    <queries>
        <intent>
            <action android:name="android.intent.action.PROCESS_TEXT"/>
            <data android:mimeType="text/plain"/>
        </intent>
    </queries>
</manifest>
"""

MAIN_ACTIVITY = """package com.moon.sleep_moon

import io.flutter.embedding.android.FlutterActivity

class MainActivity: FlutterActivity()
"""

INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
\t<key>CFBundleDisplayName</key>
\t<string>Sleep Moon</string>
\t<key>UILaunchStoryboardName</key>
\t<string>LaunchScreen</string>
</dict>
</plist>
"""

REQUIRED_PERMISSIONS = {
    "android.permission.WAKE_LOCK",
    "android.permission.FOREGROUND_SERVICE",
    "android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK",
    "android.permission.POST_NOTIFICATIONS",
}

failures: list[str] = []


def check(condition: bool, label: str) -> None:
    if condition:
        print(f"  OK   {label}")
    else:
        print(f"  실패 {label}")
        failures.append(label)


def scaffold(root: Path, *, manifest: str = MANIFEST, with_queries: bool = True) -> None:
    android = root / "android/app/src/main"
    (android / "kotlin/com/moon/sleep_moon").mkdir(parents=True)
    text = manifest
    if not with_queries:
        start = text.index("    <queries>")
        end = text.index("</queries>") + len("</queries>\n")
        text = text[:start] + text[end:]
    (android / "AndroidManifest.xml").write_text(text, encoding="utf-8")
    (android / "kotlin/com/moon/sleep_moon/MainActivity.kt").write_text(
        MAIN_ACTIVITY, encoding="utf-8"
    )
    (root / "ios/Runner").mkdir(parents=True)
    (root / "ios/Runner/Info.plist").write_text(INFO_PLIST, encoding="utf-8")


def run_patch(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HERE / "patch_platforms.py"), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def inspect(root: Path) -> tuple[ET.Element, dict, str]:
    tree = ET.parse(root / "android/app/src/main/AndroidManifest.xml")
    plist = plistlib.loads((root / "ios/Runner/Info.plist").read_bytes())
    activity = (
        root / "android/app/src/main/kotlin/com/moon/sleep_moon/MainActivity.kt"
    ).read_text(encoding="utf-8")
    return tree.getroot(), plist, activity


def main() -> int:
    print("기본 스캐폴딩")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        scaffold(root)
        first = run_patch(root)
        check(first.returncode == 0, "패치가 성공으로 끝난다")

        manifest, plist, activity = inspect(root)
        perms = {e.get(NS + "name") for e in manifest.findall("uses-permission")}
        actions = {a.get(NS + "name") for a in manifest.iter("action")}
        services = {s.get(NS + "name") for s in manifest.iter("service")}
        receivers = {r.get(NS + "name") for r in manifest.iter("receiver")}

        check(REQUIRED_PERMISSIONS <= perms, "권한 4종이 모두 선언된다")
        check(
            "com.ryanheise.audioservice.AudioService" in services,
            "AudioService 가 등록된다",
        )
        check(
            next(iter(s.get(NS + "foregroundServiceType") for s in manifest.iter("service")))
            == "mediaPlayback",
            "서비스가 mediaPlayback 포그라운드 타입이다",
        )
        check(
            "com.ryanheise.audioservice.MediaButtonReceiver" in receivers,
            "MediaButtonReceiver 가 등록된다",
        )
        check("android.speech.tts.TTS_SERVICE" in actions, "TTS 엔진 조회가 등록된다")
        check(
            "android.intent.action.PROCESS_TEXT" in actions,
            "원래 있던 queries 항목이 남아 있다",
        )
        check("AudioServiceActivity" in activity, "MainActivity 가 교체된다")
        check(
            "io.flutter.embedding.android.FlutterActivity" not in activity,
            "예전 import 가 남지 않는다",
        )
        check(plist.get("UIBackgroundModes") == ["audio"], "iOS 백그라운드 오디오가 켜진다")
        check(plist.get("CFBundleDisplayName") == "Sleep Moon", "plist 의 다른 키가 보존된다")

        before = (root / "android/app/src/main/AndroidManifest.xml").read_text(
            encoding="utf-8"
        )
        second = run_patch(root)
        after = (root / "android/app/src/main/AndroidManifest.xml").read_text(
            encoding="utf-8"
        )
        check(second.returncode == 0 and before == after, "두 번 돌려도 결과가 같다")

    print("queries 블록이 없는 스캐폴딩")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        scaffold(root, with_queries=False)
        run_patch(root)
        manifest, _, _ = inspect(root)
        actions = {a.get(NS + "name") for a in manifest.iter("action")}
        check(manifest.find("queries") is not None, "queries 블록을 새로 만든다")
        check("android.speech.tts.TTS_SERVICE" in actions, "TTS 엔진 조회가 등록된다")

    print("권한 이름이 서로의 부분 문자열인 경우")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        partial = MANIFEST.replace(
            "    <application",
            '    <uses-permission '
            'android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK"/>\n'
            "    <application",
            1,
        )
        scaffold(root, manifest=partial)
        run_patch(root)
        manifest, _, _ = inspect(root)
        perms = [e.get(NS + "name") for e in manifest.findall("uses-permission")]
        check(
            "android.permission.FOREGROUND_SERVICE" in perms,
            "MEDIA_PLAYBACK 만 있어도 FOREGROUND_SERVICE 를 따로 넣는다",
        )
        check(len(perms) == len(set(perms)), "권한이 중복되지 않는다")

    print()
    if failures:
        print(f"실패 {len(failures)}건: {', '.join(failures)}")
        return 1
    print("모두 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
