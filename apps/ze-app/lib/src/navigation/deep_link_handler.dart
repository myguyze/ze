import 'package:go_router/go_router.dart';

const kAppScheme = 'ze-app';

void handleDeepLink(Uri uri, GoRouter router) {
  if (uri.scheme != kAppScheme || uri.host != 'navigate') return;
  // v1: all deep links route to chat. Screen parameter parsed but not acted on.
  router.go('/');
}
