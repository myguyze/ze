// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'confirm_component.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
    'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models');

ConfirmComponent _$ConfirmComponentFromJson(Map<String, dynamic> json) {
  return _ConfirmComponent.fromJson(json);
}

/// @nodoc
mixin _$ConfirmComponent {
  String get prompt => throw _privateConstructorUsedError;
  List<ConfirmAction> get actions => throw _privateConstructorUsedError;

  /// Serializes this ConfirmComponent to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of ConfirmComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $ConfirmComponentCopyWith<ConfirmComponent> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $ConfirmComponentCopyWith<$Res> {
  factory $ConfirmComponentCopyWith(
          ConfirmComponent value, $Res Function(ConfirmComponent) then) =
      _$ConfirmComponentCopyWithImpl<$Res, ConfirmComponent>;
  @useResult
  $Res call({String prompt, List<ConfirmAction> actions});
}

/// @nodoc
class _$ConfirmComponentCopyWithImpl<$Res, $Val extends ConfirmComponent>
    implements $ConfirmComponentCopyWith<$Res> {
  _$ConfirmComponentCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of ConfirmComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? prompt = null,
    Object? actions = null,
  }) {
    return _then(_value.copyWith(
      prompt: null == prompt
          ? _value.prompt
          : prompt // ignore: cast_nullable_to_non_nullable
              as String,
      actions: null == actions
          ? _value.actions
          : actions // ignore: cast_nullable_to_non_nullable
              as List<ConfirmAction>,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$ConfirmComponentImplCopyWith<$Res>
    implements $ConfirmComponentCopyWith<$Res> {
  factory _$$ConfirmComponentImplCopyWith(_$ConfirmComponentImpl value,
          $Res Function(_$ConfirmComponentImpl) then) =
      __$$ConfirmComponentImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String prompt, List<ConfirmAction> actions});
}

/// @nodoc
class __$$ConfirmComponentImplCopyWithImpl<$Res>
    extends _$ConfirmComponentCopyWithImpl<$Res, _$ConfirmComponentImpl>
    implements _$$ConfirmComponentImplCopyWith<$Res> {
  __$$ConfirmComponentImplCopyWithImpl(_$ConfirmComponentImpl _value,
      $Res Function(_$ConfirmComponentImpl) _then)
      : super(_value, _then);

  /// Create a copy of ConfirmComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? prompt = null,
    Object? actions = null,
  }) {
    return _then(_$ConfirmComponentImpl(
      prompt: null == prompt
          ? _value.prompt
          : prompt // ignore: cast_nullable_to_non_nullable
              as String,
      actions: null == actions
          ? _value._actions
          : actions // ignore: cast_nullable_to_non_nullable
              as List<ConfirmAction>,
    ));
  }
}

/// @nodoc
@JsonSerializable()
class _$ConfirmComponentImpl implements _ConfirmComponent {
  const _$ConfirmComponentImpl(
      {required this.prompt, required final List<ConfirmAction> actions})
      : _actions = actions;

  factory _$ConfirmComponentImpl.fromJson(Map<String, dynamic> json) =>
      _$$ConfirmComponentImplFromJson(json);

  @override
  final String prompt;
  final List<ConfirmAction> _actions;
  @override
  List<ConfirmAction> get actions {
    if (_actions is EqualUnmodifiableListView) return _actions;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(_actions);
  }

  @override
  String toString() {
    return 'ConfirmComponent(prompt: $prompt, actions: $actions)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$ConfirmComponentImpl &&
            (identical(other.prompt, prompt) || other.prompt == prompt) &&
            const DeepCollectionEquality().equals(other._actions, _actions));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(
      runtimeType, prompt, const DeepCollectionEquality().hash(_actions));

  /// Create a copy of ConfirmComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$ConfirmComponentImplCopyWith<_$ConfirmComponentImpl> get copyWith =>
      __$$ConfirmComponentImplCopyWithImpl<_$ConfirmComponentImpl>(
          this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$ConfirmComponentImplToJson(
      this,
    );
  }
}

abstract class _ConfirmComponent implements ConfirmComponent {
  const factory _ConfirmComponent(
      {required final String prompt,
      required final List<ConfirmAction> actions}) = _$ConfirmComponentImpl;

  factory _ConfirmComponent.fromJson(Map<String, dynamic> json) =
      _$ConfirmComponentImpl.fromJson;

  @override
  String get prompt;
  @override
  List<ConfirmAction> get actions;

  /// Create a copy of ConfirmComponent
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$ConfirmComponentImplCopyWith<_$ConfirmComponentImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
