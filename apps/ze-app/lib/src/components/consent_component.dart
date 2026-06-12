import 'package:ze_app/src/components/consent_scope.dart';

class ConsentComponent {
  const ConsentComponent({
    required this.id,
    required this.title,
    required this.body,
    required this.scopes,
    this.acceptLabel = 'Allow',
    this.rejectLabel = 'Skip',
  });

  final String id;
  final String title;
  final String body;
  final List<ConsentScope> scopes;
  final String acceptLabel;
  final String rejectLabel;

  factory ConsentComponent.fromJson(Map<String, dynamic> json) => ConsentComponent(
        id: json['id'] as String,
        title: json['title'] as String,
        body: json['body'] as String,
        scopes: (json['scopes'] as List<dynamic>? ?? [])
            .map((scope) => ConsentScope.fromJson(scope as Map<String, dynamic>))
            .toList(),
        acceptLabel: json['accept_label'] as String? ?? 'Allow',
        rejectLabel: json['reject_label'] as String? ?? 'Skip',
      );
}