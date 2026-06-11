import 'dart:async';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:ze_app/src/config/app_config.dart';
import 'package:ze_app/src/ws/ws_protocol.dart';

class ZeWebSocketClient {
  ZeWebSocketClient({required this.config});

  final AppConfig config;

  WebSocketChannel? _channel;
  StreamController<InboundFrame>? _controller;
  bool _disposed = false;
  int _retryDelay = 1;
  Timer? _reconnectTimer;
  Timer? _pingTimer;

  Stream<InboundFrame> get frames => (_controller ??= StreamController.broadcast()).stream;

  bool get isConnected => _channel != null;

  Future<void> connect() async {
    if (_disposed) return;
    _reconnectTimer?.cancel();
    _controller ??= StreamController.broadcast();

    try {
      final uri = Uri.parse(config.wsUrl);
      _channel = WebSocketChannel.connect(uri);
      await _channel!.ready;
      _retryDelay = 1;
      _startPing();
      _channel!.stream.listen(
        _onData,
        onError: (_) => _scheduleReconnect(),
        onDone: _scheduleReconnect,
      );
    } catch (_) {
      _scheduleReconnect();
    }
  }

  void send(OutboundFrame frame) {
    if (_channel == null) return;
    _channel!.sink.add(jsonEncode(frame.toJson()));
  }

  void _onData(dynamic data) {
    final frame = parseInboundFrame(data as String);
    if (frame != null) _controller?.add(frame);
  }

  void _scheduleReconnect() {
    _channel = null;
    _pingTimer?.cancel();
    if (_disposed) return;
    _reconnectTimer = Timer(Duration(seconds: _retryDelay), () {
      _retryDelay = (_retryDelay * 2).clamp(1, 30);
      connect();
    });
  }

  void _startPing() {
    _pingTimer?.cancel();
    _pingTimer = Timer.periodic(const Duration(seconds: 30), (_) => send(PingFrame()));
  }

  void dispose() {
    _disposed = true;
    _reconnectTimer?.cancel();
    _pingTimer?.cancel();
    _channel?.sink.close();
    _controller?.close();
  }
}
