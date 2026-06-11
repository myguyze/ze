import 'package:flutter/material.dart';

class ContextFAB extends StatefulWidget {
  const ContextFAB({super.key, required this.onTap, this.isThinking = false});
  final VoidCallback onTap;
  final bool isThinking;

  @override
  State<ContextFAB> createState() => _ContextFABState();
}

class _ContextFABState extends State<ContextFAB> with SingleTickerProviderStateMixin {
  late AnimationController _pulse;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.primary;
    return GestureDetector(
      onTap: widget.onTap,
      child: AnimatedBuilder(
        animation: _pulse,
        builder: (ctx, child) {
          return Stack(
            alignment: Alignment.center,
            children: [
              if (widget.isThinking)
                Container(
                  width: 68 + _pulse.value * 12,
                  height: 68 + _pulse.value * 12,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(color: color.withOpacity(0.4 * (1 - _pulse.value)), width: 2),
                  ),
                ),
              FloatingActionButton(
                onPressed: widget.onTap,
                child: const Icon(Icons.chat_bubble_outline),
              ),
            ],
          );
        },
      ),
    );
  }
}
