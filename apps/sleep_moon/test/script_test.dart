import 'package:flutter_test/flutter_test.dart';
import 'package:sleep_moon/narration/script.dart';

void main() {
  group('수면 유도 대본', () {
    test('멘트는 시간 순서대로 놓여 있고 25초 이상 벌어져 있다', () {
      for (int i = 1; i < kSleepScript.length; i++) {
        final int gap =
            kSleepScript[i].atSeconds - kSleepScript[i - 1].atSeconds;
        expect(gap, greaterThanOrEqualTo(25),
            reason: '${kSleepScript[i].text} 앞 간격이 너무 좁습니다');
      }
    });

    test('마지막 멘트는 페이드아웃이 시작되기 전에 끝난다', () {
      // SessionController 는 남은 시간이 페이드아웃 구간(전체의 10%,
      // 최대 3분)에 들어오면 멘트를 넣지 않는다. 그 전에 대본이
      // 끝나야 마지막 멘트가 통째로 잘리지 않는다.
      const int total = 30 * 60;
      const int fadeWindow = 180;
      const int fadeStart = total - fadeWindow;
      expect(kSleepScript.last.atSeconds, lessThanOrEqualTo(fadeStart - 30));
    });

    test('짧은 세션은 핵심 멘트만 남기고 길이 안에 들어온다', () {
      final List<NarrationCue> short = scriptFor(const Duration(minutes: 15));
      expect(short.length, lessThan(kSleepScript.length));
      expect(short.every((NarrationCue c) => c.essential), isTrue);
      expect(short.last.atSeconds, lessThan(15 * 60));
    });

    test('20분 이상이면 전체 대본을 그대로 쓴다', () {
      expect(scriptFor(const Duration(minutes: 30)).length,
          kSleepScript.length);
    });

    test('단계는 시간이 흐르는 순서대로 바뀐다', () {
      const Duration total = Duration(minutes: 30);
      expect(phaseFor(Duration.zero, total), SessionPhase.breathing);
      expect(phaseFor(const Duration(minutes: 5), total),
          SessionPhase.relaxing);
      expect(phaseFor(const Duration(minutes: 17), total),
          SessionPhase.countdown);
      expect(phaseFor(const Duration(minutes: 25), total),
          SessionPhase.stillness);
    });
  });
}
