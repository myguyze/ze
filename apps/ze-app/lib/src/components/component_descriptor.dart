// GENERATED — do not edit. Run make generate-components to regenerate.
import 'package:ze_app/src/components/list.dart';
export 'package:ze_app/src/components/list.dart';
import 'package:ze_app/src/components/timeline.dart';
export 'package:ze_app/src/components/timeline.dart';
import 'package:ze_app/src/components/progress.dart';
export 'package:ze_app/src/components/progress.dart';
import 'package:ze_app/src/components/confirm.dart';
export 'package:ze_app/src/components/confirm.dart';
import 'package:ze_app/src/components/form.dart';
export 'package:ze_app/src/components/form.dart';
import 'package:ze_app/src/components/choice_option.dart';
export 'package:ze_app/src/components/choice_option.dart';
import 'package:ze_app/src/components/consent_scope.dart';
export 'package:ze_app/src/components/consent_scope.dart';
import 'package:ze_app/src/components/review.dart';
export 'package:ze_app/src/components/review.dart';
import 'package:ze_app/src/components/table_component.dart';
export 'package:ze_app/src/components/table_component.dart';
import 'package:ze_app/src/components/metric_component.dart';
export 'package:ze_app/src/components/metric_component.dart';
import 'package:ze_app/src/components/list_component.dart';
export 'package:ze_app/src/components/list_component.dart';
import 'package:ze_app/src/components/timeline_component.dart';
export 'package:ze_app/src/components/timeline_component.dart';
import 'package:ze_app/src/components/progress_component.dart';
export 'package:ze_app/src/components/progress_component.dart';
import 'package:ze_app/src/components/confirm_component.dart';
export 'package:ze_app/src/components/confirm_component.dart';
import 'package:ze_app/src/components/form_component.dart';
export 'package:ze_app/src/components/form_component.dart';
import 'package:ze_app/src/components/card_component.dart';
export 'package:ze_app/src/components/card_component.dart';
import 'package:ze_app/src/components/choice_group_component.dart';
export 'package:ze_app/src/components/choice_group_component.dart';
import 'package:ze_app/src/components/consent_component.dart';
export 'package:ze_app/src/components/consent_component.dart';
import 'package:ze_app/src/components/connect_account_component.dart';
export 'package:ze_app/src/components/connect_account_component.dart';
import 'package:ze_app/src/components/review_component.dart';
export 'package:ze_app/src/components/review_component.dart';

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
    'choice_group' => ChoiceGroupComponent.fromJson(json),
    'consent' => ConsentComponent.fromJson(json),
    'connect_account' => ConnectAccountComponent.fromJson(json),
    'review' => ReviewComponent.fromJson(json),
    _ => throw FormatException('Unknown component type: \${json[\'type\']}')
  };