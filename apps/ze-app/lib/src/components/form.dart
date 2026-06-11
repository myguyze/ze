// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:freezed_annotation/freezed_annotation.dart';

part 'form.freezed.dart';
part 'form.g.dart';

@freezed
class FormField with _$FormField {
  const factory FormField({
    required String id,
    required String label,
    @JsonKey(name: 'field_type')  @Default('text')String fieldType,
    String? placeholder,
    List<String>? options,
  }) = _FormField;

  factory FormField.fromJson(Map<String, dynamic> json) =>
      _$FormFieldFromJson(json);
}