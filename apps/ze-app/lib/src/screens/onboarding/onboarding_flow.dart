import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:ze_app/src/config/app_config.dart';
import 'package:ze_app/src/ws/providers.dart';

class OnboardingFlow extends ConsumerStatefulWidget {
  const OnboardingFlow({super.key});

  @override
  ConsumerState<OnboardingFlow> createState() => _OnboardingFlowState();
}

class _OnboardingFlowState extends ConsumerState<OnboardingFlow> {
  int _page = 0;
  final _urlCtrl = TextEditingController();
  final _keyCtrl = TextEditingController();
  bool _testing = false;
  bool? _testOk;
  String? _testError;

  Future<void> _testConnection() async {
    setState(() { _testing = true; _testOk = null; _testError = null; });
    try {
      final uri = Uri.parse('${_urlCtrl.text.trim()}/api/messages');
      final res = await http.get(uri, headers: {'X-API-Key': _keyCtrl.text.trim()}).timeout(const Duration(seconds: 8));
      setState(() { _testing = false; _testOk = res.statusCode < 400; });
    } catch (e) {
      setState(() { _testing = false; _testOk = false; _testError = e.toString(); });
    }
  }

  Future<void> _finish() async {
    await AppConfig.save(serverUrl: _urlCtrl.text.trim(), apiKey: _keyCtrl.text.trim());
    ref.invalidate(wsClientProvider);
    if (mounted) context.go('/');
  }

  @override
  void dispose() {
    _urlCtrl.dispose();
    _keyCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: PageView(
          physics: const NeverScrollableScrollPhysics(),
          children: [_WelcomePage(onNext: () => setState(() => _page = 1)),
            _ConnectPage(urlCtrl: _urlCtrl, keyCtrl: _keyCtrl, testing: _testing, testOk: _testOk, testError: _testError, onTest: _testConnection, onNext: () => setState(() => _page = 2)),
            _NotificationsPage(onDone: _finish),
          ],
        ),
      ),
    );
  }
}

class _WelcomePage extends StatelessWidget {
  const _WelcomePage({required this.onNext});
  final VoidCallback onNext;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(32),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.smart_toy_outlined, size: 80),
          const SizedBox(height: 24),
          Text('Ze', style: Theme.of(context).textTheme.displayMedium),
          const SizedBox(height: 12),
          const Text('Ze is your personal AI assistant.', textAlign: TextAlign.center),
          const SizedBox(height: 32),
          FilledButton(onPressed: onNext, child: const Text('Get started →')),
        ],
      ),
    ),
  );
}

class _ConnectPage extends StatelessWidget {
  const _ConnectPage({required this.urlCtrl, required this.keyCtrl, required this.testing, required this.testOk, required this.testError, required this.onTest, required this.onNext});
  final TextEditingController urlCtrl;
  final TextEditingController keyCtrl;
  final bool testing;
  final bool? testOk;
  final String? testError;
  final VoidCallback onTest;
  final VoidCallback onNext;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(32),
    child: Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Connect', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 24),
        TextField(controller: urlCtrl, decoration: const InputDecoration(labelText: 'Server URL', hintText: 'http://localhost:8000 or your server address', border: OutlineInputBorder())),
        const SizedBox(height: 12),
        TextField(controller: keyCtrl, obscureText: true, decoration: const InputDecoration(labelText: 'API Key', hintText: 'Find ZE_API_KEY in your backend .env file', border: OutlineInputBorder())),
        const SizedBox(height: 16),
        OutlinedButton(
          onPressed: testing ? null : onTest,
          child: testing ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Test connection'),
        ),
        if (testOk == true) const Padding(padding: EdgeInsets.only(top: 8), child: Text('✓ Connected', style: TextStyle(color: Colors.green))),
        if (testOk == false) Padding(padding: const EdgeInsets.only(top: 8), child: Text('Connection failed. ${testError ?? ''}', style: const TextStyle(color: Colors.red))),
        const SizedBox(height: 24),
        FilledButton(onPressed: testOk == true ? onNext : null, child: const Text('Continue →')),
      ],
    ),
  );
}

class _NotificationsPage extends StatelessWidget {
  const _NotificationsPage({required this.onDone});
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(32),
    child: Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Notifications', style: Theme.of(context).textTheme.headlineMedium),
        const SizedBox(height: 16),
        const Text('Install the ntfy app to receive notifications when Ze is backgrounded.'),
        const SizedBox(height: 24),
        FilledButton(onPressed: onDone, child: const Text('Done →')),
        const SizedBox(height: 8),
        TextButton(onPressed: onDone, child: const Text('Skip for now')),
      ],
    ),
  );
}
