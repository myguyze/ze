class ReviewItem {
  const ReviewItem({
    required this.id,
    required this.label,
    required this.value,
    required this.kind,
    this.plugin,
  });

  final String id;
  final String label;
  final String value;
  final String kind;
  final String? plugin;

  factory ReviewItem.fromJson(Map<String, dynamic> json) => ReviewItem(
        id: json['id'] as String,
        label: json['label'] as String,
        value: json['value'] as String,
        kind: json['kind'] as String,
        plugin: json['plugin'] as String?,
      );
}