import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_state.dart';
import '../services/api_service.dart';
import '../widgets/status_card.dart';
import '../widgets/estop_button.dart';
import '../widgets/event_list.dart';
import 'settings_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() => _isLoading = true);

    final appState = context.read<AppState>();
    final apiService = context.read<ApiService>();
    apiService.setBaseUrl(appState.serverUrl);

    try {
      // Check connection
      final connected = await apiService.healthCheck();
      appState.updateConnectionStatus(connected);

      if (connected) {
        // Get E-STOP status
        final estopData = await apiService.getEstopStatus();
        appState.updateEstopStatus(estopData['estop'] == true);

        // Get home data
        final homeData = await apiService.getHome();
        if (homeData['items'] != null) {
          appState.updateRecentEvents(
            List<Map<String, dynamic>>.from(homeData['items']),
          );
        }
        appState.updateStatusSummary(homeData);
        appState.clearError();
      } else {
        appState.setError('Cannot connect to server');
      }
    } catch (e) {
      appState.setError(e.toString());
      appState.updateConnectionStatus(false);
    }

    setState(() => _isLoading = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('BBooster'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadData,
          ),
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const SettingsScreen()),
              ).then((_) => _loadData());
            },
          ),
        ],
      ),
      body: Consumer<AppState>(
        builder: (context, appState, child) {
          if (_isLoading) {
            return const Center(child: CircularProgressIndicator());
          }

          return RefreshIndicator(
            onRefresh: _loadData,
            child: SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Connection status
                  StatusCard(
                    title: 'Server Status',
                    status: appState.isConnected ? 'Connected' : 'Disconnected',
                    isOk: appState.isConnected,
                    icon: appState.isConnected
                        ? Icons.cloud_done
                        : Icons.cloud_off,
                  ),
                  const SizedBox(height: 12),

                  // E-STOP control
                  const EstopButton(),
                  const SizedBox(height: 12),

                  // Error message
                  if (appState.errorMessage != null)
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.red.shade50,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.red.shade200),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.error_outline, color: Colors.red.shade700),
                          const SizedBox(width: 12),
                          Expanded(
                            child: Text(
                              appState.errorMessage!,
                              style: TextStyle(color: Colors.red.shade700),
                            ),
                          ),
                        ],
                      ),
                    ),
                  if (appState.errorMessage != null) const SizedBox(height: 12),

                  // Recent events
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(16),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text(
                                'Recent Orders',
                                style: TextStyle(
                                  fontSize: 16,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                              if (appState.lastUpdate != null)
                                Text(
                                  'Updated: ${_formatTime(appState.lastUpdate!)}',
                                  style: TextStyle(
                                    fontSize: 12,
                                    color: Colors.grey.shade600,
                                  ),
                                ),
                            ],
                          ),
                          const Divider(),
                          EventList(events: appState.recentEvents),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  String _formatTime(DateTime dt) {
    return '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }
}
