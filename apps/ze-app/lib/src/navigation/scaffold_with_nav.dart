import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:ze_app/src/overlay/overlay_controller.dart';
import 'package:ze_app/src/overlay/fab.dart';
import 'package:ze_app/src/overlay/context_overlay.dart';
import 'package:ze_app/src/ws/providers.dart';

final overlayControllerProvider = Provider<OverlayController>((ref) => OverlayController());

class ScaffoldWithNav extends ConsumerWidget {
  const ScaffoldWithNav({super.key, required this.child});
  final Widget child;

  static const _tabs = [
    (label: 'Chat', icon: Icons.chat_bubble_outline, path: '/'),
    (label: 'Goals', icon: Icons.flag_outlined, path: '/goals'),
    (label: 'News', icon: Icons.newspaper_outlined, path: '/news'),
    (label: 'More', icon: Icons.more_horiz, path: '/__more'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final overlayCtrl = ref.watch(overlayControllerProvider);
    final wsState = ref.watch(wsStateProvider);
    final location = GoRouterState.of(context).matchedLocation;
    final isChat = location == '/';

    return Shortcuts(
      shortcuts: {
        const SingleActivator(LogicalKeyboardKey.keyK, meta: true): const _OpenOverlayIntent(),
      },
      child: Actions(
        actions: {
          _OpenOverlayIntent: CallbackAction<_OpenOverlayIntent>(
            onInvoke: (_) => overlayCtrl.open(screen: _screenFromPath(location)),
          ),
        },
        child: ContextOverlay(
          controller: overlayCtrl,
          child: Scaffold(
            body: child,
            floatingActionButton: isChat
                ? null
                : ContextFAB(
                    isThinking: wsState.isThinking,
                    onTap: () => overlayCtrl.open(screen: _screenFromPath(location)),
                  ),
            bottomNavigationBar: NavigationBar(
              selectedIndex: _selectedIndex(location),
              onDestinationSelected: (i) => _onTab(context, i),
              destinations: _tabs.map((t) => NavigationDestination(
                icon: Icon(t.icon),
                label: t.label,
              )).toList(),
            ),
          ),
        ),
      ),
    );
  }

  int _selectedIndex(String location) {
    if (location == '/') return 0;
    if (location.startsWith('/goals')) return 1;
    if (location.startsWith('/news')) return 2;
    return 3;
  }

  void _onTab(BuildContext context, int index) {
    switch (index) {
      case 0: context.go('/');
      case 1: context.go('/goals');
      case 2: context.go('/news');
      case 3: _showMorePanel(context);
    }
  }

  void _showMorePanel(BuildContext context) {
    showModalBottomSheet(context: context, builder: (_) => _MorePanel());
  }

  String? _screenFromPath(String path) {
    return switch (path) {
      '/' => 'chat',
      '/goals' => 'goals',
      '/news' => 'news',
      '/reminders' => 'reminders',
      '/contacts' => 'contacts',
      '/costs' => 'costs',
      _ => null,
    };
  }
}

class _MorePanel extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final items = [
      (label: 'Reminders', icon: Icons.alarm_outlined, path: '/reminders'),
      (label: 'Contacts', icon: Icons.contacts_outlined, path: '/contacts'),
      (label: 'Costs', icon: Icons.attach_money_outlined, path: '/costs'),
      (label: 'Finance', icon: Icons.bar_chart_outlined, path: null),
      (label: 'Legal', icon: Icons.gavel_outlined, path: null),
      (label: 'Settings', icon: Icons.settings_outlined, path: '/settings'),
    ];
    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: items.map((item) => ListTile(
          leading: Icon(item.icon),
          title: Text(item.label),
          trailing: item.path == null ? const Chip(label: Text('Coming soon'), visualDensity: VisualDensity.compact) : null,
          onTap: item.path != null ? () { Navigator.pop(context); context.go(item.path!); } : null,
        )).toList(),
      ),
    );
  }
}

class _OpenOverlayIntent extends Intent {
  const _OpenOverlayIntent();
}
