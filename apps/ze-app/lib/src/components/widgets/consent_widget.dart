import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';

class ConsentWidget extends StatelessWidget {
  const ConsentWidget({
    super.key,
    required this.component,
    this.onboardingSessionId,
    this.onComponentSubmit,
  });

  final ConsentComponent component;
  final String? onboardingSessionId;
  final void Function(String sessionId, String stepId, String componentId, Map<String, dynamic> values)? onComponentSubmit;

  void _submit(String action) {
    final sessionId = onboardingSessionId;
    if (sessionId == null || onComponentSubmit == null) return;
    onComponentSubmit!(sessionId, component.id, component.id, {
      'action': action,
      'scopes': component.scopes.map((scope) => scope.id).toList(),
    });
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
            const SizedBox(height: 4),
            Text(component.body),
            const SizedBox(height: 8),
            ...component.scopes.map((scope) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(scope.label),
                  subtitle: Text(scope.description),
                  trailing: scope.required ? const Text('Required') : null,
                )),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              children: [
                FilledButton(onPressed: () => _submit('approve'), child: Text(component.acceptLabel)),
                OutlinedButton(onPressed: () => _submit('skip'), child: Text(component.rejectLabel)),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
