// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'form.dart';

// **************************************************************************
// JsonSerializableGenerator
// **************************************************************************

_$FormFieldImpl _$$FormFieldImplFromJson(Map<String, dynamic> json) =>
    _$FormFieldImpl(
      id: json['id'] as String,
      label: json['label'] as String,
      fieldType: json['field_type'] as String? ?? 'text',
      placeholder: json['placeholder'] as String?,
      options:
          (json['options'] as List<dynamic>?)?.map((e) => e as String).toList(),
    );

Map<String, dynamic> _$$FormFieldImplToJson(_$FormFieldImpl instance) =>
    <String, dynamic>{
      'id': instance.id,
      'label': instance.label,
      'field_type': instance.fieldType,
      'placeholder': instance.placeholder,
      'options': instance.options,
    };
