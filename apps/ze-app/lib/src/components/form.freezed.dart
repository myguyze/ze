// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'form.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
    'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models');

FormField _$FormFieldFromJson(Map<String, dynamic> json) {
  return _FormField.fromJson(json);
}

/// @nodoc
mixin _$FormField {
  String get id => throw _privateConstructorUsedError;
  String get label => throw _privateConstructorUsedError;
  @JsonKey(name: 'field_type')
  String get fieldType => throw _privateConstructorUsedError;
  String? get placeholder => throw _privateConstructorUsedError;
  List<String>? get options => throw _privateConstructorUsedError;

  /// Serializes this FormField to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of FormField
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $FormFieldCopyWith<FormField> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $FormFieldCopyWith<$Res> {
  factory $FormFieldCopyWith(FormField value, $Res Function(FormField) then) =
      _$FormFieldCopyWithImpl<$Res, FormField>;
  @useResult
  $Res call(
      {String id,
      String label,
      @JsonKey(name: 'field_type') String fieldType,
      String? placeholder,
      List<String>? options});
}

/// @nodoc
class _$FormFieldCopyWithImpl<$Res, $Val extends FormField>
    implements $FormFieldCopyWith<$Res> {
  _$FormFieldCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of FormField
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? label = null,
    Object? fieldType = null,
    Object? placeholder = freezed,
    Object? options = freezed,
  }) {
    return _then(_value.copyWith(
      id: null == id
          ? _value.id
          : id // ignore: cast_nullable_to_non_nullable
              as String,
      label: null == label
          ? _value.label
          : label // ignore: cast_nullable_to_non_nullable
              as String,
      fieldType: null == fieldType
          ? _value.fieldType
          : fieldType // ignore: cast_nullable_to_non_nullable
              as String,
      placeholder: freezed == placeholder
          ? _value.placeholder
          : placeholder // ignore: cast_nullable_to_non_nullable
              as String?,
      options: freezed == options
          ? _value.options
          : options // ignore: cast_nullable_to_non_nullable
              as List<String>?,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$FormFieldImplCopyWith<$Res>
    implements $FormFieldCopyWith<$Res> {
  factory _$$FormFieldImplCopyWith(
          _$FormFieldImpl value, $Res Function(_$FormFieldImpl) then) =
      __$$FormFieldImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call(
      {String id,
      String label,
      @JsonKey(name: 'field_type') String fieldType,
      String? placeholder,
      List<String>? options});
}

/// @nodoc
class __$$FormFieldImplCopyWithImpl<$Res>
    extends _$FormFieldCopyWithImpl<$Res, _$FormFieldImpl>
    implements _$$FormFieldImplCopyWith<$Res> {
  __$$FormFieldImplCopyWithImpl(
      _$FormFieldImpl _value, $Res Function(_$FormFieldImpl) _then)
      : super(_value, _then);

  /// Create a copy of FormField
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? id = null,
    Object? label = null,
    Object? fieldType = null,
    Object? placeholder = freezed,
    Object? options = freezed,
  }) {
    return _then(_$FormFieldImpl(
      id: null == id
          ? _value.id
          : id // ignore: cast_nullable_to_non_nullable
              as String,
      label: null == label
          ? _value.label
          : label // ignore: cast_nullable_to_non_nullable
              as String,
      fieldType: null == fieldType
          ? _value.fieldType
          : fieldType // ignore: cast_nullable_to_non_nullable
              as String,
      placeholder: freezed == placeholder
          ? _value.placeholder
          : placeholder // ignore: cast_nullable_to_non_nullable
              as String?,
      options: freezed == options
          ? _value._options
          : options // ignore: cast_nullable_to_non_nullable
              as List<String>?,
    ));
  }
}

/// @nodoc
@JsonSerializable()
class _$FormFieldImpl implements _FormField {
  const _$FormFieldImpl(
      {required this.id,
      required this.label,
      @JsonKey(name: 'field_type') this.fieldType = 'text',
      this.placeholder,
      final List<String>? options})
      : _options = options;

  factory _$FormFieldImpl.fromJson(Map<String, dynamic> json) =>
      _$$FormFieldImplFromJson(json);

  @override
  final String id;
  @override
  final String label;
  @override
  @JsonKey(name: 'field_type')
  final String fieldType;
  @override
  final String? placeholder;
  final List<String>? _options;
  @override
  List<String>? get options {
    final value = _options;
    if (value == null) return null;
    if (_options is EqualUnmodifiableListView) return _options;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(value);
  }

  @override
  String toString() {
    return 'FormField(id: $id, label: $label, fieldType: $fieldType, placeholder: $placeholder, options: $options)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$FormFieldImpl &&
            (identical(other.id, id) || other.id == id) &&
            (identical(other.label, label) || other.label == label) &&
            (identical(other.fieldType, fieldType) ||
                other.fieldType == fieldType) &&
            (identical(other.placeholder, placeholder) ||
                other.placeholder == placeholder) &&
            const DeepCollectionEquality().equals(other._options, _options));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(runtimeType, id, label, fieldType,
      placeholder, const DeepCollectionEquality().hash(_options));

  /// Create a copy of FormField
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$FormFieldImplCopyWith<_$FormFieldImpl> get copyWith =>
      __$$FormFieldImplCopyWithImpl<_$FormFieldImpl>(this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$FormFieldImplToJson(
      this,
    );
  }
}

abstract class _FormField implements FormField {
  const factory _FormField(
      {required final String id,
      required final String label,
      @JsonKey(name: 'field_type') final String fieldType,
      final String? placeholder,
      final List<String>? options}) = _$FormFieldImpl;

  factory _FormField.fromJson(Map<String, dynamic> json) =
      _$FormFieldImpl.fromJson;

  @override
  String get id;
  @override
  String get label;
  @override
  @JsonKey(name: 'field_type')
  String get fieldType;
  @override
  String? get placeholder;
  @override
  List<String>? get options;

  /// Create a copy of FormField
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$FormFieldImplCopyWith<_$FormFieldImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
