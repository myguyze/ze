import 'package:flutter_test/flutter_test.dart';
import 'package:ze_app/src/ws/ws_protocol.dart';
import 'package:ze_app/src/messages/message.dart';

void main() {
  group('parseInboundFrame', () {
    test('parses message frame', () {
      final raw = '{"type":"message","message":{"id":"1","role":"assistant","text":"Hi","created_at":"2024-01-01T00:00:00Z","components":[],"is_read":false}}';
      final frame = parseInboundFrame(raw);
      expect(frame, isA<MessageFrame>());
      expect((frame as MessageFrame).message.text, 'Hi');
    });

    test('parses typing frame', () {
      final frame = parseInboundFrame('{"type":"typing"}');
      expect(frame, isA<TypingFrame>());
    });

    test('parses refresh frame', () {
      final frame = parseInboundFrame('{"type":"refresh","screen":"goals"}');
      expect(frame, isA<RefreshFrame>());
      expect((frame as RefreshFrame).screen, 'goals');
    });

    test('returns null for unknown type', () {
      final frame = parseInboundFrame('{"type":"unknown_xyz"}');
      expect(frame, isNull);
    });
  });
}
