// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:ze_app/src/components/table_component.dart';
import 'package:ze_app/src/components/table_component.dart';
import 'package:ze_app/src/components/metric_component.dart';
import 'package:ze_app/src/components/list_component.dart';
import 'package:ze_app/src/components/timeline_component.dart';
import 'package:ze_app/src/components/progress_component.dart';
import 'package:ze_app/src/components/confirm_component.dart';
import 'package:ze_app/src/components/form_component.dart';
import 'package:ze_app/src/components/card_component.dart';

// Dispatches JSON to the correct component class based on the 'type' field.
dynamic componentFromJson(Map<String, dynamic> json) =>
  switch (json['type'] as String) {
    'table' => TableComponent.fromJson(json),
    'metric' => MetricComponent.fromJson(json),
    'list' => ListComponent.fromJson(json),
    'timeline' => TimelineComponent.fromJson(json),
    'progress' => ProgressComponent.fromJson(json),
    'confirm' => ConfirmComponent.fromJson(json),
    'form' => FormComponent.fromJson(json),
    'card' => CardComponent.fromJson(json),
    _ => throw FormatException('Unknown component type: \${json[\'type\']}')
  };