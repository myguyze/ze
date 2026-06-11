import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';
import 'package:ze_app/src/components/widgets/table_widget.dart';
import 'package:ze_app/src/components/widgets/metric_widget.dart';
import 'package:ze_app/src/components/widgets/list_widget.dart';
import 'package:ze_app/src/components/widgets/timeline_widget.dart';
import 'package:ze_app/src/components/widgets/progress_widget.dart';
import 'package:ze_app/src/components/widgets/confirm_widget.dart';
import 'package:ze_app/src/components/widgets/form_widget.dart';
import 'package:ze_app/src/components/widgets/card_widget.dart';

Widget componentWidget(Map<String, dynamic> json, {void Function(String text)? onSend}) {
  try {
    final descriptor = componentFromJson(json);
    return switch (descriptor) {
      TableComponent c => TableWidget(component: c),
      MetricComponent c => MetricWidget(component: c),
      ListComponent c => ListWidget(component: c),
      TimelineComponent c => TimelineWidget(component: c),
      ProgressComponent c => ProgressWidget(component: c),
      ConfirmComponent c => ConfirmWidget(component: c, onSend: onSend),
      FormComponent c => FormWidget(component: c, onSend: onSend),
      CardComponent c => CardWidget(component: c),
      _ => const SizedBox.shrink(),
    };
  } catch (_) {
    return const SizedBox.shrink();
  }
}
