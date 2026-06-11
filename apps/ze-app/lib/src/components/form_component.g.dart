// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'form_component.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$FormComponentImpl _$$FormComponentImplFromJson(Map<String, dynamic> json) =>
    _$FormComponentImpl(
      title: json['title'] as String,
      fields: (json['fields'] as List<dynamic>)
          .map((e) => FormField.fromJson(e as Map<String, dynamic>))
          .toList(),
    );

Map<String, dynamic> _$$FormComponentImplToJson(_$FormComponentImpl instance) =>
    <String, dynamic>{
      'title': instance.title,
      'fields': instance.fields,
    };
