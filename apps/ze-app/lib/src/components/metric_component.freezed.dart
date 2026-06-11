// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'metric_component.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
    'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models');

MetricComponent _$MetricComponentFromJson(Map<String, dynamic> json) {
  return _MetricComponent.fromJson(json);
}

/// @nodoc
mixin _$MetricComponent {
  String get label => throw _privateConstructorUsedError;
  String get value => throw _privateConstructorUsedError;
  String? get trend => throw _privateConstructorUsedError;
  String? get note => throw _privateConstructorUsedError;

  /// Serializes this MetricComponent to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of MetricComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $MetricComponentCopyWith<MetricComponent> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $MetricComponentCopyWith<$Res> {
  factory $MetricComponentCopyWith(
          MetricComponent value, $Res Function(MetricComponent) then) =
      _$MetricComponentCopyWithImpl<$Res, MetricComponent>;
  @useResult
  $Res call({String label, String value, String? trend, String? note});
}

/// @nodoc
class _$MetricComponentCopyWithImpl<$Res, $Val extends MetricComponent>
    implements $MetricComponentCopyWith<$Res> {
  _$MetricComponentCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of MetricComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? label = null,
    Object? value = null,
    Object? trend = freezed,
    Object? note = freezed,
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
      trend: freezed == trend
          ? _value.trend
          : trend // ignore: cast_nullable_to_non_nullable
              as String?,
      note: freezed == note
          ? _value.note
          : note // ignore: cast_nullable_to_non_nullable
              as String?,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$MetricComponentImplCopyWith<$Res>
    implements $MetricComponentCopyWith<$Res> {
  factory _$$MetricComponentImplCopyWith(_$MetricComponentImpl value,
          $Res Function(_$MetricComponentImpl) then) =
      __$$MetricComponentImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String label, String value, String? trend, String? note});
}

/// @nodoc
class __$$MetricComponentImplCopyWithImpl<$Res>
    extends _$MetricComponentCopyWithImpl<$Res, _$MetricComponentImpl>
    implements _$$MetricComponentImplCopyWith<$Res> {
  __$$MetricComponentImplCopyWithImpl(
      _$MetricComponentImpl _value, $Res Function(_$MetricComponentImpl) _then)
      : super(_value, _then);

  /// Create a copy of MetricComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? label = null,
    Object? value = null,
    Object? trend = freezed,
    Object? note = freezed,
  }) {
    return _then(_$MetricComponentImpl(
      label: null == label
          ? _value.label
          : label // ignore: cast_nullable_to_non_nullable
              as String,
      value: null == value
          ? _value.value
          : value // ignore: cast_nullable_to_non_nullable
              as String,
      trend: freezed == trend
          ? _value.trend
          : trend // ignore: cast_nullable_to_non_nullable
              as String?,
      note: freezed == note
          ? _value.note
          : note // ignore: cast_nullable_to_non_nullable
              as String?,
    ));
  }
}

/// @nodoc
@JsonSerializable()
class _$MetricComponentImpl implements _MetricComponent {
  const _$MetricComponentImpl(
      {required this.label, required this.value, this.trend, this.note});

  factory _$MetricComponentImpl.fromJson(Map<String, dynamic> json) =>
      _$$MetricComponentImplFromJson(json);

  @override
  final String label;
  @override
  final String value;
  @override
  final String? trend;
  @override
  final String? note;

  @override
  String toString() {
    return 'MetricComponent(label: $label, value: $value, trend: $trend, note: $note)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$MetricComponentImpl &&
            (identical(other.label, label) || other.label == label) &&
            (identical(other.value, value) || other.value == value) &&
            (identical(other.trend, trend) || other.trend == trend) &&
            (identical(other.note, note) || other.note == note));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(runtimeType, label, value, trend, note);

  /// Create a copy of MetricComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$MetricComponentImplCopyWith<_$MetricComponentImpl> get copyWith =>
      __$$MetricComponentImplCopyWithImpl<_$MetricComponentImpl>(
          this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$MetricComponentImplToJson(
      this,
    );
  }
}

abstract class _MetricComponent implements MetricComponent {
  const factory _MetricComponent(
      {required final String label,
      required final String value,
      final String? trend,
      final String? note}) = _$MetricComponentImpl;

  factory _MetricComponent.fromJson(Map<String, dynamic> json) =
      _$MetricComponentImpl.fromJson;

  @override
  String get label;
  @override
  String get value;
  @override
  String? get trend;
  @override
  String? get note;

  /// Create a copy of MetricComponent
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$MetricComponentImplCopyWith<_$MetricComponentImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
