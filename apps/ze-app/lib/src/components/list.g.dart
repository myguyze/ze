// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'list.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$ListItemImpl _$$ListItemImplFromJson(Map<String, dynamic> json) =>
    _$ListItemImpl(
      text: json['text'] as String,
      subtext: json['subtext'] as String?,
      status: json['status'] as String?,
    );

Map<String, dynamic> _$$ListItemImplToJson(_$ListItemImpl instance) =>
    <String, dynamic>{
      'text': instance.text,
      'subtext': instance.subtext,
      'status': instance.status,
    };
