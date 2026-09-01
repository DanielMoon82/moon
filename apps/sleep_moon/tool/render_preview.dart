// 앱과 똑같은 합성기로 루프 음원을 뽑아 WAV 로 저장한다. 소리를 직접
// 들어 보거나, 기기 없이 렌더링 시간을 재 볼 때 쓴다.
//
//   dart run tool/render_preview.dart [출력폴더]
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:sleep_moon/audio/soundscape.dart';
import 'package:sleep_moon/audio/wav.dart';

Future<void> main(List<String> args) async {
  final String outDir = args.isNotEmpty ? args.first : 'build/preview';
  await Directory(outDir).create(recursive: true);

  for (final SoundscapeSpec spec in Soundscapes.all) {
    final Stopwatch watch = Stopwatch()..start();
    final Int16List pcm = renderSoundscape(spec);
    watch.stop();

    int peak = 0;
    double square = 0;
    for (final int s in pcm) {
      final int a = s.abs();
      if (a > peak) peak = a;
      square += (s / 32768) * (s / 32768);
    }
    final double rms = math.sqrt(square / pcm.length);
    final double dbfs = 20 * math.log(math.max(rms, 1e-9)) / math.ln10;

    final String path = '$outDir/${spec.id}.wav';
    await writeWavFile(path, pcm, sampleRate: kSampleRate, channels: 2);
    final int bytes = await File(path).length();

    stdout.writeln('${spec.name.padRight(6)} '
        '렌더 ${watch.elapsedMilliseconds}ms  '
        '피크 ${(peak / 32768 * 100).toStringAsFixed(1)}%  '
        'RMS ${dbfs.toStringAsFixed(1)}dBFS  '
        '${(bytes / 1024 / 1024).toStringAsFixed(1)}MB  -> $path');
  }
}
