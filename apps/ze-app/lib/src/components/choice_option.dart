class ChoiceOption {
  const ChoiceOption({
    required this.id,
    required this.label,
    this.description,
    this.recommended = false,
  });

  final String id;
  final String label;
  final String? description;
  final bool recommended;

  factory ChoiceOption.fromJson(Map<String, dynamic> json) => ChoiceOption(
        id: json['id'] as String,
        label: json['label'] as String,
        description: json['description'] as String?,
        recommended: json['recommended'] as bool? ?? false,
      );
}