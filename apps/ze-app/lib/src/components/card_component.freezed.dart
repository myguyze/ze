// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'card_component.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
    'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models');

CardComponent _$CardComponentFromJson(Map<String, dynamic> json) {
  return _CardComponent.fromJson(json);
}

/// @nodoc
mixin _$CardComponent {
  String get body => throw _privateConstructorUsedError;
  String? get title => throw _privateConstructorUsedError;
  String get style => throw _privateConstructorUsedError;

  /// Serializes this CardComponent to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of CardComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $CardComponentCopyWith<CardComponent> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $CardComponentCopyWith<$Res> {
  factory $CardComponentCopyWith(
          CardComponent value, $Res Function(CardComponent) then) =
      _$CardComponentCopyWithImpl<$Res, CardComponent>;
  @useResult
  $Res call({String body, String? title, String style});
}

/// @nodoc
class _$CardComponentCopyWithImpl<$Res, $Val extends CardComponent>
    implements $CardComponentCopyWith<$Res> {
  _$CardComponentCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of CardComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? body = null,
    Object? title = freezed,
    Object? style = null,
  }) {
    return _then(_value.copyWith(
      body: null == body
          ? _value.body
          : body // ignore: cast_nullable_to_non_nullable
              as String,
      title: freezed == title
          ? _value.title
          : title // ignore: cast_nullable_to_non_nullable
              as String?,
      style: null == style
          ? _value.style
          : style // ignore: cast_nullable_to_non_nullable
              as String,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$CardComponentImplCopyWith<$Res>
    implements $CardComponentCopyWith<$Res> {
  factory _$$CardComponentImplCopyWith(
          _$CardComponentImpl value, $Res Function(_$CardComponentImpl) then) =
      __$$CardComponentImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({String body, String? title, String style});
}

/// @nodoc
class __$$CardComponentImplCopyWithImpl<$Res>
    extends _$CardComponentCopyWithImpl<$Res, _$CardComponentImpl>
    implements _$$CardComponentImplCopyWith<$Res> {
  __$$CardComponentImplCopyWithImpl(
      _$CardComponentImpl _value, $Res Function(_$CardComponentImpl) _then)
      : super(_value, _then);

  /// Create a copy of CardComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? body = null,
    Object? title = freezed,
    Object? style = null,
  }) {
    return _then(_$CardComponentImpl(
      body: null == body
          ? _value.body
          : body // ignore: cast_nullable_to_non_nullable
              as String,
      title: freezed == title
          ? _value.title
          : title // ignore: cast_nullable_to_non_nullable
              as String?,
      style: null == style
          ? _value.style
          : style // ignore: cast_nullable_to_non_nullable
              as String,
    ));
  }
}

/// @nodoc
@JsonSerializable()
class _$CardComponentImpl implements _CardComponent {
  const _$CardComponentImpl(
      {required this.body, this.title, this.style = 'info'});

  factory _$CardComponentImpl.fromJson(Map<String, dynamic> json) =>
      _$$CardComponentImplFromJson(json);

  @override
  final String body;
  @override
  final String? title;
  @override
  @JsonKey()
  final String style;

  @override
  String toString() {
    return 'CardComponent(body: $body, title: $title, style: $style)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$CardComponentImpl &&
            (identical(other.body, body) || other.body == body) &&
            (identical(other.title, title) || other.title == title) &&
            (identical(other.style, style) || other.style == style));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(runtimeType, body, title, style);

  /// Create a copy of CardComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$CardComponentImplCopyWith<_$CardComponentImpl> get copyWith =>
      __$$CardComponentImplCopyWithImpl<_$CardComponentImpl>(this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$CardComponentImplToJson(
      this,
    );
  }
}

abstract class _CardComponent implements CardComponent {
  const factory _CardComponent(
      {required final String body,
      final String? title,
      final String style}) = _$CardComponentImpl;

  factory _CardComponent.fromJson(Map<String, dynamic> json) =
      _$CardComponentImpl.fromJson;

  @override
  String get body;
  @override
  String? get title;
  @override
  String get style;

  /// Create a copy of CardComponent
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$CardComponentImplCopyWith<_$CardComponentImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
