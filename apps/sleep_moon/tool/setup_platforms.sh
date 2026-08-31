#!/usr/bin/env bash
# 플랫폼 폴더를 만들고, 이 앱에 필요한 설정을 등록한다.
#
#   bash tool/setup_platforms.sh
#
# 몇 번을 실행해도 결과는 같다. flutter create 가 매니페스트를 다시 덮어써도
# 뒤이어 도는 patch_platforms.py 가 등록을 되살린다.
set -euo pipefail

cd "$(dirname "$0")/.."
APP_DIR="$(pwd)"

if ! command -v flutter >/dev/null 2>&1; then
  echo "flutter 를 찾을 수 없습니다. https://docs.flutter.dev/get-started/install 참고" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 를 찾을 수 없습니다. 설정 등록은 README 의 수동 스니펫을 쓰세요." >&2
  exit 1
fi

echo "[1/4] 플랫폼 폴더 생성 ($APP_DIR)"
flutter create . \
  --platforms=android,ios \
  --org com.moon \
  --project-name sleep_moon

echo "[2/4] 의존성 내려받기"
flutter pub get

echo "[3/4] 백그라운드 재생 / TTS 설정 등록"
python3 tool/patch_platforms.py

echo "[4/4] 테스트"
flutter test

echo
echo "준비가 끝났습니다. 기기를 연결하고 'flutter run' 을 실행하세요."
