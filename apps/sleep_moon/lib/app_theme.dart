import 'package:flutter/material.dart';

/// 밤에 보는 화면이라 전부 어둡게, 흰색은 쓰지 않는다.
class NightColors {
  NightColors._();

  static const Color deep = Color(0xFF05070E);
  static const Color surface = Color(0xFF0C1120);
  static const Color surfaceHigh = Color(0xFF141B2E);
  static const Color moon = Color(0xFFE8E1CD);
  static const Color muted = Color(0xFF8791A8);
  static const Color accent = Color(0xFF6E7FB8);
}

ThemeData buildNightTheme() {
  final ThemeData base = ThemeData.dark(useMaterial3: true);
  return base.copyWith(
    scaffoldBackgroundColor: NightColors.deep,
    colorScheme: base.colorScheme.copyWith(
      primary: NightColors.accent,
      secondary: NightColors.moon,
      surface: NightColors.surface,
    ),
    textTheme: base.textTheme.apply(
      bodyColor: NightColors.moon,
      displayColor: NightColors.moon,
    ),
    sliderTheme: base.sliderTheme.copyWith(
      activeTrackColor: NightColors.accent,
      inactiveTrackColor: NightColors.surfaceHigh,
      thumbColor: NightColors.moon,
      overlayColor: const Color(0x226E7FB8),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((Set<WidgetState> states) =>
          states.contains(WidgetState.selected)
              ? NightColors.moon
              : NightColors.muted),
      trackColor: WidgetStateProperty.resolveWith((Set<WidgetState> states) =>
          states.contains(WidgetState.selected)
              ? NightColors.accent
              : NightColors.surfaceHigh),
    ),
  );
}

/// 밤하늘 그라데이션 배경.
class NightBackground extends StatelessWidget {
  const NightBackground({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: const BoxDecoration(
        gradient: RadialGradient(
          center: Alignment(0.0, -0.55),
          radius: 1.15,
          colors: <Color>[Color(0xFF16203A), NightColors.deep],
          stops: <double>[0.0, 1.0],
        ),
      ),
      child: child,
    );
  }
}
