import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _keyServerUrl = 'ze_server_url';
const _keyApiKey = 'ze_api_key';

class AppConfig {
  AppConfig({required this.serverUrl, required this.apiKey});

  final String serverUrl;
  final String apiKey;

  static const _storage = FlutterSecureStorage();

  static Future<AppConfig?> load() async {
    final url = await _storage.read(key: _keyServerUrl);
    final key = await _storage.read(key: _keyApiKey);
    if (url == null || key == null) return null;
    return AppConfig(serverUrl: url, apiKey: key);
  }

  static Future<void> save({required String serverUrl, required String apiKey}) async {
    await _storage.write(key: _keyServerUrl, value: serverUrl);
    await _storage.write(key: _keyApiKey, value: apiKey);
  }

  static Future<void> clear() async {
    await _storage.delete(key: _keyServerUrl);
    await _storage.delete(key: _keyApiKey);
  }

  String get wsUrl {
    final base = serverUrl.replaceFirst(RegExp(r'^http'), 'ws');
    return '$base/ws?token=$apiKey';
  }
}
