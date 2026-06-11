import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:ze_app/src/config/app_config.dart';
import 'package:ze_app/src/screens/chat/chat_screen.dart';
import 'package:ze_app/src/screens/goals/goals_screen.dart';
import 'package:ze_app/src/screens/news/news_screen.dart';
import 'package:ze_app/src/screens/reminders/reminders_screen.dart';
import 'package:ze_app/src/screens/contacts/contacts_screen.dart';
import 'package:ze_app/src/screens/costs/costs_screen.dart';
import 'package:ze_app/src/screens/settings/settings_screen.dart';
import 'package:ze_app/src/screens/onboarding/onboarding_flow.dart';
import 'package:ze_app/src/navigation/scaffold_with_nav.dart';

final routerProvider = Provider<GoRouter>((ref) {
  return GoRouter(
    initialLocation: '/',
    redirect: (context, state) async {
      final config = await AppConfig.load();
      if (config == null && state.matchedLocation != '/onboarding') {
        return '/onboarding';
      }
      return null;
    },
    routes: [
      GoRoute(path: '/onboarding', builder: (_, __) => const OnboardingFlow()),
      ShellRoute(
        builder: (context, state, child) => ScaffoldWithNav(child: child),
        routes: [
          GoRoute(path: '/', builder: (_, __) => const ChatScreen()),
          GoRoute(path: '/goals', builder: (_, __) => const GoalsScreen()),
          GoRoute(path: '/news', builder: (_, __) => const NewsScreen()),
          GoRoute(path: '/reminders', builder: (_, __) => const RemindersScreen()),
          GoRoute(path: '/contacts', builder: (_, __) => const ContactsScreen()),
          GoRoute(path: '/costs', builder: (_, __) => const CostsScreen()),
          GoRoute(path: '/settings', builder: (_, __) => const SettingsScreen()),
        ],
      ),
    ],
  );
});
