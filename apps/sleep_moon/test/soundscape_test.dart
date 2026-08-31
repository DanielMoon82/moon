import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:sleep_moon/audio/soundscape.dart';

/// 실제 앱은 32kHz/120초로 굽지만 테스트에서는 짧게 렌더링해 성질만 본다.
const int _sr = 4000;
const double _seconds = 4.0;

void main() {
  group('사운드스케이프 합성', () {
    for (final SoundscapeSpec spec in Soundscapes.all) {
      test('${spec.name}: 소리가 나고, 찌그러지지 않는다', () {
        final Int16List pcm =
            renderSoundscape(spec, sampleRate: _sr, loopSeconds: _seconds);
        expect(pcm.length, (_sr * _seconds).round() * 2);

        int peak = 0;
        double sum = 0;
        for (final int s in pcm) {
          final int a = s.abs();
          if (a > peak) peak = a;
          sum += s * s;
        }
        final double rms = (sum / pcm.length) / (32768 * 32768);
        expect(peak, greaterThan(6000), reason: '너무 작아서 들리지 않습니다');
        expect(peak, lessThanOrEqualTo(32767));
        expect(rms, greaterThan(0.0001), reason: '무음에 가깝습니다');
      });

      test('${spec.name}: 루프 이음매에서 튀지 않는다', () {
        final Int16List pcm =
            renderSoundscape(spec, sampleRate: _sr, loopSeconds: _seconds);
        final int frames = pcm.length ~/ 2;

        // 루프가 다시 시작될 때의 샘플 차이가 평소 샘플 간 변화보다
        // 크면 딸깍 소리가 난다.
        double innerJump = 0;
        for (int i = 1; i < frames; i++) {
          innerJump += (pcm[i * 2] - pcm[(i - 1) * 2]).abs();
        }
        innerJump /= frames - 1;
        final int seamJump = (pcm[0] - pcm[(frames - 1) * 2]).abs();

        expect(seamJump, lessThan((innerJump * 6).clamp(24, 40000)),
            reason: '이음매 ${seamJump}, 평균 ${innerJump.toStringAsFixed(1)}');
      });
    }
  });
}
