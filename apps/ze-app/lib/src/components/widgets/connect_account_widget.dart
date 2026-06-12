import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';

class ConnectAccountWidget extends StatelessWidget {
  const ConnectAccountWidget({
    super.key,
    required this.component,
    this.onboardingSessionId,
    this.onComponentSubmit,
  });

  final ConnectAccountComponent component;
  final String? onboardingSessionId;
  final void Function(String sessionId, String stepId, String componentId, Map<String, dynamic> values)? onComponentSubmit;

  void _submit() {
    final sessionId = onboardingSessionId;
    if (sessionId == null || onComponentSubmit == null) return;
    onComponentSubmit!(sessionId, component.id, component.id, {
      'action': 'connect',
      'provider': component.provider,
    });
  }

  @override
  Widget build(BuildContext context) {
    final connected = component.status == 'connected';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(component.title, style: Theme.of(context).textTheme.titleSmall),
            const SizedBox(height: 4),
            Text(component.description),
            const SizedBox(height: 8),
            FilledButton.icon(
              onPressed: connected ? null : _submit,
              icon: Icon(connected ? Icons.check_circle_outline : Icons.link),
              label: Text(connected ? 'Connected' : component.actionLabel),
            ),
          ],
        ),
      ),
    );
  }
}
