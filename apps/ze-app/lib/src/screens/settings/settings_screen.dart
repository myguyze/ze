import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:ze_app/src/config/app_config.dart';
import 'package:ze_app/src/ws/providers.dart';

class SettingsScreen extends ConsumerStatefulWidget {
  const SettingsScreen({super.key});

  @override
  ConsumerState<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends ConsumerState<SettingsScreen> {
  final _formKey = GlobalKey<FormState>();
  late TextEditingController _urlCtrl;
  late TextEditingController _keyCtrl;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _urlCtrl = TextEditingController();
    _keyCtrl = TextEditingController();
    _load();
  }

  Future<void> _load() async {
    final config = await AppConfig.load();
    if (config != null) {
      _urlCtrl.text = config.serverUrl;
      _keyCtrl.text = config.apiKey;
    }
  }

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() => _saving = true);
    await AppConfig.save(serverUrl: _urlCtrl.text.trim(), apiKey: _keyCtrl.text.trim());
    ref.invalidate(wsClientProvider);
    if (mounted) {
      setState(() => _saving = false);
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Settings saved. Reconnecting…')));
    }
  }

  Future<void> _reset() async {
    await AppConfig.clear();
    if (mounted) Navigator.of(context).pushNamedAndRemoveUntil('/onboarding', (_) => false);
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
      appBar: AppBar(title: const Text('Settings')),
      body: Form(
        key: _formKey,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('Connection', style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            TextFormField(
              controller: _urlCtrl,
              decoration: const InputDecoration(labelText: 'Server URL', hintText: 'http://localhost:8000'),
              validator: (v) => (v == null || v.isEmpty) ? 'Required' : null,
              keyboardType: TextInputType.url,
            ),
            const SizedBox(height: 12),
            TextFormField(
              controller: _keyCtrl,
              decoration: const InputDecoration(labelText: 'API Key'),
              validator: (v) => (v == null || v.isEmpty) ? 'Required' : null,
              obscureText: true,
            ),
            const SizedBox(height: 24),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: _saving ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Save'),
            ),
            const SizedBox(height: 32),
            const Divider(),
            ListTile(
              title: const Text('Reset onboarding', style: TextStyle(color: Colors.red)),
              leading: const Icon(Icons.restart_alt, color: Colors.red),
              onTap: _reset,
            ),
          ],
        ),
      ),
    );
  }
}
