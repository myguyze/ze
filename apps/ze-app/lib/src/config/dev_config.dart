import 'package:ze_app/src/config/app_config.dart';

/// Compile-time dev defaults injected by `make app` / `make dev-full`.
class DevConfig {
  DevConfig._();

  static const bool enabled =
      bool.fromEnvironment('ZE_DEV', defaultValue: false);

  static const String serverUrl = String.fromEnvironment(
    'ZE_SERVER_URL',
    defaultValue: 'http://localhost:8000',
  );

  static const String apiKey =
      String.fromEnvironment('ZE_API_KEY', defaultValue: '');

  static bool get hasCredentials => enabled && apiKey.isNotEmpty;

  static AppConfig? get fallback =>
      hasCredentials ? AppConfig(serverUrl: serverUrl, apiKey: apiKey) : null;
}
