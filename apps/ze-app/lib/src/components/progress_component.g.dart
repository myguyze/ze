// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'progress_component.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$ProgressComponentImpl _$$ProgressComponentImplFromJson(
        Map<String, dynamic> json) =>
    _$ProgressComponentImpl(
      title: json['title'] as String,
      steps: (json['steps'] as List<dynamic>)
          .map((e) => ProgressStep.fromJson(e as Map<String, dynamic>))
          .toList(),
    );

Map<String, dynamic> _$$ProgressComponentImplToJson(
        _$ProgressComponentImpl instance) =>
    <String, dynamic>{
      'title': instance.title,
      'steps': instance.steps,
    };
