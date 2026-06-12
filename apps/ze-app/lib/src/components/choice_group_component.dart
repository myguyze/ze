import 'package:ze_app/src/components/choice_option.dart';

class ChoiceGroupComponent {
  const ChoiceGroupComponent({
    required this.id,
    required this.title,
    required this.options,
    this.allowMultiple = false,
    this.description,
    this.submitLabel = 'Continue',
  });

  final String id;
  final String title;
  final List<ChoiceOption> options;
  final bool allowMultiple;
  final String? description;
  final String submitLabel;

  factory ChoiceGroupComponent.fromJson(Map<String, dynamic> json) => ChoiceGroupComponent(
        id: json['id'] as String,
        title: json['title'] as String,
        options: (json['options'] as List<dynamic>? ?? [])
            .map((option) => ChoiceOption.fromJson(option as Map<String, dynamic>))
            .toList(),
        allowMultiple: json['allow_multiple'] as bool? ?? false,
        description: json['description'] as String?,
        submitLabel: json['submit_label'] as String? ?? 'Continue',
      );
}