import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../audio/sound_engine.dart';
import '../audio/soundscape.dart';
import '../narration/narrator.dart';
import '../narration/script.dart';

enum SessionStatus { idle, preparing, playing, paused, finished }

/// 세션 전체를 지휘한다. 시계를 돌리고, 시간표대로 멘트를 내보내고,
/// 마지막 구간에서 음악을 서서히 지운다.
class SessionController extends ChangeNotifier {
  SessionController({SoundEngine? engine, Narrator? narrator})
      : _engine = engine ?? SoundEngine(),
        _narrator = narrator ?? Narrator();

  final SoundEngine _engine;
  final Narrator _narrator;

  final Stopwatch _clock = Stopwatch();
  Timer? _ticker;
  List<NarrationCue> _cues = kSleepScript;
  int _nextCue = 0;
  bool _dispatching = false;

  SessionStatus _status = SessionStatus.idle;
  SoundscapeSpec _preset = Soundscapes.moonWave;
  Duration _total = const Duration(minutes: 30);
  Duration _elapsed = Duration.zero;
  bool _narrationEnabled = true;
  double _musicVolume = 0.7;
  double _narrationVolume = 0.85;
  String? _lastSpoken;
  String? _notice;

  SessionStatus get status => _status;
  SoundscapeSpec get preset => _preset;
  Duration get total => _total;
  Duration get elapsed => _elapsed;
  Duration get remaining {
    final Duration left = _total - _elapsed;
    return left.isNegative ? Duration.zero : left;
  }

  double get progress {
    if (_total.inMilliseconds == 0) return 0.0;
    final double p = _elapsed.inMilliseconds / _total.inMilliseconds;
    return p.clamp(0.0, 1.0).toDouble();
  }

  bool get narrationEnabled => _narrationEnabled;
  double get musicVolume => _musicVolume;
  double get narrationVolume => _narrationVolume;
  String? get lastSpoken => _lastSpoken;
  String? get notice => _notice;
  SessionPhase get phase => phaseFor(_elapsed, _total);
  bool get isRunning =>
      _status == SessionStatus.playing || _status == SessionStatus.paused;

  /// 마지막 몇 분에 걸쳐 소리를 지울지. 세션이 짧으면 그만큼 짧아진다.
  Duration get fadeOutWindow {
    final int seconds = (_total.inSeconds * 0.1).round().clamp(45, 180).toInt();
    return Duration(seconds: seconds);
  }

  Future<void> restoreSettings() async {
    try {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      _preset = Soundscapes.byId(prefs.getString('preset') ?? _preset.id);
      _total = Duration(minutes: prefs.getInt('minutes') ?? 30);
      _narrationEnabled = prefs.getBool('narration') ?? true;
      _musicVolume = prefs.getDouble('musicVolume') ?? 0.7;
      _narrationVolume = prefs.getDouble('narrationVolume') ?? 0.85;
    } catch (e) {
      debugPrint('설정을 불러오지 못했습니다: $e');
    }
    await _narrator.init();
    if (!_narrator.koreanAvailable) {
      _notice = '이 기기에 한국어 음성이 없어 멘트는 재생되지 않습니다. '
          '설정 앱에서 한국어 TTS 음성을 내려받으면 바로 들을 수 있어요.';
    }
    notifyListeners();
  }

  Future<void> _save() async {
    try {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      await prefs.setString('preset', _preset.id);
      await prefs.setInt('minutes', _total.inMinutes);
      await prefs.setBool('narration', _narrationEnabled);
      await prefs.setDouble('musicVolume', _musicVolume);
      await prefs.setDouble('narrationVolume', _narrationVolume);
    } catch (e) {
      debugPrint('설정을 저장하지 못했습니다: $e');
    }
  }

  void selectPreset(SoundscapeSpec spec) {
    if (_preset.id == spec.id) return;
    _preset = spec;
    notifyListeners();
    _save();
  }

  void selectDuration(Duration duration) {
    if (_total == duration) return;
    _total = duration;
    notifyListeners();
    _save();
  }

  void setNarrationEnabled(bool enabled) {
    _narrationEnabled = enabled;
    if (!enabled) {
      _narrator.stop();
      _engine.unduck();
    }
    notifyListeners();
    _save();
  }

  void setMusicVolume(double value) {
    _musicVolume = value;
    _engine.setBaseVolume(value);
    notifyListeners();
    _save();
  }

  void setNarrationVolume(double value) {
    _narrationVolume = value;
    _narrator.setVolume(value);
    notifyListeners();
    _save();
  }

  /// 세션 시작. 처음 고른 프리셋은 음원을 굽느라 몇 초 걸릴 수 있어
  /// 그동안 [SessionStatus.preparing] 상태가 된다.
  Future<void> start() async {
    if (_status == SessionStatus.preparing) return;
    _status = SessionStatus.preparing;
    _notice = _narrator.koreanAvailable ? null : _notice;
    notifyListeners();

    try {
      await _narrator.init();
      await _narrator.setVolume(_narrationVolume);
      await _engine.load(_preset);
    } catch (e) {
      debugPrint('세션 준비 실패: $e');
      _status = SessionStatus.idle;
      _notice = '소리를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.';
      notifyListeners();
      return;
    }

    // 세션 도중에 멘트를 다시 켤 수 있으므로 대본은 항상 준비해 두고,
    // 실제로 읽을지는 [_dispatchCue] 에서 판단한다.
    _cues = scriptFor(_total);
    _nextCue = 0;
    _lastSpoken = null;
    _elapsed = Duration.zero;
    _clock
      ..reset()
      ..start();
    await _engine.start(volume: _musicVolume);
    _status = SessionStatus.playing;
    notifyListeners();

    _ticker?.cancel();
    _ticker = Timer.periodic(const Duration(milliseconds: 250), _onTick);
  }

  Future<void> pause() async {
    if (_status != SessionStatus.playing) return;
    _clock.stop();
    _status = SessionStatus.paused;
    await _narrator.stop();
    await _engine.pause();
    notifyListeners();
  }

  Future<void> resume() async {
    if (_status != SessionStatus.paused) return;
    _clock.start();
    _status = SessionStatus.playing;
    await _engine.resume();
    notifyListeners();
  }

  /// 세션을 끝내고 처음 화면 상태로 되돌린다.
  Future<void> stop({bool completed = false}) async {
    _ticker?.cancel();
    _ticker = null;
    _clock
      ..stop()
      ..reset();
    await _narrator.stop();
    await _engine.stop();
    _status = completed ? SessionStatus.finished : SessionStatus.idle;
    if (!completed) {
      _elapsed = Duration.zero;
    }
    notifyListeners();
  }

  void reset() {
    _elapsed = Duration.zero;
    _status = SessionStatus.idle;
    notifyListeners();
  }

  void _onTick(Timer timer) {
    _elapsed = _clock.elapsed;

    if (_elapsed >= _total) {
      unawaited(stop(completed: true));
      return;
    }

    _applyFadeOut();
    _dispatchCue();
    notifyListeners();
  }

  /// 마지막 구간에서 음량을 서서히 0 으로. 잠들기 직전에 소리가
  /// 뚝 끊기면 오히려 깨기 때문에 곡선으로 지운다.
  void _applyFadeOut() {
    final Duration window = fadeOutWindow;
    final Duration left = remaining;
    if (left > window) return;
    final double factor =
        (left.inMilliseconds / window.inMilliseconds).clamp(0.0, 1.0).toDouble();
    _engine.applyFadeOut(factor * factor);
  }

  /// 시간표에서 다음 멘트를 꺼내 읽는다.
  ///
  /// 앞 멘트가 아직 끝나지 않았으면 기다리고, 너무 오래 밀린 멘트는
  /// 건너뛴다. 뒤늦게 몰아서 말하는 것이 더 어색하기 때문이다.
  void _dispatchCue() {
    if (!_narrationEnabled || _dispatching || _nextCue >= _cues.length) return;
    if (_narrator.isSpeaking) return;

    final NarrationCue cue = _cues[_nextCue];
    if (_elapsed.inSeconds < cue.atSeconds) return;

    _nextCue++;
    if (_elapsed.inSeconds - cue.atSeconds > 45) return; // 너무 밀렸으면 생략
    // 페이드아웃이 시작된 뒤에는 멘트를 넣지 않는다.
    if (remaining <= fadeOutWindow) return;

    _dispatching = true;
    _lastSpoken = cue.text;
    _engine.duck();
    unawaited(() async {
      try {
        await _narrator.speak(cue.text);
      } finally {
        _dispatching = false;
        _engine.unduck();
      }
    }());
  }

  @override
  void dispose() {
    _ticker?.cancel();
    _narrator.stop();
    _engine.dispose();
    super.dispose();
  }
}
