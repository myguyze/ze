// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'metric_component.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$MetricComponentImpl _$$MetricComponentImplFromJson(
        Map<String, dynamic> json) =>
    _$MetricComponentImpl(
      label: json['label'] as String,
      value: json['value'] as String,
      trend: json['trend'] as String?,
      note: json['note'] as String?,
    );

Map<String, dynamic> _$$MetricComponentImplToJson(
        _$MetricComponentImpl instance) =>
    <String, dynamic>{
      'label': instance.label,
      'value': instance.value,
      'trend': instance.trend,
      'note': instance.note,
    };
