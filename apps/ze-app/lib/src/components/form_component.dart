import 'package:ze_app/src/components/form.dart';

class FormComponent {
  const FormComponent({
    required this.title,
    required this.fields,
  });

  final String title;
  final List<FormField> fields;

  factory FormComponent.fromJson(Map<String, dynamic> json) => FormComponent(
        title: json['title'] as String,
        fields: (json['fields'] as List<dynamic>? ?? [])
            .map((field) => FormField.fromJson(field as Map<String, dynamic>))
            .toList(),
      );
}