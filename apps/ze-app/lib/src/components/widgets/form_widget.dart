import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';
import 'package:ze_app/src/components/form.dart' as ze_form;

class FormWidget extends StatefulWidget {
  const FormWidget({
    super.key,
    required this.component,
    this.componentId,
    this.onboardingSessionId,
    this.onSend,
    this.onComponentSubmit,
  });
  final FormComponent component;
  final String? componentId;
  final String? onboardingSessionId;
  final void Function(String text)? onSend;
  final void Function(String sessionId, String stepId, String componentId, Map<String, dynamic> values)? onComponentSubmit;

  @override
  State<FormWidget> createState() => _FormWidgetState();
}

class _FormWidgetState extends State<FormWidget> {
  final _formKey = GlobalKey<FormState>();
  final _values = <String, dynamic>{};
  final _multiValues = <String, Set<String>>{};

  void _submit() {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    _formKey.currentState!.save();
    final sessionId = widget.onboardingSessionId;
    final componentId = widget.componentId;
    if (sessionId != null && componentId != null && widget.onComponentSubmit != null) {
      widget.onComponentSubmit!(sessionId, componentId, componentId, Map<String, dynamic>.from(_values));
      return;
    }
    widget.onSend?.call('[form] ${jsonEncode(_values)}');
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _formKey,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(widget.component.title, style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 8),
          ...widget.component.fields.map(_buildField),
          const SizedBox(height: 12),
          FilledButton(onPressed: _submit, child: const Text('Submit')),
        ],
      ),
    );
  }

  Widget _buildField(ze_form.FormField f) {
    if (f.fieldType == 'boolean') {
      final current = (_values[f.id] as bool?) ?? (f.defaultValue == 'true');
      return CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(f.label),
        subtitle: f.helpText == null ? null : Text(f.helpText!),
        value: current,
        onChanged: (v) => setState(() => _values[f.id] = v ?? false),
      );
    }
    if (f.fieldType == 'multiselect' && f.options != null) {
      final selected = _multiValues.putIfAbsent(f.id, () => <String>{});
      return FormField<Set<String>>(
        validator: (_) => f.required && selected.isEmpty ? 'Required' : null,
        onSaved: (_) => _values[f.id] = selected.toList(),
        builder: (state) => Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(f.label, style: Theme.of(context).textTheme.bodyMedium),
              if (f.helpText != null) Text(f.helpText!, style: Theme.of(context).textTheme.bodySmall),
              ...f.options!.map((option) => CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text(option),
                    value: selected.contains(option),
                    onChanged: (checked) {
                      setState(() {
                        if (checked ?? false) {
                          selected.add(option);
                        } else {
                          selected.remove(option);
                        }
                        state.didChange(selected);
                      });
                    },
                  )),
              if (state.hasError) Text(state.errorText!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
          ),
        ),
      );
    }
    if (f.fieldType == 'select' && f.options != null) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: DropdownButtonFormField<String>(
          value: f.defaultValue,
          decoration: InputDecoration(labelText: f.label, helperText: f.helpText),
          items: f.options!.map((o) => DropdownMenuItem(value: o, child: Text(o))).toList(),
          onChanged: (v) => _values[f.id] = v ?? '',
          onSaved: (v) => _values[f.id] = v ?? '',
          validator: (v) => f.required && (v == null || v.isEmpty) ? 'Required' : null,
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: TextFormField(
        initialValue: f.defaultValue,
        decoration: InputDecoration(labelText: f.label, hintText: f.placeholder, helperText: f.helpText),
        keyboardType: f.fieldType == 'number' ? TextInputType.number : TextInputType.text,
        maxLines: f.fieldType == 'textarea' || f.fieldType == 'chips' ? null : 1,
        onSaved: (v) => _values[f.id] = f.fieldType == 'chips' ? _splitChips(v ?? '') : v ?? '',
        validator: (v) => f.required && (v == null || v.isEmpty) ? 'Required' : null,
      ),
    );
  }

  List<String> _splitChips(String value) => value
      .split(',')
      .map((item) => item.trim())
      .where((item) => item.isNotEmpty)
      .toList();
}
