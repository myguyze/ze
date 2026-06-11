// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'timeline_component.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$TimelineComponentImpl _$$TimelineComponentImplFromJson(
        Map<String, dynamic> json) =>
    _$TimelineComponentImpl(
      events: (json['events'] as List<dynamic>)
          .map((e) => TimelineEvent.fromJson(e as Map<String, dynamic>))
          .toList(),
      title: json['title'] as String?,
    );

Map<String, dynamic> _$$TimelineComponentImplToJson(
        _$TimelineComponentImpl instance) =>
    <String, dynamic>{
      'events': instance.events,
      'title': instance.title,
    };
