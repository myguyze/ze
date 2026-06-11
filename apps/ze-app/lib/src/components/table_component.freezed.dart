// coverage:ignore-file
// GENERATED CODE - DO NOT MODIFY BY HAND
// ignore_for_file: type=lint
// ignore_for_file: unused_element, deprecated_member_use, deprecated_member_use_from_same_package, use_function_type_syntax_for_parameters, unnecessary_const, avoid_init_to_null, invalid_override_different_default_values_named, prefer_expression_function_bodies, annotate_overrides, invalid_annotation_target, unnecessary_question_mark

part of 'table_component.dart';

// **************************************************************************
// FreezedGenerator
// **************************************************************************

T _$identity<T>(T value) => value;

final _privateConstructorUsedError = UnsupportedError(
    'It seems like you constructed your class using `MyClass._()`. This constructor is only meant to be used by freezed and you are not supposed to need it nor use it.\nPlease check the documentation here for more information: https://github.com/rrousselGit/freezed#adding-getters-and-methods-to-our-models');

TableComponent _$TableComponentFromJson(Map<String, dynamic> json) {
  return _TableComponent.fromJson(json);
}

/// @nodoc
mixin _$TableComponent {
  List<String> get headers => throw _privateConstructorUsedError;
  List<List<String>> get rows => throw _privateConstructorUsedError;
  String? get title => throw _privateConstructorUsedError;
  String? get caption => throw _privateConstructorUsedError;

  /// Serializes this TableComponent to a JSON map.
  Map<String, dynamic> toJson() => throw _privateConstructorUsedError;

  /// Create a copy of TableComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  $TableComponentCopyWith<TableComponent> get copyWith =>
      throw _privateConstructorUsedError;
}

/// @nodoc
abstract class $TableComponentCopyWith<$Res> {
  factory $TableComponentCopyWith(
          TableComponent value, $Res Function(TableComponent) then) =
      _$TableComponentCopyWithImpl<$Res, TableComponent>;
  @useResult
  $Res call(
      {List<String> headers,
      List<List<String>> rows,
      String? title,
      String? caption});
}

/// @nodoc
class _$TableComponentCopyWithImpl<$Res, $Val extends TableComponent>
    implements $TableComponentCopyWith<$Res> {
  _$TableComponentCopyWithImpl(this._value, this._then);

  // ignore: unused_field
  final $Val _value;
  // ignore: unused_field
  final $Res Function($Val) _then;

  /// Create a copy of TableComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? headers = null,
    Object? rows = null,
    Object? title = freezed,
    Object? caption = freezed,
  }) {
    return _then(_value.copyWith(
      headers: null == headers
          ? _value.headers
          : headers // ignore: cast_nullable_to_non_nullable
              as List<String>,
      rows: null == rows
          ? _value.rows
          : rows // ignore: cast_nullable_to_non_nullable
              as List<List<String>>,
      title: freezed == title
          ? _value.title
          : title // ignore: cast_nullable_to_non_nullable
              as String?,
      caption: freezed == caption
          ? _value.caption
          : caption // ignore: cast_nullable_to_non_nullable
              as String?,
    ) as $Val);
  }
}

/// @nodoc
abstract class _$$TableComponentImplCopyWith<$Res>
    implements $TableComponentCopyWith<$Res> {
  factory _$$TableComponentImplCopyWith(_$TableComponentImpl value,
          $Res Function(_$TableComponentImpl) then) =
      __$$TableComponentImplCopyWithImpl<$Res>;
  @override
  @useResult
  $Res call(
      {List<String> headers,
      List<List<String>> rows,
      String? title,
      String? caption});
}

/// @nodoc
class __$$TableComponentImplCopyWithImpl<$Res>
    extends _$TableComponentCopyWithImpl<$Res, _$TableComponentImpl>
    implements _$$TableComponentImplCopyWith<$Res> {
  __$$TableComponentImplCopyWithImpl(
      _$TableComponentImpl _value, $Res Function(_$TableComponentImpl) _then)
      : super(_value, _then);

  /// Create a copy of TableComponent
  /// with the given fields replaced by the non-null parameter values.
  @pragma('vm:prefer-inline')
  @override
  $Res call({
    Object? headers = null,
    Object? rows = null,
    Object? title = freezed,
    Object? caption = freezed,
  }) {
    return _then(_$TableComponentImpl(
      headers: null == headers
          ? _value._headers
          : headers // ignore: cast_nullable_to_non_nullable
              as List<String>,
      rows: null == rows
          ? _value._rows
          : rows // ignore: cast_nullable_to_non_nullable
              as List<List<String>>,
      title: freezed == title
          ? _value.title
          : title // ignore: cast_nullable_to_non_nullable
              as String?,
      caption: freezed == caption
          ? _value.caption
          : caption // ignore: cast_nullable_to_non_nullable
              as String?,
    ));
  }
}

/// @nodoc
@JsonSerializable()
class _$TableComponentImpl implements _TableComponent {
  const _$TableComponentImpl(
      {required final List<String> headers,
      required final List<List<String>> rows,
      this.title,
      this.caption})
      : _headers = headers,
        _rows = rows;

  factory _$TableComponentImpl.fromJson(Map<String, dynamic> json) =>
      _$$TableComponentImplFromJson(json);

  final List<String> _headers;
  @override
  List<String> get headers {
    if (_headers is EqualUnmodifiableListView) return _headers;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(_headers);
  }

  final List<List<String>> _rows;
  @override
  List<List<String>> get rows {
    if (_rows is EqualUnmodifiableListView) return _rows;
    // ignore: implicit_dynamic_type
    return EqualUnmodifiableListView(_rows);
  }

  @override
  final String? title;
  @override
  final String? caption;

  @override
  String toString() {
    return 'TableComponent(headers: $headers, rows: $rows, title: $title, caption: $caption)';
  }

  @override
  bool operator ==(Object other) {
    return identical(this, other) ||
        (other.runtimeType == runtimeType &&
            other is _$TableComponentImpl &&
            const DeepCollectionEquality().equals(other._headers, _headers) &&
            const DeepCollectionEquality().equals(other._rows, _rows) &&
            (identical(other.title, title) || other.title == title) &&
            (identical(other.caption, caption) || other.caption == caption));
  }

  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  int get hashCode => Object.hash(
      runtimeType,
      const DeepCollectionEquality().hash(_headers),
      const DeepCollectionEquality().hash(_rows),
      title,
      caption);

  /// Create a copy of TableComponent
  /// with the given fields replaced by the non-null parameter values.
  @JsonKey(includeFromJson: false, includeToJson: false)
  @override
  @pragma('vm:prefer-inline')
  _$$TableComponentImplCopyWith<_$TableComponentImpl> get copyWith =>
      __$$TableComponentImplCopyWithImpl<_$TableComponentImpl>(
          this, _$identity);

  @override
  Map<String, dynamic> toJson() {
    return _$$TableComponentImplToJson(
      this,
    );
  }
}

abstract class _TableComponent implements TableComponent {
  const factory _TableComponent(
      {required final List<String> headers,
      required final List<List<String>> rows,
      final String? title,
      final String? caption}) = _$TableComponentImpl;

  factory _TableComponent.fromJson(Map<String, dynamic> json) =
      _$TableComponentImpl.fromJson;

  @override
  List<String> get headers;
  @override
  List<List<String>> get rows;
  @override
  String? get title;
  @override
  String? get caption;

  /// Create a copy of TableComponent
  /// with the given fields replaced by the non-null parameter values.
  @override
  @JsonKey(includeFromJson: false, includeToJson: false)
  _$$TableComponentImplCopyWith<_$TableComponentImpl> get copyWith =>
      throw _privateConstructorUsedError;
}
