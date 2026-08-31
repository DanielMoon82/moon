/// 수면 유도 멘트 한 줄과 그 줄이 나오는 시각.
class NarrationCue {
  const NarrationCue(this.atSeconds, this.text, {this.essential = false});

  /// 30분 세션 기준 시작 후 경과 초.
  final int atSeconds;
  final String text;

  /// 짧은 세션(20분 미만)에서도 남기는 핵심 멘트인지.
  final bool essential;
}

/// 세션의 흐름. 화면에 지금 어느 단계인지 보여주는 데 쓴다.
enum SessionPhase {
  breathing('호흡을 고르는 시간'),
  relaxing('몸을 풀어놓는 시간'),
  letting('생각을 내려놓는 시간'),
  imagery('조용한 밤을 그리는 시간'),
  countdown('깊이 내려가는 시간'),
  stillness('고요');

  const SessionPhase(this.label);
  final String label;
}

/// 30분 세션용 전체 대본.
///
/// 앞 20분에 걸쳐 호흡 - 이완 - 내려놓기 - 심상 - 카운트다운 순으로 이어지고,
/// 그 뒤로는 음악만 남는다. 멘트 사이 간격은 최소 25초 이상 벌려 두어
/// 말이 겹치거나 조급하게 들리지 않게 했다.
const List<NarrationCue> kSleepScript = <NarrationCue>[
  // 호흡
  NarrationCue(20, '편안한 자세로 누우세요. 지금부터 삼십 분 동안, 아무것도 하지 않아도 괜찮습니다.',
      essential: true),
  NarrationCue(52, '눈을 부드럽게 감고, 어깨의 힘을 천천히 내려놓으세요.', essential: true),
  NarrationCue(88, '코로 숨을 들이마십니다. 하나, 둘, 셋, 넷.', essential: true),
  NarrationCue(120, '잠시 멈추고, 길게 내쉽니다. 하나, 둘, 셋, 넷, 다섯, 여섯.', essential: true),
  NarrationCue(156, '한 번 더. 천천히 들이마시고, 더 길게 내쉬세요.'),
  NarrationCue(192, '이제 호흡은 몸에 맡깁니다. 애쓰지 않아도 숨은 알아서 이어집니다.',
      essential: true),

  // 이완
  NarrationCue(225, '이마의 주름을 폅니다. 미간이 조금씩 넓어집니다.'),
  NarrationCue(265, '눈꺼풀이 무거워집니다. 눈 뒤쪽까지 힘이 풀립니다.', essential: true),
  NarrationCue(305, '턱에 힘을 뺍니다. 이 사이가 벌어지고, 혀가 아래로 내려앉습니다.'),
  NarrationCue(348, '어깨가 아래로, 바닥 쪽으로 흘러내립니다.', essential: true),
  NarrationCue(392, '팔을 따라 손끝까지, 따뜻한 무게가 내려갑니다.'),
  NarrationCue(436, '가슴이 천천히 오르내립니다. 그저 지켜보기만 하세요.', essential: true),
  NarrationCue(480, '배가 부드러워집니다. 하루 종일 조여 있던 곳이 풀립니다.'),
  NarrationCue(525, '등과 허리가 닿은 자리를 느껴 보세요. 몸을 완전히 맡겨도 좋습니다.'),
  NarrationCue(570, '다리에서 힘이 빠지고, 발끝까지 무거워집니다.', essential: true),

  // 내려놓기
  NarrationCue(620, '오늘 하루는 여기까지입니다. 지금은 아무것도 정리하지 않아도 됩니다.',
      essential: true),
  NarrationCue(668, '생각이 떠오르면 밀어내지 말고, 그냥 지나가게 두세요.'),
  NarrationCue(720, '떠오른 생각은 물 위의 나뭇잎처럼 천천히 흘러갑니다.', essential: true),

  // 심상
  NarrationCue(782, '당신은 지금 조용한 방에 있습니다. 창밖은 깊은 밤입니다.', essential: true),
  NarrationCue(842, '숨을 쉴 때마다 몸이 조금씩 더 아래로 가라앉습니다.'),
  NarrationCue(902, '따뜻하고 안전합니다. 지금 여기서는 아무 일도 일어나지 않습니다.',
      essential: true),

  // 카운트다운
  NarrationCue(952, '이제 열부터 하나까지 세겠습니다. 숫자가 줄어들수록 더 깊이 내려갑니다.',
      essential: true),
  NarrationCue(984, '열. 아홉.'),
  NarrationCue(1016, '여덟. 일곱.'),
  NarrationCue(1050, '여섯. 다섯.', essential: true),
  NarrationCue(1086, '넷. 셋.'),
  NarrationCue(1124, '둘.'),
  NarrationCue(1162, '하나. 가장 깊은 곳입니다.', essential: true),

  // 고요
  NarrationCue(1235, '이제 아무 말도 필요하지 않습니다. 소리에 몸을 맡기세요.', essential: true),
  NarrationCue(1385, '괜찮습니다. 그대로 잠들어도 됩니다.'),
  NarrationCue(1560, '여기서부터는 조용히 곁에 있겠습니다.'),
];

/// 세션 길이에 맞춘 대본을 만든다.
///
/// 20분보다 짧은 세션은 핵심 멘트만 남기고 시간표를 앞당겨,
/// 카운트다운이 잘리지 않게 한다. 30분보다 긴 세션은 원본 그대로 쓰고
/// 남는 시간은 음악만 흐른다.
List<NarrationCue> scriptFor(Duration total) {
  const int reference = 30 * 60;
  final int seconds = total.inSeconds;
  if (seconds >= 20 * 60) return kSleepScript;

  final double scale = (seconds * 0.62) / reference;
  return kSleepScript
      .where((NarrationCue c) => c.essential)
      .map((NarrationCue c) => NarrationCue(
            (c.atSeconds * scale).round(),
            c.text,
            essential: true,
          ))
      .toList(growable: false);
}

/// 경과 시간에 해당하는 단계. 짧은 세션에서도 비율이 맞도록
/// 전체 길이에 맞춰 경계를 늘리고 줄인다.
SessionPhase phaseFor(Duration elapsed, Duration total) {
  if (total.inSeconds == 0) return SessionPhase.breathing;
  final double ratio = elapsed.inSeconds / total.inSeconds;
  if (ratio < 0.11) return SessionPhase.breathing;
  if (ratio < 0.33) return SessionPhase.relaxing;
  if (ratio < 0.42) return SessionPhase.letting;
  if (ratio < 0.52) return SessionPhase.imagery;
  if (ratio < 0.68) return SessionPhase.countdown;
  return SessionPhase.stillness;
}
