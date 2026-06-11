import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:ze_app/src/ws/providers.dart';
import 'package:ze_app/src/screens/chat/message_bubble.dart';
import 'package:ze_app/src/screens/chat/chat_input.dart';
import 'package:ze_app/src/screens/chat/typing_indicator.dart';

class ChatScreen extends ConsumerWidget {
  const ChatScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ws = ref.watch(wsStateProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Ze'),
        actions: [
          IconButton(icon: const Icon(Icons.more_vert), onPressed: () => Navigator.pushNamed(context, '/settings')),
        ],
      ),
      body: Column(
        children: [
          _StatusBanner(ws: ws),
          Expanded(child: _MessageList(ws: ws)),
          if (ws.isThinking) const TypingIndicator(),
          ChatInput(
            enabled: !ws.isThinking && ws.status != WsStatus.disconnected,
            onSend: (text) => ref.read(wsClientProvider.notifier).sendMessage(text),
          ),
        ],
      ),
    );
  }
}

class _StatusBanner extends StatelessWidget {
  const _StatusBanner({required this.ws});
  final WsState ws;

  @override
  Widget build(BuildContext context) {
    return switch (ws.status) {
      WsStatus.connecting => const MaterialBanner(
          content: Text('Connecting to Ze…'),
          backgroundColor: Colors.amber,
          actions: [SizedBox.shrink()],
        ),
      WsStatus.disconnected => MaterialBanner(
          content: const Text('Could not connect.'),
          backgroundColor: Colors.red,
          actions: [TextButton(onPressed: () {}, child: const Text('Retry'))],
        ),
      WsStatus.connected => const SizedBox.shrink(),
    };
  }
}

class _MessageList extends StatelessWidget {
  const _MessageList({required this.ws});
  final WsState ws;

  @override
  Widget build(BuildContext context) {
    if (ws.status == WsStatus.connecting && ws.messages.isEmpty) {
      return const _SkeletonList();
    }
    if (ws.messages.isEmpty) {
      return const _EmptyState();
    }
    return ListView.builder(
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: ws.messages.length,
      itemBuilder: (_, i) => MessageBubble(message: ws.messages[i]),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();
  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        const Icon(Icons.smart_toy_outlined, size: 64),
        const SizedBox(height: 16),
        const Text('Say hello', style: TextStyle(fontSize: 18)),
        const SizedBox(height: 12),
        ActionChip(label: const Text('What can you help me with?'), onPressed: () {}),
      ],
    ),
  );
}

class _SkeletonList extends StatelessWidget {
  const _SkeletonList();
  @override
  Widget build(BuildContext context) => Column(
    children: List.generate(3, (_) => Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      height: 60,
      decoration: BoxDecoration(color: Theme.of(context).colorScheme.surfaceVariant, borderRadius: BorderRadius.circular(12)),
    )),
  );
}
