// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'progress_component.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
    'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models');

ProgressComponent _$ProgressComponentFromJson(Map<String, dynamic> json) {
  return _ProgressComponent.fromJson(json);
}

/// @nodoc
mixin _$ProgressComponent {
  String get title => throw _privateConstructorUsedError;
  List<ProgressStep> get steps => throw _privateConstructorUsedError;

  /// Serializes this ProgressComponent to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of ProgressComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $ProgressComponentCopyWith<ProgressComponent> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $ProgressComponentCopyWith<$Res> {
  factory $ProgressComponentCopyWith(
          ProgressComponent value, $Res Function(ProgressComponent) then) =
      _$ProgressComponentCopyWithImpl<$Res, ProgressComponent>;
  @useResult
  $Res call({String title, List<ProgressStep> steps});
}

/// @nodoc
class _$ProgressComponentCopyWithImpl<$Res, $Val extends ProgressComponent>
    implements $ProgressComponentCopyWith<$Res> {
  _$ProgressComponentCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of ProgressComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? title = null,
    Object? steps = null,
  }) {
    return _then(_value.copyWith(
      title: null == title
          ? _value.title
          : title // ignore: cast_nullable_to_non_nullable
              as String,
      steps: null == steps
          ? _value.steps
          : steps // ignore: cast_nullable_to_non_nullable
              as List<ProgressStep>,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$ProgressComponentImplCopyWith<$Res>
    implements $ProgressComponentCopyWith<$Res> {
  factory _$$ProgressComponentImplCopyWith(_$ProgressComponentImpl value,
          $Res Function(_$ProgressComponentImpl) then) =
      __$$ProgressComponentImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String title, List<ProgressStep> steps});
}

/// @nodoc
class __$$ProgressComponentImplCopyWithImpl<$Res>
    extends _$ProgressComponentCopyWithImpl<$Res, _$ProgressComponentImpl>
    implements _$$ProgressComponentImplCopyWith<$Res> {
  __$$ProgressComponentImplCopyWithImpl(_$ProgressComponentImpl _value,
      $Res Function(_$ProgressComponentImpl) _then)
      : super(_value, _then);

  /// Create a copy of ProgressComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? title = null,
    Object? steps = null,
  }) {
    return _then(_$ProgressComponentImpl(
      title: null == title
          ? _value.title
          : title // ignore: cast_nullable_to_non_nullable
              as String,
      steps: null == steps
          ? _value._steps
          : steps // ignore: cast_nullable_to_non_nullable
              as List<ProgressStep>,
    ));
  }
}

/// @nodoc
@JsonSerializable()
class _$ProgressComponentImpl implements _ProgressComponent {
  const _$ProgressComponentImpl(
      {required this.title, required final List<ProgressStep> steps})
      : _steps = steps;

  factory _$ProgressComponentImpl.fromJson(Map<String, dynamic> json) =>
      _$$ProgressComponentImplFromJson(json);

  @override
  final String title;
  final List<ProgressStep> _steps;
  @override
  List<ProgressStep> get steps {
    if (_steps is EqualUnmodifiableListView) return _steps;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(_steps);
  }

  @override
  String toString() {
    return 'ProgressComponent(title: $title, steps: $steps)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$ProgressComponentImpl &&
            (identical(other.title, title) || other.title == title) &&
            const DeepCollectionEquality().equals(other._steps, _steps));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(
      runtimeType, title, const DeepCollectionEquality().hash(_steps));

  /// Create a copy of ProgressComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$ProgressComponentImplCopyWith<_$ProgressComponentImpl> get copyWith =>
      __$$ProgressComponentImplCopyWithImpl<_$ProgressComponentImpl>(
          this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$ProgressComponentImplToJson(
      this,
    );
  }
}

abstract class _ProgressComponent implements ProgressComponent {
  const factory _ProgressComponent(
      {required final String title,
      required final List<ProgressStep> steps}) = _$ProgressComponentImpl;

  factory _ProgressComponent.fromJson(Map<String, dynamic> json) =
      _$ProgressComponentImpl.fromJson;

  @override
  String get title;
  @override
  List<ProgressStep> get steps;

  /// Create a copy of ProgressComponent
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$ProgressComponentImplCopyWith<_$ProgressComponentImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
