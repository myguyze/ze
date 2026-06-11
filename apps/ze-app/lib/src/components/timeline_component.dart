// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:freezed_annotation/freezed_annotation.dart';
import 'package:ze_app/src/components/timeline.dart';

part 'timeline_component.freezed.dart';
part 'timeline_component.g.dart';

@freezed
class TimelineComponent with _$TimelineComponent {
  const factory TimelineComponent({
    required List<TimelineEvent> events,
    String? title,
  }) = _TimelineComponent;

  factory TimelineComponent.fromJson(Map<String, dynamic> json) =>
      _$TimelineComponentFromJson(json);
}