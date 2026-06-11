import 'dart:collection';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:ze_app/src/config/app_config.dart';
import 'package:ze_app/src/messages/message.dart';

class MessageRepository {
  final _messages = LinkedHashMap<String, Message>();

  List<Message> get messages =>
      _messages.values.toList()..sort((a, b) => a.createdAt.compareTo(b.createdAt));

  void add(Message message) => _messages[message.id] = message;

  void addAll(List<Message> msgs) {
    for (final m in msgs) {
      _messages[m.id] = m;
    }
  }

  void update(String id, Message updated) {
    if (_messages.containsKey(id)) _messages[id] = updated;
  }

  void clear() => _messages.clear();

  List<String> get unreadAssistantIds => _messages.values
      .where((m) => m.role == MessageRole.assistant && !m.isRead)
      .map((m) => m.id)
      .toList();

  Future<void> loadHistory(AppConfig config) async {
    final since = DateTime.now().subtract(const Duration(days: 7)).toUtc().toIso8601String();
    final uri = Uri.parse('${config.serverUrl}/api/messages').replace(
      queryParameters: {'since': since, 'limit': '200'},
    );
    final response = await http.get(uri, headers: {'X-API-Key': config.apiKey});
    if (response.statusCode != 200) return;
    final data = jsonDecode(response.body) as List<dynamic>;
    addAll(data.map((e) => Message.fromJson(e as Map<String, dynamic>)).toList());
  }

  Future<void> loadEarlier(AppConfig config, DateTime before) async {
    final uri = Uri.parse('${config.serverUrl}/api/messages').replace(
      queryParameters: {
        'before': before.toUtc().toIso8601String(),
        'limit': '200',
      },
    );
    final response = await http.get(uri, headers: {'X-API-Key': config.apiKey});
    if (response.statusCode != 200) return;
    final data = jsonDecode(response.body) as List<dynamic>;
    addAll(data.map((e) => Message.fromJson(e as Map<String, dynamic>)).toList());
  }
}
