// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:freezed_annotation/freezed_annotation.dart';

part 'form_component.freezed.dart';
part 'form_component.g.dart';

@freezed
class FormComponent with _$FormComponent {
  const factory FormComponent({
    required String title,
    required List<Map<String, dynamic>> fields,
  }) = _FormComponent;

  factory FormComponent.fromJson(Map<String, dynamic> json) =>
      _$FormComponentFromJson(json);
}}