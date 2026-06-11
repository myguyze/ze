import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ze_app/src/components/component_widget.dart';

void main() {
  testWidgets('componentWidget returns SizedBox.shrink on malformed JSON', (tester) async {
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: componentWidget({'type': 'unknown_bad'}))),
    );
    expect(find.byType(SizedBox), findsWidgets);
  });
}
