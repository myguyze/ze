// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:freezed_annotation/freezed_annotation.dart';

part 'card_component.freezed.dart';
part 'card_component.g.dart';

@freezed
class CardComponent with _$CardComponent {
  const factory CardComponent({
    required String body,
    String? title,
    String? style,
  }) = _CardComponent;

  factory CardComponent.fromJson(Map<String, dynamic> json) =>
      _$CardComponentFromJson(json);
}}