// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'confirm_component.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$ConfirmComponentImpl _$$ConfirmComponentImplFromJson(
        Map<String, dynamic> json) =>
    _$ConfirmComponentImpl(
      prompt: json['prompt'] as String,
      actions: (json['actions'] as List<dynamic>)
          .map((e) => ConfirmAction.fromJson(e as Map<String, dynamic>))
          .toList(),
    );

Map<String, dynamic> _$$ConfirmComponentImplToJson(
        _$ConfirmComponentImpl instance) =>
    <String, dynamic>{
      'prompt': instance.prompt,
      'actions': instance.actions,
    };
