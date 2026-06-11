// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'timeline_component.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
    'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models');

TimelineComponent _$TimelineComponentFromJson(Map<String, dynamic> json) {
  return _TimelineComponent.fromJson(json);
}

/// @nodoc
mixin _$TimelineComponent {
  List<TimelineEvent> get events => throw _privateConstructorUsedError;
  String? get title => throw _privateConstructorUsedError;

  /// Serializes this TimelineComponent to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of TimelineComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $TimelineComponentCopyWith<TimelineComponent> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $TimelineComponentCopyWith<$Res> {
  factory $TimelineComponentCopyWith(
          TimelineComponent value, $Res Function(TimelineComponent) then) =
      _$TimelineComponentCopyWithImpl<$Res, TimelineComponent>;
  @useResult
  $Res call({List<TimelineEvent> events, String? title});
}

/// @nodoc
class _$TimelineComponentCopyWithImpl<$Res, $Val extends TimelineComponent>
    implements $TimelineComponentCopyWith<$Res> {
  _$TimelineComponentCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of TimelineComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? events = null,
    Object? title = freezed,
  }) {
    return _then(_value.copyWith(
      events: null == events
          ? _value.events
          : events // ignore: cast_nullable_to_non_nullable
              as List<TimelineEvent>,
      title: freezed == title
          ? _value.title
          : title // ignore: cast_nullable_to_non_nullable
              as String?,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$TimelineComponentImplCopyWith<$Res>
    implements $TimelineComponentCopyWith<$Res> {
  factory _$$TimelineComponentImplCopyWith(_$TimelineComponentImpl value,
          $Res Function(_$TimelineComponentImpl) then) =
      __$$TimelineComponentImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({List<TimelineEvent> events, String? title});
}

/// @nodoc
class __$$TimelineComponentImplCopyWithImpl<$Res>
    extends _$TimelineComponentCopyWithImpl<$Res, _$TimelineComponentImpl>
    implements _$$TimelineComponentImplCopyWith<$Res> {
  __$$TimelineComponentImplCopyWithImpl(_$TimelineComponentImpl _value,
      $Res Function(_$TimelineComponentImpl) _then)
      : super(_value, _then);

  /// Create a copy of TimelineComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? events = null,
    Object? title = freezed,
  }) {
    return _then(_$TimelineComponentImpl(
      events: null == events
          ? _value._events
          : events // ignore: cast_nullable_to_non_nullable
              as List<TimelineEvent>,
      title: freezed == title
          ? _value.title
          : title // ignore: cast_nullable_to_non_nullable
              as String?,
    ));
  }
}

/// @nodoc
@JsonSerializable()
class _$TimelineComponentImpl implements _TimelineComponent {
  const _$TimelineComponentImpl(
      {required final List<TimelineEvent> events, this.title})
      : _events = events;

  factory _$TimelineComponentImpl.fromJson(Map<String, dynamic> json) =>
      _$$TimelineComponentImplFromJson(json);

  final List<TimelineEvent> _events;
  @override
  List<TimelineEvent> get events {
    if (_events is EqualUnmodifiableListView) return _events;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(_events);
  }

  @override
  final String? title;

  @override
  String toString() {
    return 'TimelineComponent(events: $events, title: $title)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$TimelineComponentImpl &&
            const DeepCollectionEquality().equals(other._events, _events) &&
            (identical(other.title, title) || other.title == title));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(
      runtimeType, const DeepCollectionEquality().hash(_events), title);

  /// Create a copy of TimelineComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$TimelineComponentImplCopyWith<_$TimelineComponentImpl> get copyWith =>
      __$$TimelineComponentImplCopyWithImpl<_$TimelineComponentImpl>(
          this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$TimelineComponentImplToJson(
      this,
    );
  }
}

abstract class _TimelineComponent implements TimelineComponent {
  const factory _TimelineComponent(
      {required final List<TimelineEvent> events,
      final String? title}) = _$TimelineComponentImpl;

  factory _TimelineComponent.fromJson(Map<String, dynamic> json) =
      _$TimelineComponentImpl.fromJson;

  @override
  List<TimelineEvent> get events;
  @override
  String? get title;

  /// Create a copy of TimelineComponent
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$TimelineComponentImplCopyWith<_$TimelineComponentImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
