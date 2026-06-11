// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:freezed_annotation/freezed_annotation.dart';

part 'table_component.freezed.dart';
part 'table_component.g.dart';

@freezed
class TableComponent with _$TableComponent {
  const factory TableComponent({
    required List<String> headers,
    required List<List<String>> rows,
    String? title,
    String? caption,
  }) = _TableComponent;

  factory TableComponent.fromJson(Map<String, dynamic> json) =>
      _$TableComponentFromJson(json);
}}