import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';

class ConfirmWidget extends StatefulWidget {
  const ConfirmWidget({super.key, required this.component, this.onSend});
  final ConfirmComponent component;
  final void Function(String text)? onSend;

  @override
  State<ConfirmWidget> createState() => _ConfirmWidgetState();
}

class _ConfirmWidgetState extends State<ConfirmWidget> {
  String? _selected;

  void _tap(ConfirmActionItem action) {
    if (_selected != null) return;
    setState(() => _selected = action.value);
    widget.onSend?.call(action.value);
  }

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.component.prompt, style: Theme.of(context).textTheme.bodyMedium),
            const SizedBox(height: 8),
            if (_selected != null)
              Text('Selected: $_selected', style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.outline))
            else
              Wrap(
                spacing: 8,
                children: widget.component.actions.map((action) => _button(action)).toList(),
              ),
          ],
        ),
      ),
    );
  }

  Widget _button(ConfirmActionItem action) {
    return switch (action.style) {
      'danger' => FilledButton(onPressed: () => _tap(action), style: FilledButton.styleFrom(backgroundColor: Colors.red), child: Text(action.label)),
      'primary' => FilledButton(onPressed: () => _tap(action), child: Text(action.label)),
      _ => OutlinedButton(onPressed: () => _tap(action), child: Text(action.label)),
    };
  }
}
