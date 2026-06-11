// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:freezed_annotation/freezed_annotation.dart';

part 'list_component.freezed.dart';
part 'list_component.g.dart';

@freezed
class ListComponent with _$ListComponent {
  const factory ListComponent({
    required List<Map<String, dynamic>> items,
    String? title,
  }) = _ListComponent;

  factory ListComponent.fromJson(Map<String, dynamic> json) =>
      _$ListComponentFromJson(json);
}}