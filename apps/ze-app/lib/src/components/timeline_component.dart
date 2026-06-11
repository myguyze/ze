// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:freezed_annotation/freezed_annotation.dart';

part 'timeline_component.freezed.dart';
part 'timeline_component.g.dart';

@freezed
class TimelineComponent with _$TimelineComponent {
  const factory TimelineComponent({
    required List<Map<String, dynamic>> events,
    String? title,
  }) = _TimelineComponent;

  factory TimelineComponent.fromJson(Map<String, dynamic> json) =>
      _$TimelineComponentFromJson(json);
}}