import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';

class TimelineWidget extends StatelessWidget {
  const TimelineWidget({super.key, required this.component});
  final TimelineComponent component;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (component.title != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(component.title!, style: theme.textTheme.titleSmall),
          ),
        ...component.events.map((event) => IntrinsicHeight(
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 80,
                child: Text(event.time, style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.outline)),
              ),
              Column(
                children: [
                  const SizedBox(height: 4),
                  CircleAvatar(radius: 4, backgroundColor: theme.colorScheme.primary),
                  Expanded(child: VerticalDivider(width: 1, color: theme.colorScheme.outlineVariant)),
                ],
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(event.title, style: theme.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w500)),
                      if (event.description != null)
                        Text(event.description!, style: theme.textTheme.bodySmall),
                    ],
                  ),
                ),
              ),
            ],
          ),
        )),
      ],
    );
  }
}
