import 'package:flutter/material.dart';

class GoalDetail extends StatelessWidget {
  const GoalDetail({super.key, required this.goalId});
  final String goalId;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Goal')),
      body: const Center(child: Text('Goal detail coming soon.')),
    );
  }
}
