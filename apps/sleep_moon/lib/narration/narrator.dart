import 'dart:io' show Platform;

import 'package:flutter/foundation.dart';
import 'package:flutter_tts/flutter_tts.dart';

/// 한국어 수면 유도 멘트를 읽어 주는 음성합성 래퍼.
///
/// 음성 파일을 넣지 않고 기기 내장 TTS 를 쓴다. 기기에 한국어 음성이
/// 없으면 [koreanAvailable] 이 false 가 되고, 앱은 음악만 재생한다.
class Narrator {
  final FlutterTts _tts = FlutterTts();

  bool _initialized = false;
  bool _speaking = false;
  bool koreanAvailable = true;

  double _rate = 0.38;
  double _volume = 0.85;

  bool get isSpeaking => _speaking;

  Future<void> init() async {
    if (_initialized) return;
    _initialized = true;
    try {
      if (Platform.isIOS) {
        // 배경음과 함께 나오도록 재생 카테고리를 공유한다.
        await _tts.setSharedInstance(true);
        await _tts.setIosAudioCategory(
          IosTextToSpeechAudioCategory.playback,
          <IosTextToSpeechAudioCategoryOptions>[
            IosTextToSpeechAudioCategoryOptions.mixWithOthers,
          ],
          IosTextToSpeechAudioMode.voicePrompt,
        );
      }
      await _tts.awaitSpeakCompletion(true);
      await _tts.setLanguage('ko-KR');
      // 플랫폼마다 기준이 달라 iOS 는 절반 정도가 사람이 말하는 속도다.
      _rate = Platform.isIOS ? 0.42 : 0.38;
      await _tts.setSpeechRate(_rate);
      await _tts.setPitch(0.92);
      await _tts.setVolume(_volume);

      final dynamic available = await _tts.isLanguageAvailable('ko-KR');
      koreanAvailable = available == true || available == 1;
    } catch (e) {
      debugPrint('TTS 초기화 실패: $e');
      koreanAvailable = false;
    }
  }

  /// 한 줄을 끝까지 읽는다. 읽는 동안 [isSpeaking] 이 true 다.
  Future<void> speak(String text) async {
    if (!koreanAvailable) return;
    _speaking = true;
    try {
      await _tts.speak(text);
    } catch (e) {
      debugPrint('멘트 재생 실패: $e');
    } finally {
      _speaking = false;
    }
  }

  Future<void> setVolume(double volume) async {
    _volume = volume.clamp(0.0, 1.0).toDouble();
    try {
      await _tts.setVolume(_volume);
    } catch (_) {
      // 무시 - 다음 멘트부터 반영된다.
    }
  }

  /// 말하는 속도. 0.3 ~ 0.5 사이가 수면 유도에 알맞다.
  Future<void> setRate(double rate) async {
    _rate = rate.clamp(0.1, 1.0).toDouble();
    try {
      await _tts.setSpeechRate(_rate);
    } catch (_) {}
  }

  Future<void> stop() async {
    _speaking = false;
    try {
      await _tts.stop();
    } catch (_) {}
  }
}
