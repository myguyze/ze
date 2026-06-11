// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'table_component.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$TableComponentImpl _$$TableComponentImplFromJson(Map<String, dynamic> json) =>
    _$TableComponentImpl(
      headers:
          (json['headers'] as List<dynamic>).map((e) => e as String).toList(),
      rows: (json['rows'] as List<dynamic>)
          .map((e) => (e as List<dynamic>).map((e) => e as String).toList())
          .toList(),
      title: json['title'] as String?,
      caption: json['caption'] as String?,
    );

Map<String, dynamic> _$$TableComponentImplToJson(
        _$TableComponentImpl instance) =>
    <String, dynamic>{
      'headers': instance.headers,
      'rows': instance.rows,
      'title': instance.title,
      'caption': instance.caption,
    };
