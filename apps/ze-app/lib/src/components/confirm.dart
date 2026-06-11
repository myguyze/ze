// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:freezed_annotation/freezed_annotation.dart';

part 'confirm.freezed.dart';
part 'confirm.g.dart';

@freezed
class ConfirmAction with _$ConfirmAction {
  const factory ConfirmAction({
    required String label,
    required String value,
    String? style,
  }) = _ConfirmAction;

  factory ConfirmAction.fromJson(Map<String, dynamic> json) =>
      _$ConfirmActionFromJson(json);
}}