// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:freezed_annotation/freezed_annotation.dart';

part 'progress_component.freezed.dart';
part 'progress_component.g.dart';

@freezed
class ProgressComponent with _$ProgressComponent {
  const factory ProgressComponent({
    required String title,
    required List<Map<String, dynamic>> steps,
  }) = _ProgressComponent;

  factory ProgressComponent.fromJson(Map<String, dynamic> json) =>
      _$ProgressComponentFromJson(json);
}}