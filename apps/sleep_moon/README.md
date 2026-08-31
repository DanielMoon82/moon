# 밤 세션 (sleep_moon)

수면 유도 멘트와 수면 유도 음악을 함께 틀어 주는 플러터 앱.
기본값은 30분이며, 끝나기 전 마지막 3분 동안 소리가 스스로 사라진다.

## 핵심 아이디어

**오디오 파일을 하나도 넣지 않는다.** 음악은 앱이 직접 합성하고, 멘트는
기기에 있는 한국어 TTS 음성이 읽는다. 그래서

- 앱 용량이 늘지 않고, 음원 저작권 문제가 없다
- 완전히 오프라인으로 동작한다
- 대본과 화음을 코드에서 바로 고칠 수 있다

## 어떻게 동작하나

### 1. 음악 - 실시간 합성 후 캐시

`lib/audio/soundscape.dart` 가 프리셋 명세대로 **120초짜리 스테레오 루프**를
만든다. 구성은 세 층이다.

| 층 | 내용 |
| --- | --- |
| 패드 | 살짝 디튠한 두 겹의 화음 드론, 성부마다 다른 주기의 느린 볼륨 스웰 |
| 노이즈 | 백색~갈색 노이즈를 2차 저역통과로 걸러 만든 파도/빗소리, 30Hz 아래는 제거 |
| 종소리 | 배음 4개를 지수 감쇠시킨 은은한 벨 (프리셋에 따라 없음) |

이음매 없이 반복되도록 두 가지를 지켰다.

- 모든 주파수와 변조 주기를 **루프 길이의 정수 분주**로 스냅한다.
  그러면 루프 끝의 파형이 시작과 정확히 맞물린다.
- 무작위인 노이즈 층만은 끝 2초를 앞머리에 **등파워 크로스페이드**로 겹친다.

결과는 첫 실행 때 한 번만 렌더링해 앱 내부 저장소에 WAV 로 굽고
(`lib/audio/loop_cache.dart`), 그 뒤로는 즉시 재생한다. 렌더링은
별도 아이솔레이트에서 돌아 화면이 멈추지 않는다.

프리셋 세 가지: **달빛 파도**, **밤비**, **깊은 잠**.

### 2. 멘트 - 시간표대로 읽어 주는 대본

`lib/narration/script.dart` 에 30분 기준 대본이 초 단위 시간표로 들어 있다.

```
호흡(0~3분) → 이완/바디스캔(3~9분) → 내려놓기(9~12분)
→ 심상(12~15분) → 카운트다운(15~19분) → 고요(19분~)
```

멘트가 나올 때는 음악을 42% 로 낮췄다가(더킹) 끝나면 2.2초에 걸쳐
되돌린다. 앞 멘트가 아직 끝나지 않았으면 다음 멘트를 미루고,
45초 넘게 밀린 멘트는 건너뛴다. 뒤늦게 몰아 말하는 편이 더 어색하기 때문이다.

15분 세션을 고르면 핵심 멘트만 남기고 시간표를 앞당겨 카운트다운이
잘리지 않게 한다.

### 3. 세션 - 시계와 페이드아웃

`lib/session/session_controller.dart` 가 250ms 마다 시계를 확인하며
멘트를 내보내고, 남은 시간이 페이드아웃 구간(전체의 10%, 최대 3분)에
들어오면 음량을 제곱 곡선으로 지운다. 소리가 뚝 끊기면 오히려 깨기 때문이다.

## 실행 방법

이 폴더에는 `lib/`, `test/`, `pubspec.yaml` 만 들어 있다.
플랫폼 폴더는 각자 환경에서 만든다.

```bash
cd apps/sleep_moon
flutter create . --platforms=android,ios --org com.moon --project-name sleep_moon
flutter pub get
flutter run
```

버전 충돌이 나면 `flutter pub upgrade --major-versions` 로 한 번 정리하면 된다.

### 안드로이드 추가 설정

화면을 끄고 잠들어도 소리가 이어지려면 `android/app/src/main/AndroidManifest.xml`
에 아래를 넣는다.

```xml
<manifest xmlns:tools="http://schemas.android.com/tools" ...>
  <uses-permission android:name="android.permission.WAKE_LOCK"/>
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE"/>
  <uses-permission android:name="android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK"/>

  <application ...>
    <!-- ... 기존 activity ... -->
    <service android:name="com.ryanheise.audioservice.AudioService"
             android:foregroundServiceType="mediaPlayback"
             android:exported="true" tools:ignore="Instantiatable">
      <intent-filter>
        <action android:name="android.media.browse.MediaBrowserService"/>
      </intent-filter>
    </service>
    <receiver android:name="com.ryanheise.audioservice.MediaButtonReceiver"
              android:exported="true" tools:ignore="Instantiatable">
      <intent-filter>
        <action android:name="android.intent.action.MEDIA_BUTTON"/>
      </intent-filter>
    </receiver>
  </application>
</manifest>
```

`MainActivity` 는 `FlutterActivity` 대신
`com.ryanheise.audioservice.AudioServiceActivity` 를 상속해야 한다.

### iOS 추가 설정

`ios/Runner/Info.plist` 에:

```xml
<key>UIBackgroundModes</key>
<array>
  <string>audio</string>
</array>
```

기기에 한국어 시리 음성이 없으면 멘트가 나오지 않는다.
설정 > 손쉬운 사용 > 음성 콘텐츠에서 한국어 음성을 내려받으면 된다.
안드로이드는 설정 > 접근성 > TTS 출력에서 한국어 음성을 받는다.
음성이 없는 기기에서는 앱이 첫 화면에 안내를 띄우고 음악만 재생한다.

## 테스트

```bash
flutter test
```

- `test/script_test.dart` - 멘트 간격, 순서, 짧은 세션 압축, 단계 전환
- `test/soundscape_test.dart` - 합성 결과의 음량과 **루프 이음매 연속성**
  (딸깍 소리가 나지 않는지 샘플 차이로 검사)

## 고쳐 쓰기

- **멘트 바꾸기**: `lib/narration/script.dart` 의 `kSleepScript` 에서
  시각과 문장을 바꾼다. 간격은 25초 이상 두는 것을 권한다(테스트가 잡아 준다).
- **소리 바꾸기**: `lib/audio/soundscape.dart` 의 `SoundscapeSpec` 을 새로
  하나 만들고 `Soundscapes.all` 에 넣는다. 화음(`chord`)은 Hz 배열이다.
  합성 방식을 고쳤다면 `kRenderVersion` 을 올려 예전 캐시를 버리게 한다.
- **말 속도**: `lib/narration/narrator.dart` 의 `setSpeechRate` 값.
  안드로이드 0.38, iOS 0.42 가 수면 유도에 알맞은 느린 속도다.

## 폴더

```
lib/
  main.dart                       앱 진입점, 백그라운드 재생 초기화
  app_theme.dart                  밤 전용 어두운 테마
  audio/
    soundscape.dart               프리셋 명세 + 합성기
    wav.dart                      16비트 PCM WAV writer
    loop_cache.dart               아이솔레이트 렌더링 + 캐시
    sound_engine.dart             재생, 페이드, 더킹
  narration/
    script.dart                   수면 유도 대본과 단계
    narrator.dart                 한국어 TTS 래퍼
  session/
    session_controller.dart       세션 시계와 지휘
  ui/
    home_page.dart                길이 / 소리 / 멘트 고르기
    session_page.dart             진행 화면, 20초 뒤 자동 암전
    progress_ring.dart            남은 시간 링
```
