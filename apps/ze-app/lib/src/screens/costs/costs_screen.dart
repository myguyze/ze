import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:ze_app/src/navigation/refresh_handler.dart';

class CostsScreen extends ConsumerWidget {
  const CostsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final costs = ref.watch(costsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Costs')),
      body: costs.when(
        data: (_) => const Center(child: Text('No cost data yet.')),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Error: $e')),
      ),
    );
  }
}
