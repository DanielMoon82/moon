import 'dart:math' as math;
import 'dart:typed_data';

/// 수면용 사운드스케이프 한 종류의 설계도.
///
/// 오디오 파일을 번들하지 않고 이 명세만으로 앱에서 직접 합성한다.
/// 모든 변조 주기를 루프 길이의 정수 분주로 잡기 때문에 렌더링된 결과는
/// 이음매 없이(seamless) 무한 반복된다.
class SoundscapeSpec {
  const SoundscapeSpec({
    required this.id,
    required this.name,
    required this.description,
    required this.chord,
    required this.padLevel,
    required this.padBrightness,
    required this.noiseLevel,
    required this.noiseCutoff,
    required this.noiseBrown,
    required this.swellCycles,
    required this.swellDepth,
    required this.bellCount,
    required this.bellScale,
    required this.bellLevel,
  });

  /// 캐시 파일 이름과 프리셋 저장에 쓰이는 식별자.
  final String id;
  final String name;
  final String description;

  /// 패드(드론) 화음. Hz 단위.
  final List<double> chord;
  final double padLevel;

  /// 0에 가까우면 배음이 거의 없는 먹먹한 소리, 1에 가까우면 밝은 소리.
  final double padBrightness;

  final double noiseLevel;

  /// 노이즈 1차 저역통과 차단 주파수(Hz).
  final double noiseCutoff;

  /// 0 = 백색에 가까움(비), 1 = 갈색에 가까움(파도/바람).
  final double noiseBrown;

  /// 루프 한 바퀴 동안 밀려왔다 나가는 횟수. 정수라야 이음매가 없다.
  final int swellCycles;
  final double swellDepth;

  /// 루프에 심어 둘 종소리 개수(0이면 없음).
  final int bellCount;
  final List<double> bellScale;
  final double bellLevel;
}

/// 기본 렌더링 파라미터.
///
/// 32kHz / 스테레오 / 120초 루프 = 약 30MB. 앱 내부 캐시에 한 번만 굽는다.
const int kSampleRate = 32000;
const double kLoopSeconds = 120.0;

/// 합성 알고리즘을 고칠 때마다 올린다. 캐시 파일 이름에 들어가서
/// 예전에 구워 둔 음원이 자동으로 무시된다.
const int kRenderVersion = 1;

class Soundscapes {
  Soundscapes._();

  /// 달빛 파도 - 느리게 밀려오는 저역 파도와 따뜻한 Am9 드론.
  static const SoundscapeSpec moonWave = SoundscapeSpec(
    id: 'moon_wave',
    name: '달빛 파도',
    description: '느리게 밀려오는 파도와 낮게 깔린 따뜻한 드론',
    chord: <double>[55.0, 82.41, 110.0, 164.81, 220.0],
    padLevel: 0.30,
    padBrightness: 0.35,
    noiseLevel: 0.42,
    noiseCutoff: 520.0,
    noiseBrown: 0.85,
    swellCycles: 8, // 120초에 8번 = 15초 주기
    swellDepth: 0.72,
    bellCount: 3,
    bellScale: <double>[440.0, 523.25, 659.25, 783.99],
    bellLevel: 0.16,
  );

  /// 밤비 - 창밖 빗소리에 가까운 밝은 노이즈, 드론은 거의 배경.
  static const SoundscapeSpec nightRain = SoundscapeSpec(
    id: 'night_rain',
    name: '밤비',
    description: '창밖에 조용히 내리는 비, 아주 옅은 드론',
    chord: <double>[55.0, 110.0, 146.83, 220.0],
    padLevel: 0.16,
    padBrightness: 0.18,
    noiseLevel: 0.50,
    noiseCutoff: 2600.0,
    noiseBrown: 0.30,
    swellCycles: 5, // 24초 주기의 아주 옅은 흔들림
    swellDepth: 0.22,
    bellCount: 0,
    bellScale: <double>[],
    bellLevel: 0.0,
  );

  /// 깊은 잠 - 거의 소리가 없는 저역 드론. 소음에 예민한 사람용.
  static const SoundscapeSpec deepDrone = SoundscapeSpec(
    id: 'deep_drone',
    name: '깊은 잠',
    description: '숨소리처럼 낮고 단순한 드론, 소리에 예민한 밤에',
    chord: <double>[48.99, 73.42, 97.99, 146.83],
    padLevel: 0.36,
    padBrightness: 0.10,
    noiseLevel: 0.18,
    noiseCutoff: 240.0,
    noiseBrown: 1.0,
    swellCycles: 4, // 30초 주기, 느린 호흡처럼
    swellDepth: 0.55,
    bellCount: 0,
    bellScale: <double>[],
    bellLevel: 0.0,
  );

  static const List<SoundscapeSpec> all = <SoundscapeSpec>[
    moonWave,
    nightRain,
    deepDrone,
  ];

  static SoundscapeSpec byId(String id) {
    for (final SoundscapeSpec spec in all) {
      if (spec.id == id) return spec;
    }
    return moonWave;
  }
}

// ---------------------------------------------------------------------------
// 합성기
// ---------------------------------------------------------------------------

const int _kTableSize = 4096;
final Float64List _sinTable = _buildSinTable();

Float64List _buildSinTable() {
  final Float64List table = Float64List(_kTableSize + 1);
  for (int i = 0; i <= _kTableSize; i++) {
    table[i] = math.sin(2 * math.pi * i / _kTableSize);
  }
  return table;
}

/// 0~1 로 정규화된 위상에 대한 사인값. 선형 보간 테이블이라
/// 샘플마다 [math.sin] 을 부르는 것보다 훨씬 빠르다.
double _sinAt(double phase) {
  final double wrapped = phase - phase.floorToDouble();
  final double x = wrapped * _kTableSize;
  final int i = x.toInt();
  final double frac = x - i;
  return _sinTable[i] + (_sinTable[i + 1] - _sinTable[i]) * frac;
}

/// 명세대로 한 바퀴 도는 스테레오 루프를 만들어 16비트 PCM 으로 돌려준다.
Int16List renderSoundscape(
  SoundscapeSpec spec, {
  int sampleRate = kSampleRate,
  double loopSeconds = kLoopSeconds,
  int seed = 20260831,
}) {
  final int frames = (sampleRate * loopSeconds).round();
  final Float64List left = Float64List(frames);
  final Float64List right = Float64List(frames);

  _renderPad(spec, left, right, sampleRate, loopSeconds);
  _renderNoise(spec, left, right, sampleRate, loopSeconds, seed);
  if (spec.bellCount > 0 && spec.bellScale.isNotEmpty) {
    _renderBells(spec, left, right, sampleRate, loopSeconds, seed + 17);
  }

  return _interleave(left, right);
}

/// 화음 드론. 각 성부는 살짝 디튠된 두 겹으로 쌓고, 성부마다 다른 주기의
/// 아주 느린 볼륨 스웰을 준다.
void _renderPad(
  SoundscapeSpec spec,
  Float64List left,
  Float64List right,
  int sampleRate,
  double loopSeconds,
) {
  if (spec.padLevel <= 0) return;
  final int frames = left.length;
  final double resolution = 1.0 / loopSeconds; // 이 배수여야 이음매가 없다
  final int voices = spec.chord.length;

  for (int v = 0; v < voices; v++) {
    final double pan = voices == 1 ? 0.0 : (v / (voices - 1)) * 2.0 - 1.0;
    final double gainL = math.sqrt((1.0 - pan) / 2.0);
    final double gainR = math.sqrt((1.0 + pan) / 2.0);

    // 낮은 음일수록 크게, 높은 음일수록 옅게.
    final double voiceLevel = spec.padLevel / (1.0 + v * 0.85);
    final int swellCycles = 1 + v; // 성부마다 다른 정수 주기 → 위상이 계속 어긋난다
    final double swellPhase = v * 0.37;

    for (int d = 0; d < 2; d++) {
      final double detune = d == 0 ? 0.9993 : 1.0007;
      final double target = spec.chord[v] * detune;
      final double f = (target / resolution).roundToDouble() * resolution;
      final double inc = f / sampleRate;
      final double inc2 = (f * 2) / sampleRate;
      final double inc3 = (f * 3) / sampleRate;
      final double h2 = 0.22 * spec.padBrightness;
      final double h3 = 0.09 * spec.padBrightness * spec.padBrightness;
      final double layerLevel = voiceLevel * 0.5;

      double p1 = d * 0.25;
      double p2 = 0.0;
      double p3 = 0.5;

      for (int i = 0; i < frames; i++) {
        final double env = 1.0 -
            spec.swellDepth *
                0.45 *
                (0.5 - 0.5 * _sinAt(swellCycles * i / frames + swellPhase));
        final double s =
            (_sinAt(p1) + h2 * _sinAt(p2) + h3 * _sinAt(p3)) * layerLevel * env;
        left[i] += s * gainL;
        right[i] += s * gainR;
        p1 += inc;
        p2 += inc2;
        p3 += inc3;
        if (p1 >= 1.0) p1 -= 1.0;
        if (p2 >= 1.0) p2 -= 1.0;
        if (p3 >= 1.0) p3 -= 1.0;
      }
    }
  }
}

/// 파도/빗소리 층. 채널마다 독립된 노이즈를 만들어 넓게 퍼지게 하고,
/// 끝 2초를 앞머리에 등파워 크로스페이드로 겹쳐 이음매를 없앤다.
void _renderNoise(
  SoundscapeSpec spec,
  Float64List left,
  Float64List right,
  int sampleRate,
  double loopSeconds,
  int seed,
) {
  if (spec.noiseLevel <= 0) return;
  final int frames = left.length;
  final int fade = math.min(2 * sampleRate, frames ~/ 4);
  final int raw = frames + fade;

  final double cutoffAlpha =
      1.0 - math.exp(-2 * math.pi * spec.noiseCutoff / sampleRate);
  // 30Hz 아래 초저역을 걷어낸다. 귀에는 들리지 않으면서 헤드룸만
  // 잡아먹고, 스피커를 불필요하게 흔들기 때문이다.
  final double subsonicAlpha = 1.0 - math.exp(-2 * math.pi * 30.0 / sampleRate);
  // 갈색 노이즈용 적분기의 누설 계수. 낮을수록 저역이 더 뭉친다.
  final double leak = 1.0 - (12.0 / sampleRate);

  for (int ch = 0; ch < 2; ch++) {
    final math.Random rnd = math.Random(seed + ch * 7919);
    final Float64List buffer = Float64List(raw);
    double brown = 0.0;
    double lp = 0.0;
    double lp2 = 0.0;
    double sub = 0.0;

    for (int i = 0; i < raw; i++) {
      final double white = rnd.nextDouble() * 2.0 - 1.0;
      brown = brown * leak + white * 0.02;
      final double mixed =
          white * (1.0 - spec.noiseBrown) + brown * 14.0 * spec.noiseBrown;
      lp += cutoffAlpha * (mixed - lp);
      lp2 += cutoffAlpha * (lp - lp2); // 2차로 걸어 쉭쉭거리는 고역을 더 죽인다
      sub += subsonicAlpha * (lp2 - sub);
      buffer[i] = lp2 - sub;
    }

    final Float64List out = ch == 0 ? left : right;
    final double gain = spec.noiseLevel * 1.6;

    for (int i = 0; i < frames; i++) {
      double v = buffer[i];
      if (i < fade) {
        final double t = i / fade;
        final double a = _sinAt(t * 0.25); // sin(90도 * t)
        final double b = _sinAt(0.25 + t * 0.25); // cos(90도 * t)
        v = buffer[i] * a + buffer[frames + i] * b;
      }
      // 밀려왔다 빠지는 스웰. 정수 주기라 루프 경계에서도 끊기지 않는다.
      final double swell = 1.0 -
          spec.swellDepth *
              (0.5 -
                  0.5 * _sinAt(spec.swellCycles * i / frames + ch * 0.08));
      out[i] += v * gain * swell;
    }
  }
}

/// 가끔 울리는 종소리. 루프 끝을 넘어가는 꼬리는 앞머리로 감아 넣는다.
void _renderBells(
  SoundscapeSpec spec,
  Float64List left,
  Float64List right,
  int sampleRate,
  double loopSeconds,
  int seed,
) {
  final int frames = left.length;
  final math.Random rnd = math.Random(seed);
  final double slot = loopSeconds / spec.bellCount;
  const List<double> partials = <double>[1.0, 2.01, 3.03, 4.97];
  const List<double> partialGains = <double>[1.0, 0.34, 0.14, 0.06];

  for (int b = 0; b < spec.bellCount; b++) {
    final double at = slot * (b + 0.35 + rnd.nextDouble() * 0.4);
    final int start = (at * sampleRate).round() % frames;
    final double freq = spec.bellScale[rnd.nextInt(spec.bellScale.length)] *
        (rnd.nextBool() ? 1.0 : 0.5);
    final double pan = rnd.nextDouble() * 1.2 - 0.6;
    final double gainL = math.sqrt((1.0 - pan) / 2.0);
    final double gainR = math.sqrt((1.0 + pan) / 2.0);
    final double decay = 5.0 + rnd.nextDouble() * 3.0; // 초
    final int length = math.min((decay * 2.2 * sampleRate).round(), frames);
    final double attack = 0.05 * sampleRate;

    for (int i = 0; i < length; i++) {
      final double t = i / sampleRate;
      final double env = math.exp(-t / decay) *
          (i < attack ? i / attack : 1.0);
      double s = 0.0;
      for (int p = 0; p < partials.length; p++) {
        s += partialGains[p] *
            _sinAt(freq * partials[p] * t) *
            math.exp(-t / (decay / (1.0 + p * 0.8)));
      }
      s *= env * spec.bellLevel * 0.5;
      final int idx = (start + i) % frames;
      left[idx] += s * gainL;
      right[idx] += s * gainR;
    }
  }
}

/// 전체 피크를 맞춘 뒤 부드럽게 포화시켜 16비트로 내린다.
Int16List _interleave(Float64List left, Float64List right) {
  final int frames = left.length;
  double peak = 0.0;
  for (int i = 0; i < frames; i++) {
    final double a = left[i].abs();
    final double b = right[i].abs();
    if (a > peak) peak = a;
    if (b > peak) peak = b;
  }
  final double norm = peak > 0 ? 0.82 / peak : 1.0;

  final Int16List out = Int16List(frames * 2);
  for (int i = 0; i < frames; i++) {
    final double l = _softClip(left[i] * norm);
    final double r = _softClip(right[i] * norm);
    out[i * 2] = (l * 32767).round().clamp(-32768, 32767).toInt();
    out[i * 2 + 1] = (r * 32767).round().clamp(-32768, 32767).toInt();
  }
  return out;
}

double _softClip(double x) {
  if (x > -0.7 && x < 0.7) return x;
  final double sign = x < 0 ? -1.0 : 1.0;
  final double a = x.abs();
  return sign * (0.7 + (1.0 - math.exp(-(a - 0.7) * 3.0)) * 0.28);
}
