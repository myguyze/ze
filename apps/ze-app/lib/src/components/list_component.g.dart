// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'list_component.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$ListComponentImpl _$$ListComponentImplFromJson(Map<String, dynamic> json) =>
    _$ListComponentImpl(
      items: (json['items'] as List<dynamic>)
          .map((e) => ListItem.fromJson(e as Map<String, dynamic>))
          .toList(),
      title: json['title'] as String?,
    );

Map<String, dynamic> _$$ListComponentImplToJson(_$ListComponentImpl instance) =>
    <String, dynamic>{
      'items': instance.items,
      'title': instance.title,
    };
