import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:ze_app/src/ws/ws_protocol.dart';

// Screen data providers — defined in their respective screen files,
// referenced here by name. These will be populated as screens are built.

// ignore: prefer_function_declarations_over_variables
final handleRefreshFrame = (RefreshFrame frame, WidgetRef ref) {
  switch (frame.screen) {
    case 'goals':     ref.invalidate(goalsProvider);
    case 'reminders': ref.invalidate(remindersProvider);
    case 'contacts':  ref.invalidate(contactsProvider);
    case 'costs':     ref.invalidate(costsProvider);
    case 'news':      ref.invalidate(newsProvider);
  }
};

// Provider stubs — will be replaced by real providers in screen files
final goalsProvider = FutureProvider<List<dynamic>>((_) async => []);
final remindersProvider = FutureProvider<List<dynamic>>((_) async => []);
final contactsProvider = FutureProvider<List<dynamic>>((_) async => []);
final costsProvider = FutureProvider<List<dynamic>>((_) async => []);
final newsProvider = FutureProvider<List<dynamic>>((_) async => []);
