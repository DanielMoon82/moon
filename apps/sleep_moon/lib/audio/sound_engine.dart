import 'dart:async';

import 'package:just_audio/just_audio.dart';
import 'package:just_audio_background/just_audio_background.dart';

import 'loop_cache.dart';
import 'soundscape.dart';

/// 배경음 재생 담당. 루프 재생, 서서히 볼륨 바꾸기, 멘트가 나올 때
/// 잠깐 음량을 낮추는 더킹까지 여기서 처리한다.
class SoundEngine {
  final AudioPlayer _player = AudioPlayer();

  Timer? _fadeTimer;
  double _baseVolume = 0.7;
  double _currentVolume = 0.0;
  bool _ducked = false;
  String? _loadedSpecId;

  double get baseVolume => _baseVolume;
  bool get isPlaying => _player.playing;

  /// 프리셋 음원을 준비한다. 캐시에 없으면 여기서 합성이 일어나
  /// 기기에 따라 수 초 걸릴 수 있다.
  Future<void> load(SoundscapeSpec spec) async {
    if (_loadedSpecId == spec.id) return;
    final String path = await LoopCache.ensure(spec);
    await _player.setAudioSource(
      AudioSource.uri(
        Uri.file(path),
        tag: MediaItem(
          id: spec.id,
          title: spec.name,
          album: '수면 세션',
          artist: '30분 수면 유도',
        ),
      ),
      preload: true,
    );
    await _player.setLoopMode(LoopMode.one);
    _loadedSpecId = spec.id;
  }

  Future<void> start({required double volume}) async {
    _baseVolume = volume;
    await _applyVolume(0.0);
    await _player.play();
    // 갑자기 소리가 튀지 않게 3초에 걸쳐 올린다.
    fadeTo(volume, const Duration(seconds: 3));
  }

  Future<void> pause() async {
    _fadeTimer?.cancel();
    await _player.pause();
  }

  Future<void> resume() async {
    await _applyVolume(0.0);
    await _player.play();
    fadeTo(_ducked ? _baseVolume * _kDuckRatio : _baseVolume,
        const Duration(seconds: 2));
  }

  Future<void> stop() async {
    _fadeTimer?.cancel();
    await _player.stop();
  }

  /// 사용자가 볼륨 슬라이더를 움직였을 때.
  Future<void> setBaseVolume(double volume) async {
    _baseVolume = volume;
    if (_fadeTimer?.isActive ?? false) return;
    await _applyVolume(_ducked ? volume * _kDuckRatio : volume);
  }

  /// 세션 마지막 구간에서 서서히 사라지게 만들 때 쓴다. 0~1 배율.
  Future<void> applyFadeOut(double factor) async {
    _fadeTimer?.cancel();
    final double target = _baseVolume * factor.clamp(0.0, 1.0).toDouble();
    await _applyVolume(_ducked ? target * _kDuckRatio : target);
  }

  /// 멘트가 시작될 때 음악을 뒤로 물린다.
  void duck() {
    if (_ducked) return;
    _ducked = true;
    fadeTo(_baseVolume * _kDuckRatio, const Duration(milliseconds: 900));
  }

  void unduck() {
    if (!_ducked) return;
    _ducked = false;
    fadeTo(_baseVolume, const Duration(milliseconds: 2200));
  }

  /// [duration] 동안 [target] 볼륨까지 매끄럽게 이동.
  void fadeTo(double target, Duration duration) {
    _fadeTimer?.cancel();
    final double from = _currentVolume;
    final double to = target.clamp(0.0, 1.0).toDouble();
    final int steps = (duration.inMilliseconds / 40).ceil().clamp(1, 100000).toInt();
    int step = 0;
    _fadeTimer = Timer.periodic(const Duration(milliseconds: 40), (Timer t) {
      step++;
      final double p = (step / steps).clamp(0.0, 1.0).toDouble();
      // 귀에 자연스럽도록 제곱 곡선으로.
      final double eased = from + (to - from) * (p * p * (3 - 2 * p));
      _applyVolume(eased);
      if (step >= steps) {
        t.cancel();
      }
    });
  }

  Future<void> _applyVolume(double v) async {
    _currentVolume = v.clamp(0.0, 1.0).toDouble();
    try {
      await _player.setVolume(_currentVolume);
    } catch (_) {
      // 플레이어가 이미 정리된 경우 무시.
    }
  }

  Future<void> dispose() async {
    _fadeTimer?.cancel();
    await _player.dispose();
  }

  static const double _kDuckRatio = 0.42;
}
