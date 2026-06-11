// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:freezed_annotation/freezed_annotation.dart';

part 'progress.freezed.dart';
part 'progress.g.dart';

@freezed
class ProgressStep with _$ProgressStep {
  const factory ProgressStep({
    required String label,
    String? status,
  }) = _ProgressStep;

  factory ProgressStep.fromJson(Map<String, dynamic> json) =>
      _$ProgressStepFromJson(json);
}}