import 'dart:async';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:ze_app/src/config/app_config.dart';
import 'package:ze_app/src/messages/message.dart';
import 'package:ze_app/src/messages/message_repository.dart';
import 'package:ze_app/src/ws/ws_client.dart';
import 'package:ze_app/src/ws/ws_protocol.dart';

// ── AppConfig provider ─────────────────────────────────────────────────────────

final appConfigProvider = StateProvider<AppConfig?>((ref) => null);

// ── WebSocket state ────────────────────────────────────────────────────────────

enum WsStatus { connecting, connected, disconnected }

class WsState {
  const WsState({
    this.status = WsStatus.connecting,
    this.messages = const [],
    this.overlayMessages = const [],
    this.isThinking = false,
  });

  final WsStatus status;
  final List<Message> messages;
  final List<Message> overlayMessages;
  final bool isThinking;

  bool get isConnected => status == WsStatus.connected;

  WsState copyWith({WsStatus? status, List<Message>? messages, List<Message>? overlayMessages, bool? isThinking}) => WsState(
    status: status ?? this.status,
    messages: messages ?? this.messages,
    overlayMessages: overlayMessages ?? this.overlayMessages,
    isThinking: isThinking ?? this.isThinking,
  );
}

class WsClientNotifier extends StateNotifier<WsState> {
  WsClientNotifier(this._config) : super(const WsState()) {
    _repo = MessageRepository();
    _client = ZeWebSocketClient(config: _config);
    _init();
  }

  final AppConfig _config;
  late ZeWebSocketClient _client;
  late MessageRepository _repo;
  StreamSubscription<InboundFrame>? _sub;

  Future<void> _init() async {
    await _client.connect();
    state = state.copyWith(status: WsStatus.connected);
    _sub = _client.frames.listen(_handleFrame, onError: (_) {
      state = state.copyWith(status: WsStatus.disconnected);
    });
    await _repo.loadHistory(_config);
    _refresh();
    final unread = _repo.unreadAssistantIds;
    if (unread.isNotEmpty) _client.send(AckFrame(ids: unread));
  }

  void _handleFrame(InboundFrame frame) {
    switch (frame) {
      case MessageFrame(message: final m):
        _repo.add(m);
        state = state.copyWith(messages: _repo.messages, isThinking: false, status: WsStatus.connected);
      case TypingFrame():
        state = state.copyWith(isThinking: true);
      case EditFrame(id: final id, text: final text, components: final comps):
        final existing = _repo.messages.firstWhere((m) => m.id == id, orElse: () => Message(id: id, role: MessageRole.assistant, text: text, createdAt: DateTime.now()));
        _repo.update(id, Message(id: id, role: existing.role, text: text ?? existing.text, createdAt: existing.createdAt, components: comps));
        state = state.copyWith(messages: _repo.messages);
      case RefreshFrame():
        break;
      case ErrorFrame():
        state = state.copyWith(isThinking: false);
      case _:
        break;
    }
  }

  void sendMessage(String text, {Map<String, String>? context}) {
    _client.send(SendMessageFrame(text: text, context: context));
    final msg = Message(id: 'local_${DateTime.now().millisecondsSinceEpoch}', role: MessageRole.user, text: text, createdAt: DateTime.now());
    _repo.add(msg);
    state = state.copyWith(messages: _repo.messages, isThinking: true);
  }

  void _refresh() => state = state.copyWith(messages: _repo.messages);

  @override
  void dispose() {
    _sub?.cancel();
    _client.dispose();
    super.dispose();
  }
}

final wsClientProvider = StateNotifierProvider<WsClientNotifier, WsState>((ref) {
  final config = ref.watch(appConfigProvider);
  if (config == null) {
    return WsClientNotifier(AppConfig(serverUrl: '', apiKey: ''));
  }
  return WsClientNotifier(config);
});

final wsStateProvider = Provider<WsState>((ref) => ref.watch(wsClientProvider));
