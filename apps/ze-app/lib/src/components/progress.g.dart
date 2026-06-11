// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'progress.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$ProgressStepImpl _$$ProgressStepImplFromJson(Map<String, dynamic> json) =>
    _$ProgressStepImpl(
      label: json['label'] as String,
      status: json['status'] as String? ?? 'pending',
    );

Map<String, dynamic> _$$ProgressStepImplToJson(_$ProgressStepImpl instance) =>
    <String, dynamic>{
      'label': instance.label,
      'status': instance.status,
    };
