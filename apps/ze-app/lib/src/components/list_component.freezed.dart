// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'list_component.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
    'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models');

ListComponent _$ListComponentFromJson(Map<String, dynamic> json) {
  return _ListComponent.fromJson(json);
}

/// @nodoc
mixin _$ListComponent {
  List<ListItem> get items => throw _privateConstructorUsedError;
  String? get title => throw _privateConstructorUsedError;

  /// Serializes this ListComponent to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of ListComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $ListComponentCopyWith<ListComponent> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $ListComponentCopyWith<$Res> {
  factory $ListComponentCopyWith(
          ListComponent value, $Res Function(ListComponent) then) =
      _$ListComponentCopyWithImpl<$Res, ListComponent>;
  @useResult
  $Res call({List<ListItem> items, String? title});
}

/// @nodoc
class _$ListComponentCopyWithImpl<$Res, $Val extends ListComponent>
    implements $ListComponentCopyWith<$Res> {
  _$ListComponentCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of ListComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? items = null,
    Object? title = freezed,
  }) {
    return _then(_value.copyWith(
      items: null == items
          ? _value.items
          : items // ignore: cast_nullable_to_non_nullable
              as List<ListItem>,
      title: freezed == title
          ? _value.title
          : title // ignore: cast_nullable_to_non_nullable
              as String?,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$ListComponentImplCopyWith<$Res>
    implements $ListComponentCopyWith<$Res> {
  factory _$$ListComponentImplCopyWith(
          _$ListComponentImpl value, $Res Function(_$ListComponentImpl) then) =
      __$$ListComponentImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call({List<ListItem> items, String? title});
}

/// @nodoc
class __$$ListComponentImplCopyWithImpl<$Res>
    extends _$ListComponentCopyWithImpl<$Res, _$ListComponentImpl>
    implements _$$ListComponentImplCopyWith<$Res> {
  __$$ListComponentImplCopyWithImpl(
      _$ListComponentImpl _value, $Res Function(_$ListComponentImpl) _then)
      : super(_value, _then);

  /// Create a copy of ListComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? items = null,
    Object? title = freezed,
  }) {
    return _then(_$ListComponentImpl(
      items: null == items
          ? _value._items
          : items // ignore: cast_nullable_to_non_nullable
              as List<ListItem>,
      title: freezed == title
          ? _value.title
          : title // ignore: cast_nullable_to_non_nullable
              as String?,
    ));
  }
}

/// @nodoc
@JsonSerializable()
class _$ListComponentImpl implements _ListComponent {
  const _$ListComponentImpl({required final List<ListItem> items, this.title})
      : _items = items;

  factory _$ListComponentImpl.fromJson(Map<String, dynamic> json) =>
      _$$ListComponentImplFromJson(json);

  final List<ListItem> _items;
  @override
  List<ListItem> get items {
    if (_items is EqualUnmodifiableListView) return _items;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(_items);
  }

  @override
  final String? title;

  @override
  String toString() {
    return 'ListComponent(items: $items, title: $title)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$ListComponentImpl &&
            const DeepCollectionEquality().equals(other._items, _items) &&
            (identical(other.title, title) || other.title == title));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(
      runtimeType, const DeepCollectionEquality().hash(_items), title);

  /// Create a copy of ListComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$ListComponentImplCopyWith<_$ListComponentImpl> get copyWith =>
      __$$ListComponentImplCopyWithImpl<_$ListComponentImpl>(this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$ListComponentImplToJson(
      this,
    );
  }
}

abstract class _ListComponent implements ListComponent {
  const factory _ListComponent(
      {required final List<ListItem> items,
      final String? title}) = _$ListComponentImpl;

  factory _ListComponent.fromJson(Map<String, dynamic> json) =
      _$ListComponentImpl.fromJson;

  @override
  List<ListItem> get items;
  @override
  String? get title;

  /// Create a copy of ListComponent
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$ListComponentImplCopyWith<_$ListComponentImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
