// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'form_component.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
    'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models');

FormComponent _$FormComponentFromJson(Map<String, dynamic> json) {
  return _FormComponent.fromJson(json);
}

/// @nodoc
mixin _$FormComponent {
  String get title => throw _privateConstructorUsedError;
  List<FormField> get fields => throw _privateConstructorUsedError;

  /// Serializes this FormComponent to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of FormComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $FormComponentCopyWith<FormComponent> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $FormComponentCopyWith<$Res> {
  factory $FormComponentCopyWith(
          FormComponent value, $Res Function(FormComponent) then) =
      _$FormComponentCopyWithImpl<$Res, FormComponent>;
  @useResult
  $Res call({String title, List<FormField> fields});
}

/// @nodoc
class _$FormComponentCopyWithImpl<$Res, $Val extends FormComponent>
    implements $FormComponentCopyWith<$Res> {
  _$FormComponentCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of FormComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? title = null,
    Object? fields = null,
  }) {
    return _then(_value.copyWith(
      title: null == title
          ? _value.title
          : title // ignore: cast_nullable_to_non_nullable
              as String,
      fields: null == fields
          ? _value.fields
          : fields // ignore: cast_nullable_to_non_nullable
              as List<FormField>,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$FormComponentImplCopyWith<$Res>
    implements $FormComponentCopyWith<$Res> {
  factory _$$FormComponentImplCopyWith(
          _$FormComponentImpl value, $Res Function(_$FormComponentImpl) then) =
      __$$FormComponentImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String title, List<FormField> fields});
}

/// @nodoc
class __$$FormComponentImplCopyWithImpl<$Res>
    extends _$FormComponentCopyWithImpl<$Res, _$FormComponentImpl>
    implements _$$FormComponentImplCopyWith<$Res> {
  __$$FormComponentImplCopyWithImpl(
      _$FormComponentImpl _value, $Res Function(_$FormComponentImpl) _then)
      : super(_value, _then);

  /// Create a copy of FormComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? title = null,
    Object? fields = null,
  }) {
    return _then(_$FormComponentImpl(
      title: null == title
          ? _value.title
          : title // ignore: cast_nullable_to_non_nullable
              as String,
      fields: null == fields
          ? _value._fields
          : fields // ignore: cast_nullable_to_non_nullable
              as List<FormField>,
    ));
  }
}

/// @nodoc
@JsonSerializable()
class _$FormComponentImpl implements _FormComponent {
  const _$FormComponentImpl(
      {required this.title, required final List<FormField> fields})
      : _fields = fields;

  factory _$FormComponentImpl.fromJson(Map<String, dynamic> json) =>
      _$$FormComponentImplFromJson(json);

  @override
  final String title;
  final List<FormField> _fields;
  @override
  List<FormField> get fields {
    if (_fields is EqualUnmodifiableListView) return _fields;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(_fields);
  }

  @override
  String toString() {
    return 'FormComponent(title: $title, fields: $fields)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$FormComponentImpl &&
            (identical(other.title, title) || other.title == title) &&
            const DeepCollectionEquality().equals(other._fields, _fields));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(
      runtimeType, title, const DeepCollectionEquality().hash(_fields));

  /// Create a copy of FormComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$FormComponentImplCopyWith<_$FormComponentImpl> get copyWith =>
      __$$FormComponentImplCopyWithImpl<_$FormComponentImpl>(this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$FormComponentImplToJson(
      this,
    );
  }
}

abstract class _FormComponent implements FormComponent {
  const factory _FormComponent(
      {required final String title,
      required final List<FormField> fields}) = _$FormComponentImpl;

  factory _FormComponent.fromJson(Map<String, dynamic> json) =
      _$FormComponentImpl.fromJson;

  @override
  String get title;
  @override
  List<FormField> get fields;

  /// Create a copy of FormComponent
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$FormComponentImplCopyWith<_$FormComponentImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
