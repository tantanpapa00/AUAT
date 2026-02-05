import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/app_state.dart';
import '../services/api_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late TextEditingController _urlController;
  bool _isTesting = false;
  String? _testResult;

  @override
  void initState() {
    super.initState();
    final appState = context.read<AppState>();
    _urlController = TextEditingController(text: appState.serverUrl);
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  Future<void> _testConnection() async {
    setState(() {
      _isTesting = true;
      _testResult = null;
    });

    final url = _urlController.text.trim();
    final apiService = context.read<ApiService>();
    apiService.setBaseUrl(url);

    try {
      final connected = await apiService.healthCheck();
      setState(() {
        _testResult = connected ? 'success' : 'failed';
      });
    } catch (e) {
      setState(() {
        _testResult = 'error';
      });
    }

    setState(() => _isTesting = false);
  }

  void _saveSettings() {
    final url = _urlController.text.trim();
    if (url.isNotEmpty) {
      context.read<AppState>().setServerUrl(url);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Settings saved'),
          backgroundColor: Colors.green,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Server Connection
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.dns, size: 20),
                      const SizedBox(width: 8),
                      const Text(
                        'Server Connection',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Enter the URL of your BBooster server',
                    style: TextStyle(color: Colors.grey.shade500, fontSize: 13),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _urlController,
                    decoration: InputDecoration(
                      labelText: 'Server URL',
                      hintText: 'http://192.168.1.100:8000',
                      border: const OutlineInputBorder(),
                      prefixIcon: const Icon(Icons.link),
                      suffixIcon: IconButton(
                        icon: const Icon(Icons.content_paste),
                        onPressed: () async {
                          final data = await Clipboard.getData('text/plain');
                          if (data?.text != null) {
                            _urlController.text = data!.text!;
                          }
                        },
                      ),
                    ),
                    keyboardType: TextInputType.url,
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          onPressed: _isTesting ? null : _testConnection,
                          icon: _isTesting
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Icon(Icons.wifi_find),
                          label: const Text('Test'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: FilledButton.icon(
                          onPressed: _saveSettings,
                          icon: const Icon(Icons.save),
                          label: const Text('Save'),
                        ),
                      ),
                    ],
                  ),
                  if (_testResult != null) ...[
                    const SizedBox(height: 12),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: _testResult == 'success'
                            ? Colors.green.withOpacity(0.1)
                            : Colors.red.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                          color: _testResult == 'success'
                              ? Colors.green
                              : Colors.red,
                        ),
                      ),
                      child: Row(
                        children: [
                          Icon(
                            _testResult == 'success'
                                ? Icons.check_circle
                                : Icons.error,
                            color: _testResult == 'success'
                                ? Colors.green
                                : Colors.red,
                          ),
                          const SizedBox(width: 12),
                          Text(
                            _testResult == 'success'
                                ? 'Connection successful!'
                                : 'Connection failed',
                            style: TextStyle(
                              color: _testResult == 'success'
                                  ? Colors.green
                                  : Colors.red,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Quick Connect
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.flash_on, size: 20),
                      const SizedBox(width: 8),
                      const Text(
                        'Quick Connect',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      _buildQuickConnectChip('localhost', 'http://127.0.0.1:8000'),
                      _buildQuickConnectChip('Local', 'http://192.168.1.100:8000'),
                      _buildQuickConnectChip('VPS', 'https://bbooster.example.com'),
                    ],
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // About
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.info_outline, size: 20),
                      const SizedBox(width: 8),
                      const Text(
                        'About',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 16),
                  _buildInfoRow('App Name', 'BBooster'),
                  _buildInfoRow('Version', '0.1.0'),
                  _buildInfoRow('Build', '1'),
                  const Divider(height: 24),
                  Text(
                    'BBooster Mobile App\n'
                    'Observation & E-STOP control only.\n'
                    'API keys and account settings are managed on PC.',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey.shade500,
                      height: 1.5,
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),

          // Security Notice
          Card(
            color: Colors.blue.shade900.withOpacity(0.3),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Row(
                children: [
                  Icon(Icons.security, color: Colors.blue.shade300),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Security',
                          style: TextStyle(
                            fontWeight: FontWeight.bold,
                            color: Colors.blue.shade200,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'This app does not store API keys. Only server URL is saved locally.',
                          style: TextStyle(
                            fontSize: 12,
                            color: Colors.blue.shade300,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildQuickConnectChip(String label, String url) {
    return ActionChip(
      label: Text(label),
      avatar: const Icon(Icons.link, size: 16),
      onPressed: () {
        _urlController.text = url;
      },
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: TextStyle(color: Colors.grey.shade500)),
          Text(value, style: const TextStyle(fontWeight: FontWeight.w500)),
        ],
      ),
    );
  }
}
