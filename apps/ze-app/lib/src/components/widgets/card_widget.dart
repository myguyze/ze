import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';

class CardWidget extends StatelessWidget {
  const CardWidget({super.key, required this.component});
  final CardComponent component;

  static const _colors = {
    'info': Colors.blue,
    'warning': Colors.amber,
    'success': Colors.green,
    'error': Colors.red,
  };

  @override
  Widget build(BuildContext context) {
    final color = _colors[component.style] ?? Colors.blue;
    return Card(
      child: Container(
        decoration: BoxDecoration(
          border: Border(left: BorderSide(color: color, width: 4)),
          borderRadius: BorderRadius.circular(4),
        ),
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (component.title != null)
              Text(component.title!, style: Theme.of(context).textTheme.titleSmall),
            Text(component.body),
          ],
        ),
      ),
    );
  }
}
