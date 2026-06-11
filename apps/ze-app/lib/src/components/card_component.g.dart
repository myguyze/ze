// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'card_component.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$CardComponentImpl _$$CardComponentImplFromJson(Map<String, dynamic> json) =>
    _$CardComponentImpl(
      body: json['body'] as String,
      title: json['title'] as String?,
      style: json['style'] as String? ?? 'info',
    );

Map<String, dynamic> _$$CardComponentImplToJson(_$CardComponentImpl instance) =>
    <String, dynamic>{
      'body': instance.body,
      'title': instance.title,
      'style': instance.style,
    };
