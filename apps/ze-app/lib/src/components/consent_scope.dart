class ConsentScope {
  const ConsentScope({
    required this.id,
    required this.label,
    required this.description,
    this.required = true,
  });

  final String id;
  final String label;
  final String description;
  final bool required;

  factory ConsentScope.fromJson(Map<String, dynamic> json) => ConsentScope(
        id: json['id'] as String,
        label: json['label'] as String,
        description: json['description'] as String,
        required: json['required'] as bool? ?? true,
      );
}