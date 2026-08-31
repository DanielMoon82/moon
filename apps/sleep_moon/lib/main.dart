import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:just_audio_background/just_audio_background.dart';

import 'app_theme.dart';
import 'session/session_controller.dart';
import 'ui/home_page.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setPreferredOrientations(
    <DeviceOrientation>[DeviceOrientation.portraitUp],
  );
  try {
    // 화면을 끄고 잠들어도 소리가 이어지도록 백그라운드 재생을 켠다.
    await JustAudioBackground.init(
      androidNotificationChannelId: 'com.moon.sleepmoon.audio',
      androidNotificationChannelName: '수면 세션',
      androidNotificationOngoing: true,
      androidStopForegroundOnPause: false,
    );
  } catch (e) {
    debugPrint('백그라운드 재생 초기화 실패: $e');
  }
  runApp(const SleepMoonApp());
}

class SleepMoonApp extends StatefulWidget {
  const SleepMoonApp({super.key});

  @override
  State<SleepMoonApp> createState() => _SleepMoonAppState();
}

class _SleepMoonAppState extends State<SleepMoonApp> {
  final SessionController _controller = SessionController();

  @override
  void initState() {
    super.initState();
    _controller.restoreSettings();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '밤 세션',
      debugShowCheckedModeBanner: false,
      theme: buildNightTheme(),
      home: HomePage(controller: _controller),
    );
  }
}
