import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:ze_app/src/overlay/overlay_controller.dart';
import 'package:ze_app/src/screens/chat/chat_input.dart';
import 'package:ze_app/src/screens/chat/message_bubble.dart';
import 'package:ze_app/src/screens/chat/typing_indicator.dart';
import 'package:ze_app/src/messages/message.dart';
import 'package:ze_app/src/ws/providers.dart';

class ContextOverlay extends ConsumerStatefulWidget {
  const ContextOverlay({super.key, required this.controller, required this.child});
  final OverlayController controller;
  final Widget child;

  @override
  ConsumerState<ContextOverlay> createState() => _ContextOverlayState();
}

class _ContextOverlayState extends ConsumerState<ContextOverlay> {
  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        widget.child,
        ListenableBuilder(
          listenable: widget.controller,
          builder: (ctx, _) {
            if (!widget.controller.isOpen) return const SizedBox.shrink();
            return _OverlaySheet(controller: widget.controller);
          },
        ),
      ],
    );
  }
}

class _OverlaySheet extends ConsumerWidget {
  const _OverlaySheet({required this.controller});
  final OverlayController controller;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final wsState = ref.watch(wsStateProvider);
    return DraggableScrollableSheet(
      initialChildSize: 0.4,
      minChildSize: 0.2,
      maxChildSize: 0.8,
      builder: (ctx, scrollController) => Material(
        elevation: 8,
        borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
        child: Column(
          children: [
            _Handle(onClose: controller.close),
            Expanded(
              child: ListView(
                controller: scrollController,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                children: wsState.overlayMessages.map((m) => MessageBubble(message: m)).toList(),
              ),
            ),
            if (wsState.isThinking) const TypingIndicator(),
            ChatInput(
              enabled: !wsState.isThinking,
              onSend: (text) {
                final screenCtx = <String, String>{
                  if (controller.screenContext != null) 'screen': controller.screenContext!,
                  if (controller.entityId != null) 'entity_id': controller.entityId!,
                };
                ref.read(wsClientProvider.notifier).sendMessage(text, context: screenCtx.isEmpty ? null : screenCtx);
              },
            ),
          ],
        ),
      ),
    );
  }
}

class _Handle extends StatelessWidget {
  const _Handle({required this.onClose});
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      child: Row(
        children: [
          const Expanded(child: Center(child: _DragHandle())),
          IconButton(icon: const Icon(Icons.close), onPressed: onClose, tooltip: 'Dismiss'),
        ],
      ),
    );
  }
}

class _DragHandle extends StatelessWidget {
  const _DragHandle();
  @override
  Widget build(BuildContext context) => Container(
    width: 40, height: 4,
    decoration: BoxDecoration(color: Theme.of(context).colorScheme.outlineVariant, borderRadius: BorderRadius.circular(2)),
  );
}
