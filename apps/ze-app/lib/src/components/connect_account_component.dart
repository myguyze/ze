class ConnectAccountComponent {
  const ConnectAccountComponent({
    required this.id,
    required this.provider,
    required this.title,
    required this.description,
    this.status = 'not_connected',
    this.actionLabel = 'Connect',
  });

  final String id;
  final String provider;
  final String title;
  final String description;
  final String status;
  final String actionLabel;

  factory ConnectAccountComponent.fromJson(Map<String, dynamic> json) => ConnectAccountComponent(
        id: json['id'] as String,
        provider: json['provider'] as String,
        title: json['title'] as String,
        description: json['description'] as String,
        status: json['status'] as String? ?? 'not_connected',
        actionLabel: json['action_label'] as String? ?? 'Connect',
      );
}