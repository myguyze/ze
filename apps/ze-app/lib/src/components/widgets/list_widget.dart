import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';

class ListWidget extends StatelessWidget {
  const ListWidget({super.key, required this.component});
  final ListComponent component;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (component.title != null)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Text(component.title!, style: Theme.of(context).textTheme.titleSmall),
          ),
        ...component.items.map((item) => ListTile(
          dense: true,
          title: Text(item.text),
          subtitle: item.subtext != null ? Text(item.subtext!) : null,
          trailing: item.status != null ? Chip(label: Text(item.status!), visualDensity: VisualDensity.compact) : null,
        )),
      ],
    );
  }
}
