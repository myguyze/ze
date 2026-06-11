// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'progress.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
    'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models');

ProgressStep _$ProgressStepFromJson(Map<String, dynamic> json) {
  return _ProgressStep.fromJson(json);
}

/// @nodoc
mixin _$ProgressStep {
  String get label => throw _privateConstructorUsedError;
  String get status => throw _privateConstructorUsedError;

  /// Serializes this ProgressStep to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of ProgressStep
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $ProgressStepCopyWith<ProgressStep> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $ProgressStepCopyWith<$Res> {
  factory $ProgressStepCopyWith(
          ProgressStep value, $Res Function(ProgressStep) then) =
      _$ProgressStepCopyWithImpl<$Res, ProgressStep>;
  @useResult
  $Res call({String label, String status});
}

/// @nodoc
class _$ProgressStepCopyWithImpl<$Res, $Val extends ProgressStep>
    implements $ProgressStepCopyWith<$Res> {
  _$ProgressStepCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of ProgressStep
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? label = null,
    Object? status = null,
  }) {
    return _then(_value.copyWith(
      label: null == label
          ? _value.label
          : label // ignore: cast_nullable_to_non_nullable
              as String,
      status: null == status
          ? _value.status
          : status // ignore: cast_nullable_to_non_nullable
              as String,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$ProgressStepImplCopyWith<$Res>
    implements $ProgressStepCopyWith<$Res> {
  factory _$$ProgressStepImplCopyWith(
          _$ProgressStepImpl value, $Res Function(_$ProgressStepImpl) then) =
      __$$ProgressStepImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String label, String status});
}

/// @nodoc
class __$$ProgressStepImplCopyWithImpl<$Res>
    extends _$ProgressStepCopyWithImpl<$Res, _$ProgressStepImpl>
    implements _$$ProgressStepImplCopyWith<$Res> {
  __$$ProgressStepImplCopyWithImpl(
      _$ProgressStepImpl _value, $Res Function(_$ProgressStepImpl) _then)
      : super(_value, _then);

  /// Create a copy of ProgressStep
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? label = null,
    Object? status = null,
  }) {
    return _then(_$ProgressStepImpl(
      label: null == label
          ? _value.label
          : label // ignore: cast_nullable_to_non_nullable
              as String,
      status: null == status
          ? _value.status
          : status // ignore: cast_nullable_to_non_nullable
              as String,
    ));
  }
}

/// @nodoc
@JsonSerializable()
class _$ProgressStepImpl implements _ProgressStep {
  const _$ProgressStepImpl({required this.label, this.status = 'pending'});

  factory _$ProgressStepImpl.fromJson(Map<String, dynamic> json) =>
      _$$ProgressStepImplFromJson(json);

  @override
  final String label;
  @override
  @JsonKey()
  final String status;

  @override
  String toString() {
    return 'ProgressStep(label: $label, status: $status)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$ProgressStepImpl &&
            (identical(other.label, label) || other.label == label) &&
            (identical(other.status, status) || other.status == status));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(runtimeType, label, status);

  /// Create a copy of ProgressStep
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$ProgressStepImplCopyWith<_$ProgressStepImpl> get copyWith =>
      __$$ProgressStepImplCopyWithImpl<_$ProgressStepImpl>(this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$ProgressStepImplToJson(
      this,
    );
  }
}

abstract class _ProgressStep implements ProgressStep {
  const factory _ProgressStep(
      {required final String label, final String status}) = _$ProgressStepImpl;

  factory _ProgressStep.fromJson(Map<String, dynamic> json) =
      _$ProgressStepImpl.fromJson;

  @override
  String get label;
  @override
  String get status;

  /// Create a copy of ProgressStep
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$ProgressStepImplCopyWith<_$ProgressStepImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
