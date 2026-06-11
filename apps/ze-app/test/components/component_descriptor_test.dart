import 'package:flutter_test/flutter_test.dart';
import 'package:ze_app/src/components/component_descriptor.dart';

void main() {
  group('componentFromJson', () {
    test('dispatches TableComponent', () {
      final c = componentFromJson({'type': 'table', 'headers': ['A'], 'rows': [['1']]});
      expect(c, isA<TableComponent>());
    });

    test('dispatches MetricComponent', () {
      final c = componentFromJson({'type': 'metric', 'label': 'Revenue', 'value': '\$100'});
      expect(c, isA<MetricComponent>());
    });

    test('dispatches CardComponent', () {
      final c = componentFromJson({'type': 'card', 'body': 'Hello', 'style': 'info'});
      expect(c, isA<CardComponent>());
    });

    test('throws FormatException for unknown type', () {
      expect(() => componentFromJson({'type': 'not_a_real_type'}), throwsFormatException);
    });
  });
}
