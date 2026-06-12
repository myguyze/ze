class FormField {
  const FormField({
    required this.id,
    required this.label,
    this.fieldType = 'text',
    this.placeholder,
    this.options,
    this.required = true,
    this.helpText,
    this.defaultValue,
  });

  final String id;
  final String label;
  final String fieldType;
  final String? placeholder;
  final List<String>? options;
  final bool required;
  final String? helpText;
  final String? defaultValue;

  factory FormField.fromJson(Map<String, dynamic> json) => FormField(
        id: json['id'] as String,
        label: json['label'] as String,
        fieldType: json['field_type'] as String? ?? 'text',
        placeholder: json['placeholder'] as String?,
        options: (json['options'] as List<dynamic>?)?.map((e) => e.toString()).toList(),
        required: json['required'] as bool? ?? true,
        helpText: json['help_text'] as String?,
        defaultValue: json['default_value'] as String?,
      );
}