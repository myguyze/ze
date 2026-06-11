// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:freezed_annotation/freezed_annotation.dart';

part 'confirm_component.freezed.dart';
part 'confirm_component.g.dart';

@freezed
class ConfirmComponent with _$ConfirmComponent {
  const factory ConfirmComponent({
    required String prompt,
    required List<Map<String, dynamic>> actions,
  }) = _ConfirmComponent;

  factory ConfirmComponent.fromJson(Map<String, dynamic> json) =>
      _$ConfirmComponentFromJson(json);
}}