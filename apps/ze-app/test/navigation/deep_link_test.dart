import 'package:flutter_test/flutter_test.dart';
import 'package:ze_app/src/navigation/deep_link_handler.dart';

void main() {
  test('kAppScheme is ze-app', () {
    expect(kAppScheme, 'ze-app');
  });

  test('handleDeepLink ignores non-ze-app scheme', () {
    // Should not throw.
    handleDeepLink(Uri.parse('https://example.com/navigate?screen=goals'), _NoOpRouter());
  });
}

class _NoOpRouter {
  void go(String path) {}
}
