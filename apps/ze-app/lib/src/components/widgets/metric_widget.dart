import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';

class MetricWidget extends StatelessWidget {
  const MetricWidget({super.key, required this.component});
  final MetricComponent component;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(component.value, style: theme.textTheme.displaySmall?.copyWith(fontWeight: FontWeight.bold)),
          Text(component.label, style: theme.textTheme.bodyMedium),
          if (component.trend != null)
            Chip(label: Text(component.trend!), visualDensity: VisualDensity.compact),
          if (component.note != null)
            Text(component.note!, style: theme.textTheme.bodySmall),
        ],
      ),
    );
  }
}
