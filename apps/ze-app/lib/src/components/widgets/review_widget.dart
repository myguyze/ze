import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';

class ReviewWidget extends StatelessWidget {
  const ReviewWidget({
    super.key,
    required this.component,
    this.onboardingSessionId,
    this.onComponentSubmit,
  });

  final ReviewComponent component;
  final String? onboardingSessionId;
  final void Function(String sessionId, String stepId, String componentId, Map<String, dynamic> values)? onComponentSubmit;

  void _submit(String action) {
    final sessionId = onboardingSessionId;
    if (sessionId == null || onComponentSubmit == null) return;
    onComponentSubmit!(sessionId, component.id, component.id, {'action': action});
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(component.title, style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 8),
            ...component.items.map((item) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(item.label),
                  subtitle: Text([
                    item.value,
                    if (item.plugin != null) item.plugin!,
                    item.kind,
                  ].join(' · ')),
                )),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                FilledButton(onPressed: () => _submit('approve'), child: Text(component.approveLabel)),
                OutlinedButton(onPressed: () => _submit('edit'), child: Text(component.rejectLabel)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
