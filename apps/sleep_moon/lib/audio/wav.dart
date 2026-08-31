import 'dart:io';
import 'dart:typed_data';

/// 16비트 PCM WAV 파일 writer.
///
/// [samples] 는 채널이 인터리브된 형태여야 한다. (L, R, L, R ...)
/// Int16List 의 바이트 표현은 호스트 엔디안을 따르는데, 플러터가 지원하는
/// 모든 플랫폼(ARM/x86)은 리틀 엔디안이라 WAV 규격과 그대로 일치한다.
Future<void> writeWavFile(
  String path,
  Int16List samples, {
  required int sampleRate,
  required int channels,
}) async {
  final int dataBytes = samples.length * 2;
  final ByteData header = ByteData(44);

  void ascii(int offset, String tag) {
    for (int i = 0; i < tag.length; i++) {
      header.setUint8(offset + i, tag.codeUnitAt(i));
    }
  }

  ascii(0, 'RIFF');
  header.setUint32(4, 36 + dataBytes, Endian.little);
  ascii(8, 'WAVE');
  ascii(12, 'fmt ');
  header.setUint32(16, 16, Endian.little); // PCM 헤더 길이
  header.setUint16(20, 1, Endian.little); // 압축 없음
  header.setUint16(22, channels, Endian.little);
  header.setUint32(24, sampleRate, Endian.little);
  header.setUint32(28, sampleRate * channels * 2, Endian.little); // byte rate
  header.setUint16(32, channels * 2, Endian.little); // block align
  header.setUint16(34, 16, Endian.little); // bits per sample
  ascii(36, 'data');
  header.setUint32(40, dataBytes, Endian.little);

  final File file = File(path);
  await file.parent.create(recursive: true);
  final RandomAccessFile raf = await file.open(mode: FileMode.write);
  try {
    await raf.writeFrom(header.buffer.asUint8List());
    await raf.writeFrom(
      samples.buffer.asUint8List(samples.offsetInBytes, dataBytes),
    );
  } finally {
    await raf.close();
  }
}
