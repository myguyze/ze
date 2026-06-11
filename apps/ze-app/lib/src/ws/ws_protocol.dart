import 'dart:convert';
import 'package:ze_app/src/messages/message.dart';

sealed class InboundFrame {}

class MessageFrame extends InboundFrame {
  MessageFrame({required this.message});
  final Message message;
}

class EditFrame extends InboundFrame {
  EditFrame({required this.id, this.text, required this.components});
  final String id;
  final String? text;
  final List<Map<String, dynamic>> components;
}

class ConfirmRequestFrame extends InboundFrame {
  ConfirmRequestFrame({required this.id, required this.prompt, required this.actions});
  final String id;
  final String prompt;
  final List<ConfirmAction> actions;
}

class ConfirmCancelFrame extends InboundFrame {
  ConfirmCancelFrame({required this.id});
  final String id;
}

class TypingFrame extends InboundFrame {}

class ErrorFrame extends InboundFrame {
  ErrorFrame({required this.detail});
  final String detail;
}

class RefreshFrame extends InboundFrame {
  RefreshFrame({required this.screen});
  final String screen;
}

class PongFrame extends InboundFrame {}

class ConfirmAction {
  ConfirmAction({required this.label, required this.value, required this.style});
  final String label;
  final String value;
  final String style;

  factory ConfirmAction.fromJson(Map<String, dynamic> j) =>
      ConfirmAction(label: j['label'] as String, value: j['value'] as String, style: (j['style'] as String?) ?? 'secondary');
}

InboundFrame? parseInboundFrame(String raw) {
  final j = jsonDecode(raw) as Map<String, dynamic>;
  final type = j['type'] as String?;
  return switch (type) {
    'message' => MessageFrame(message: _messageFromFrame(j)),
    'edit' => EditFrame(
        id: j['id'] as String,
        text: j['text'] as String?,
        components: (j['components'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>(),
      ),
    'confirm_request' => ConfirmRequestFrame(
        id: j['id'] as String,
        prompt: j['prompt'] as String,
        actions: (j['actions'] as List<dynamic>).map((a) => ConfirmAction.fromJson(a as Map<String, dynamic>)).toList(),
      ),
    'confirm_cancel' => ConfirmCancelFrame(id: j['id'] as String),
    'typing' => TypingFrame(),
    'error' => ErrorFrame(detail: j['detail'] as String? ?? 'Unknown error'),
    'refresh' => RefreshFrame(screen: j['screen'] as String),
    'pong' => PongFrame(),
    _ => null,
  };
}


sealed class OutboundFrame {
  Map<String, dynamic> toJson();
}

class SendMessageFrame extends OutboundFrame {
  SendMessageFrame({required this.text, this.threadId, this.context});
  final String text;
  final String? threadId;
  final Map<String, String>? context;

  @override
  Map<String, dynamic> toJson() => {
    'type': 'message',
    'text': text,
    if (threadId != null) 'thread_id': threadId,
    if (context != null) 'context': context,
  };
}

class AckFrame extends OutboundFrame {
  AckFrame({required this.ids});
  final List<String> ids;

  @override
  Map<String, dynamic> toJson() => {'type': 'ack', 'ids': ids};
}

class CommandFrame extends OutboundFrame {
  CommandFrame({required this.name});
  final String name;

  @override
  Map<String, dynamic> toJson() => {'type': 'command', 'name': name};
}

class PingFrame extends OutboundFrame {
  @override
  Map<String, dynamic> toJson() => {'type': 'ping'};
}

class ComponentSubmitFrame extends OutboundFrame {
  ComponentSubmitFrame({
    required this.sessionId,
    required this.stepId,
    required this.componentId,
    required this.values,
  });

  final String sessionId;
  final String stepId;
  final String componentId;
  final Map<String, dynamic> values;

  @override
  Map<String, dynamic> toJson() => {
    'type': 'component_submit',
    'session_id': sessionId,
    'step_id': stepId,
    'component_id': componentId,
    'values': values,
  };
}

Message _messageFromFrame(Map<String, dynamic> frame) {
  final message = Map<String, dynamic>.from(frame['message'] as Map<String, dynamic>);
  final onboarding = frame['onboarding'] as Map<String, dynamic>?;
  if (onboarding != null) {
    message['onboarding_session_id'] = onboarding['session_id'];
    message['onboarding_completed'] = onboarding['completed'];
  }
  return Message.fromJson(message);
}
