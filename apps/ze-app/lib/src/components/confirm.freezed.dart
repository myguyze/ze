// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'confirm.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
    'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models');

ConfirmAction _$ConfirmActionFromJson(Map<String, dynamic> json) {
  return _ConfirmAction.fromJson(json);
}

/// @nodoc
mixin _$ConfirmAction {
  String get label => throw _privateConstructorUsedError;
  String get value => throw _privateConstructorUsedError;
  String get style => throw _privateConstructorUsedError;

  /// Serializes this ConfirmAction to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of ConfirmAction
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $ConfirmActionCopyWith<ConfirmAction> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $ConfirmActionCopyWith<$Res> {
  factory $ConfirmActionCopyWith(
          ConfirmAction value, $Res Function(ConfirmAction) then) =
      _$ConfirmActionCopyWithImpl<$Res, ConfirmAction>;
  @useResult
  $Res call({String label, String value, String style});
}

/// @nodoc
class _$ConfirmActionCopyWithImpl<$Res, $Val extends ConfirmAction>
    implements $ConfirmActionCopyWith<$Res> {
  _$ConfirmActionCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of ConfirmAction
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? label = null,
    Object? value = null,
    Object? style = null,
  }) {
    return _then(_value.copyWith(
      label: null == label
          ? _value.label
          : label // ignore: cast_nullable_to_non_nullable
              as String,
      value: null == value
          ? _value.value
          : value // ignore: cast_nullable_to_non_nullable
              as String,
      style: null == style
          ? _value.style
          : style // ignore: cast_nullable_to_non_nullable
              as String,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$ConfirmActionImplCopyWith<$Res>
    implements $ConfirmActionCopyWith<$Res> {
  factory _$$ConfirmActionImplCopyWith(
          _$ConfirmActionImpl value, $Res Function(_$ConfirmActionImpl) then) =
      __$$ConfirmActionImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String label, String value, String style});
}

/// @nodoc
class __$$ConfirmActionImplCopyWithImpl<$Res>
    extends _$ConfirmActionCopyWithImpl<$Res, _$ConfirmActionImpl>
    implements _$$ConfirmActionImplCopyWith<$Res> {
  __$$ConfirmActionImplCopyWithImpl(
      _$ConfirmActionImpl _value, $Res Function(_$ConfirmActionImpl) _then)
      : super(_value, _then);

  /// Create a copy of ConfirmAction
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? label = null,
    Object? value = null,
    Object? style = null,
  }) {
    return _then(_$ConfirmActionImpl(
      label: null == label
          ? _value.label
          : label // ignore: cast_nullable_to_non_nullable
              as String,
      value: null == value
          ? _value.value
          : value // ignore: cast_nullable_to_non_nullable
              as String,
      style: null == style
          ? _value.style
          : style // ignore: cast_nullable_to_non_nullable
              as String,
    ));
  }
}

/// @nodoc
@JsonSerializable()
class _$ConfirmActionImpl implements _ConfirmAction {
  const _$ConfirmActionImpl(
      {required this.label, required this.value, this.style = 'secondary'});

  factory _$ConfirmActionImpl.fromJson(Map<String, dynamic> json) =>
      _$$ConfirmActionImplFromJson(json);

  @override
  final String label;
  @override
  final String value;
  @override
  @JsonKey()
  final String style;

  @override
  String toString() {
    return 'ConfirmAction(label: $label, value: $value, style: $style)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$ConfirmActionImpl &&
            (identical(other.label, label) || other.label == label) &&
            (identical(other.value, value) || other.value == value) &&
            (identical(other.style, style) || other.style == style));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(runtimeType, label, value, style);

  /// Create a copy of ConfirmAction
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$ConfirmActionImplCopyWith<_$ConfirmActionImpl> get copyWith =>
      __$$ConfirmActionImplCopyWithImpl<_$ConfirmActionImpl>(this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$ConfirmActionImplToJson(
      this,
    );
  }
}

abstract class _ConfirmAction implements ConfirmAction {
  const factory _ConfirmAction(
      {required final String label,
      required final String value,
      final String style}) = _$ConfirmActionImpl;

  factory _ConfirmAction.fromJson(Map<String, dynamic> json) =
      _$ConfirmActionImpl.fromJson;

  @override
  String get label;
  @override
  String get value;
  @override
  String get style;

  /// Create a copy of ConfirmAction
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$ConfirmActionImplCopyWith<_$ConfirmActionImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
