import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';

class FormWidget extends StatefulWidget {
  const FormWidget({super.key, required this.component, this.onSend});
  final FormComponent component;
  final void Function(String text)? onSend;

  @override
  State<FormWidget> createState() => _FormWidgetState();
}

class _FormWidgetState extends State<FormWidget> {
  final _formKey = GlobalKey<FormState>();
  final _values = <String, String>{};

  void _submit() {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    _formKey.currentState!.save();
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

  Widget _buildField(FormField f) {
    if (f.fieldType == 'select' && f.options != null) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: DropdownButtonFormField<String>(
          decoration: InputDecoration(labelText: f.label),
          items: f.options!.map((o) => DropdownMenuItem(value: o, child: Text(o))).toList(),
          onChanged: (v) => _values[f.id] = v ?? '',
          onSaved: (v) => _values[f.id] = v ?? '',
          validator: (v) => (v == null || v.isEmpty) ? 'Required' : null,
        ),
      );
    }
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: TextFormField(
        decoration: InputDecoration(labelText: f.label, hintText: f.placeholder),
        keyboardType: f.fieldType == 'number' ? TextInputType.number : TextInputType.text,
        onSaved: (v) => _values[f.id] = v ?? '',
        validator: (v) => (v == null || v.isEmpty) ? 'Required' : null,
      ),
    );
  }
}
