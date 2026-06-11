// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'confirm.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$ConfirmActionImpl _$$ConfirmActionImplFromJson(Map<String, dynamic> json) =>
    _$ConfirmActionImpl(
      label: json['label'] as String,
      value: json['value'] as String,
      style: json['style'] as String? ?? 'secondary',
    );

Map<String, dynamic> _$$ConfirmActionImplToJson(_$ConfirmActionImpl instance) =>
    <String, dynamic>{
      'label': instance.label,
      'value': instance.value,
      'style': instance.style,
    };
