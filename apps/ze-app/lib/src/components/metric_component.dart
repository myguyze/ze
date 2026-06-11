// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:freezed_annotation/freezed_annotation.dart';

part 'metric_component.freezed.dart';
part 'metric_component.g.dart';

@freezed
class MetricComponent with _$MetricComponent {
  const factory MetricComponent({
    required String label,
    required String value,
    String? trend,
    String? note,
  }) = _MetricComponent;

  factory MetricComponent.fromJson(Map<String, dynamic> json) =>
      _$MetricComponentFromJson(json);
}}