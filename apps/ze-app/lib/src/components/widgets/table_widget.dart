import 'package:flutter/material.dart';
import 'package:ze_app/src/components/component_descriptor.dart';

class TableWidget extends StatelessWidget {
  const TableWidget({super.key, required this.component});
  final TableComponent component;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxHeight: 280),
      child: SingleChildScrollView(
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
            columns: component.headers.map((h) => DataColumn(label: Text(h, style: const TextStyle(fontWeight: FontWeight.bold)))).toList(),
            rows: component.rows.map((row) => DataRow(
              cells: row.map((cell) => DataCell(Text(cell))).toList(),
            )).toList(),
          ),
        ),
      ),
    );
  }
}
