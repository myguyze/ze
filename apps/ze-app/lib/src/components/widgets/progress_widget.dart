import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';

class ProgressWidget extends StatelessWidget {
  const ProgressWidget({super.key, required this.component});
  final ProgressComponent component;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(component.title, style: theme.textTheme.titleSmall),
        const SizedBox(height: 8),
        ...component.steps.map((step) => Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(
            children: [
              _StepIndicator(status: step.status),
              const SizedBox(width: 12),
              Text(step.label, style: theme.textTheme.bodyMedium),
            ],
          ),
        )),
      ],
    );
  }
}

class _StepIndicator extends StatelessWidget {
  const _StepIndicator({required this.status});
  final String status;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme;
    return switch (status) {
      'done' => CircleAvatar(radius: 10, backgroundColor: color.primary, child: const Icon(Icons.check, size: 12, color: Colors.white)),
      'active' => CircleAvatar(radius: 10, backgroundColor: color.primaryContainer, child: CircularProgressIndicator(strokeWidth: 2, color: color.primary)),
      _ => CircleAvatar(radius: 10, backgroundColor: Colors.transparent, child: CircleAvatar(radius: 9, backgroundColor: Colors.transparent, child: Container(decoration: BoxDecoration(border: Border.all(color: color.outline), shape: BoxShape.circle)))),
    };
  }
}
