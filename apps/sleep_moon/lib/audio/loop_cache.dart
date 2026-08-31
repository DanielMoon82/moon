import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import 'soundscape.dart';
import 'wav.dart';

/// 합성한 루프 음원을 앱 내부 저장소에 구워 두고 재사용한다.
///
/// 첫 실행 때 프리셋마다 한 번씩만 렌더링하면 그 뒤로는 즉시 재생된다.
class LoopCache {
  LoopCache._();

  static Future<Directory> _dir() async {
    final Directory base = await getApplicationSupportDirectory();
    final Directory dir = Directory('${base.path}/soundscapes');
    if (!dir.existsSync()) {
      await dir.create(recursive: true);
    }
    return dir;
  }

  static String _fileName(SoundscapeSpec spec) =>
      '${spec.id}_v$kRenderVersion'
      '_${kSampleRate}_${kLoopSeconds.round()}.wav';

  /// 캐시에 파일이 있으면 그 경로를, 없으면 별도 아이솔레이트에서 구운 뒤
  /// 경로를 돌려준다. 렌더링 중에도 UI 는 멈추지 않는다.
  static Future<String> ensure(SoundscapeSpec spec) async {
    final Directory dir = await _dir();
    final File file = File('${dir.path}/${_fileName(spec)}');
    if (file.existsSync() && await file.length() > 44) {
      return file.path;
    }
    // 렌더링이 중간에 끊겨도 반쪽짜리 파일이 남지 않도록 임시 이름으로 굽는다.
    final String tempPath = '${file.path}.part';
    final String written = await compute<_RenderRequest, String>(
      _renderToFile,
      _RenderRequest(specId: spec.id, path: tempPath),
    );
    await File(written).rename(file.path);
    await _pruneStale(dir);
    return file.path;
  }

  /// 예전 버전으로 구워 둔 음원 정리.
  static Future<void> _pruneStale(Directory dir) async {
    final List<String> valid =
        Soundscapes.all.map(_fileName).toList(growable: false);
    for (final FileSystemEntity entity in dir.listSync()) {
      if (entity is! File) continue;
      final String name = entity.uri.pathSegments.last;
      if (!valid.contains(name)) {
        try {
          await entity.delete();
        } catch (_) {
          // 지우지 못해도 재생에는 지장이 없다.
        }
      }
    }
  }

  static Future<bool> isReady(SoundscapeSpec spec) async {
    final Directory dir = await _dir();
    final File file = File('${dir.path}/${_fileName(spec)}');
    return file.existsSync() && await file.length() > 44;
  }
}

class _RenderRequest {
  const _RenderRequest({required this.specId, required this.path});

  final String specId;
  final String path;
}

/// 아이솔레이트 진입점. 최상위 함수여야 [compute] 로 넘길 수 있다.
Future<String> _renderToFile(_RenderRequest request) async {
  final SoundscapeSpec spec = Soundscapes.byId(request.specId);
  final Int16List pcm = renderSoundscape(spec);
  await writeWavFile(request.path, pcm, sampleRate: kSampleRate, channels: 2);
  return request.path;
}
