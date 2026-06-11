import 'package:flutter_test/flutter_test.dart';
import 'package:ze_app/src/ws/ws_protocol.dart';

void main() {
  test('RefreshFrame carries screen name', () {
    final f = RefreshFrame(screen: 'goals');
    expect(f.screen, 'goals');
  });
}
