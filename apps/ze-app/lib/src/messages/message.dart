enum MessageRole { user, assistant }

class Message {
  Message({
    required this.id,
    required this.role,
    required this.text,
    required this.createdAt,
    this.components = const [],
    this.isRead = false,
  });

  final String id;
  final MessageRole role;
  final String? text;
  final DateTime createdAt;
  final List<Map<String, dynamic>> components;
  final bool isRead;

  factory Message.fromJson(Map<String, dynamic> j) => Message(
        id: j['id'] as String,
        role: j['role'] == 'user' ? MessageRole.user : MessageRole.assistant,
        text: j['text'] as String?,
        createdAt: DateTime.parse(j['created_at'] as String),
        components: (j['components'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>(),
        isRead: j['is_read'] as bool? ?? false,
      );
}
