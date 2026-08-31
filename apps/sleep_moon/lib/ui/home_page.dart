import 'package:flutter/material.dart';

import '../app_theme.dart';
import '../audio/soundscape.dart';
import '../session/session_controller.dart';
import 'session_page.dart';

/// 세션을 고르는 첫 화면. 길이, 소리, 멘트 세 가지만 고르면 된다.
class HomePage extends StatelessWidget {
  const HomePage({super.key, required this.controller});

  final SessionController controller;

  static const List<Duration> _durations = <Duration>[
    Duration(minutes: 15),
    Duration(minutes: 30),
    Duration(minutes: 60),
  ];

  Future<void> _start(BuildContext context) async {
    final NavigatorState navigator = Navigator.of(context);
    await controller.start();
    if (controller.status == SessionStatus.playing) {
      await navigator.push(
        MaterialPageRoute<void>(
          builder: (_) => SessionPage(controller: controller),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: NightBackground(
        child: SafeArea(
          child: AnimatedBuilder(
            animation: controller,
            builder: (BuildContext context, _) {
              final bool preparing =
                  controller.status == SessionStatus.preparing;
              return ListView(
                padding: const EdgeInsets.fromLTRB(24, 32, 24, 40),
                children: <Widget>[
                  Text(
                    '밤 세션',
                    style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                          fontWeight: FontWeight.w600,
                          letterSpacing: 2,
                        ),
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    '수면 유도 멘트와 음악이 함께 흐르고,\n끝나기 전 소리는 스스로 사라집니다.',
                    style: TextStyle(
                      color: NightColors.muted,
                      height: 1.6,
                    ),
                  ),
                  if (controller.notice != null) ...<Widget>[
                    const SizedBox(height: 20),
                    _NoticeCard(text: controller.notice!),
                  ],
                  const SizedBox(height: 36),
                  const _SectionLabel('길이'),
                  const SizedBox(height: 12),
                  Row(
                    children: _durations.map((Duration d) {
                      final bool selected = controller.total == d;
                      return Padding(
                        padding: const EdgeInsets.only(right: 10),
                        child: _Chip(
                          label: '${d.inMinutes}분',
                          selected: selected,
                          onTap: () => controller.selectDuration(d),
                        ),
                      );
                    }).toList(),
                  ),
                  const SizedBox(height: 32),
                  const _SectionLabel('소리'),
                  const SizedBox(height: 12),
                  ...Soundscapes.all.map(
                    (SoundscapeSpec spec) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: _SoundscapeCard(
                        spec: spec,
                        selected: controller.preset.id == spec.id,
                        onTap: () => controller.selectPreset(spec),
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  _NarrationToggle(controller: controller),
                  const SizedBox(height: 40),
                  _StartButton(
                    preparing: preparing,
                    onPressed: preparing ? null : () => _start(context),
                  ),
                  const SizedBox(height: 16),
                  Center(
                    child: Text(
                      preparing ? '소리를 준비하고 있습니다…' : '이어폰보다 스피커를 낮게 두는 편이 좋습니다',
                      style: const TextStyle(
                        color: NightColors.muted,
                        fontSize: 12,
                      ),
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text,
      style: const TextStyle(
        color: NightColors.muted,
        fontSize: 12,
        letterSpacing: 4,
      ),
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 12),
        decoration: BoxDecoration(
          color: selected ? NightColors.surfaceHigh : Colors.transparent,
          borderRadius: BorderRadius.circular(30),
          border: Border.all(
            color: selected
                ? NightColors.moon.withValues(alpha: 0.55)
                : NightColors.surfaceHigh,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: selected ? NightColors.moon : NightColors.muted,
            fontSize: 15,
          ),
        ),
      ),
    );
  }
}

class _SoundscapeCard extends StatelessWidget {
  const _SoundscapeCard({
    required this.spec,
    required this.selected,
    required this.onTap,
  });

  final SoundscapeSpec spec;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
        decoration: BoxDecoration(
          color: selected ? NightColors.surfaceHigh : NightColors.surface,
          borderRadius: BorderRadius.circular(18),
          border: Border.all(
            color: selected
                ? NightColors.moon.withValues(alpha: 0.4)
                : Colors.transparent,
          ),
        ),
        child: Row(
          children: <Widget>[
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    spec.name,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    spec.description,
                    style: const TextStyle(
                      color: NightColors.muted,
                      fontSize: 13,
                      height: 1.4,
                    ),
                  ),
                ],
              ),
            ),
            AnimatedOpacity(
              duration: const Duration(milliseconds: 200),
              opacity: selected ? 1 : 0,
              child: const Icon(
                Icons.circle,
                size: 10,
                color: NightColors.moon,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NarrationToggle extends StatelessWidget {
  const _NarrationToggle({required this.controller});

  final SessionController controller;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
      decoration: BoxDecoration(
        color: NightColors.surface,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Row(
        children: <Widget>[
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text('수면 유도 멘트', style: TextStyle(fontSize: 15)),
                SizedBox(height: 4),
                Text(
                  '호흡, 이완, 카운트다운 순으로 안내합니다',
                  style: TextStyle(color: NightColors.muted, fontSize: 12),
                ),
              ],
            ),
          ),
          Switch(
            value: controller.narrationEnabled,
            onChanged: controller.setNarrationEnabled,
          ),
        ],
      ),
    );
  }
}

class _StartButton extends StatelessWidget {
  const _StartButton({required this.preparing, required this.onPressed});

  final bool preparing;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 58,
      child: FilledButton(
        onPressed: onPressed,
        style: FilledButton.styleFrom(
          backgroundColor: NightColors.surfaceHigh,
          foregroundColor: NightColors.moon,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(29),
          ),
        ),
        child: preparing
            ? const SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  color: NightColors.moon,
                ),
              )
            : const Text(
                '시작하기',
                style: TextStyle(fontSize: 16, letterSpacing: 3),
              ),
      ),
    );
  }
}

class _NoticeCard extends StatelessWidget {
  const _NoticeCard({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: NightColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: NightColors.surfaceHigh),
      ),
      child: Text(
        text,
        style: const TextStyle(
          color: NightColors.muted,
          fontSize: 13,
          height: 1.5,
        ),
      ),
    );
  }
}
