import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';

class ChoiceGroupWidget extends StatefulWidget {
  const ChoiceGroupWidget({
    super.key,
    required this.component,
    this.onboardingSessionId,
    this.onComponentSubmit,
  });

  final ChoiceGroupComponent component;
  final String? onboardingSessionId;
  final void Function(String sessionId, String stepId, String componentId, Map<String, dynamic> values)? onComponentSubmit;

  @override
  State<ChoiceGroupWidget> createState() => _ChoiceGroupWidgetState();
}

class _ChoiceGroupWidgetState extends State<ChoiceGroupWidget> {
  final _selected = <String>{};

  void _submit() {
    final sessionId = widget.onboardingSessionId;
    if (sessionId == null || widget.onComponentSubmit == null || _selected.isEmpty) return;
    widget.onComponentSubmit!(
      sessionId,
      widget.component.id,
      widget.component.id,
      widget.component.allowMultiple ? {'choices': _selected.toList()} : {'choice': _selected.first},
    );
  }

  @override
  Widget build(BuildContext context) {
    final c = widget.component;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(c.title, style: Theme.of(context).textTheme.titleSmall),
            if (c.description != null) Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(c.description!),
            ),
            const SizedBox(height: 8),
            ...c.options.map((option) => _optionTile(option)),
            const SizedBox(height: 8),
            FilledButton(onPressed: _selected.isEmpty ? null : _submit, child: Text(c.submitLabel)),
          ],
        ),
      ),
    );
  }

  Widget _optionTile(ChoiceOption option) {
    final selected = _selected.contains(option.id);
    final title = option.recommended ? '${option.label} (recommended)' : option.label;
    if (widget.component.allowMultiple) {
      return CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(title),
        subtitle: option.description == null ? null : Text(option.description!),
        value: selected,
        onChanged: (checked) => setState(() {
          if (checked ?? false) {
            _selected.add(option.id);
          } else {
            _selected.remove(option.id);
          }
        }),
      );
    }
    return RadioListTile<String>(
      contentPadding: EdgeInsets.zero,
      title: Text(title),
      subtitle: option.description == null ? null : Text(option.description!),
      value: option.id,
      groupValue: selected ? option.id : (_selected.isEmpty ? null : _selected.first),
      onChanged: (value) => setState(() {
        _selected
          ..clear()
          ..add(value ?? option.id);
      }),
    );
  }
}
