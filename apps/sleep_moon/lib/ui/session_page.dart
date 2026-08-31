import 'dart:async';

import 'package:flutter/material.dart';

import '../app_theme.dart';
import '../session/session_controller.dart';
import 'progress_ring.dart';

/// 세션이 흐르는 동안 보는 화면. 20초 동안 손대지 않으면 화면이
/// 거의 검게 어두워지고, 아무 곳이나 누르면 다시 밝아진다.
class SessionPage extends StatefulWidget {
  const SessionPage({super.key, required this.controller});

  final SessionController controller;

  @override
  State<SessionPage> createState() => _SessionPageState();
}

class _SessionPageState extends State<SessionPage> {
  static const Duration _dimAfter = Duration(seconds: 20);

  Timer? _dimTimer;
  bool _dimmed = false;

  @override
  void initState() {
    super.initState();
    _scheduleDim();
  }

  @override
  void dispose() {
    _dimTimer?.cancel();
    super.dispose();
  }

  void _scheduleDim() {
    _dimTimer?.cancel();
    _dimTimer = Timer(_dimAfter, () {
      if (mounted) setState(() => _dimmed = true);
    });
  }

  void _wake() {
    if (_dimmed) {
      setState(() => _dimmed = false);
    }
    _scheduleDim();
  }

  Future<void> _finish() async {
    final NavigatorState navigator = Navigator.of(context);
    await widget.controller.stop();
    if (navigator.mounted) navigator.pop();
  }

  void _openVolumeSheet() {
    _wake();
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: NightColors.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (BuildContext context) => AnimatedBuilder(
        animation: widget.controller,
        builder: (BuildContext context, _) => Padding(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 36),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Text('음악', style: TextStyle(color: NightColors.muted)),
              Slider(
                value: widget.controller.musicVolume,
                onChanged: widget.controller.setMusicVolume,
              ),
              const SizedBox(height: 8),
              const Text('멘트', style: TextStyle(color: NightColors.muted)),
              Slider(
                value: widget.controller.narrationVolume,
                onChanged: widget.controller.setNarrationVolume,
              ),
              const SizedBox(height: 8),
              Row(
                children: <Widget>[
                  const Expanded(child: Text('수면 유도 멘트')),
                  Switch(
                    value: widget.controller.narrationEnabled,
                    onChanged: widget.controller.setNarrationEnabled,
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _format(Duration d) {
    final int minutes = d.inMinutes;
    final int seconds = d.inSeconds % 60;
    return '$minutes:${seconds.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final SessionController c = widget.controller;
    return Scaffold(
      body: Listener(
        behavior: HitTestBehavior.opaque,
        onPointerDown: (_) => _wake(),
        child: Stack(
          children: <Widget>[
            NightBackground(
              child: SafeArea(
                child: AnimatedBuilder(
                  animation: c,
                  builder: (BuildContext context, _) {
                    final bool done = c.status == SessionStatus.finished;
                    return Column(
                      children: <Widget>[
                        const SizedBox(height: 12),
                        Align(
                          alignment: Alignment.centerRight,
                          child: IconButton(
                            onPressed: _openVolumeSheet,
                            icon: const Icon(Icons.tune,
                                color: NightColors.muted),
                          ),
                        ),
                        const Spacer(),
                        ProgressRing(
                          progress: c.progress,
                          size: 260,
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            children: <Widget>[
                              Text(
                                done ? '0:00' : _format(c.remaining),
                                style: const TextStyle(
                                  fontSize: 46,
                                  fontWeight: FontWeight.w200,
                                  letterSpacing: 2,
                                ),
                              ),
                              const SizedBox(height: 8),
                              Text(
                                done ? '잘 자요' : c.phase.label,
                                style: const TextStyle(
                                  color: NightColors.muted,
                                  fontSize: 13,
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 40),
                        SizedBox(
                          height: 72,
                          child: Padding(
                            padding:
                                const EdgeInsets.symmetric(horizontal: 32),
                            child: AnimatedSwitcher(
                              duration: const Duration(milliseconds: 700),
                              child: Text(
                                c.lastSpoken ?? '',
                                key: ValueKey<String>(c.lastSpoken ?? ''),
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  color: NightColors.moon
                                      .withValues(alpha: 0.55),
                                  fontSize: 14,
                                  height: 1.6,
                                ),
                              ),
                            ),
                          ),
                        ),
                        const Spacer(),
                        if (!done)
                          Row(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: <Widget>[
                              _RoundButton(
                                icon: c.status == SessionStatus.paused
                                    ? Icons.play_arrow
                                    : Icons.pause,
                                onTap: () {
                                  _wake();
                                  if (c.status == SessionStatus.paused) {
                                    c.resume();
                                  } else {
                                    c.pause();
                                  }
                                },
                              ),
                              const SizedBox(width: 24),
                              _RoundButton(
                                icon: Icons.close,
                                onTap: _finish,
                              ),
                            ],
                          )
                        else
                          TextButton(
                            onPressed: _finish,
                            child: const Text('닫기',
                                style: TextStyle(color: NightColors.muted)),
                          ),
                        const SizedBox(height: 48),
                      ],
                    );
                  },
                ),
              ),
            ),
            IgnorePointer(
              child: AnimatedOpacity(
                duration: const Duration(milliseconds: 1400),
                opacity: _dimmed ? 0.88 : 0.0,
                child: const ColoredBox(
                  color: Colors.black,
                  child: SizedBox.expand(),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RoundButton extends StatelessWidget {
  const _RoundButton({required this.icon, required this.onTap});

  final IconData icon;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: 64,
        height: 64,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: NightColors.surface,
          border: Border.all(color: NightColors.surfaceHigh),
        ),
        child: Icon(icon, color: NightColors.moon, size: 26),
      ),
    );
  }
}
