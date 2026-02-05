import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_state.dart';
import '../services/api_service.dart';
import '../widgets/status_card.dart';
import '../widgets/estop_button.dart';
import '../widgets/event_list.dart';
import '../widgets/connector_card.dart';

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
        try {
          final estopData = await apiService.getEstopStatus();
          appState.updateEstopStatus(estopData['estop'] == true);
        } catch (_) {}

        // Get home data
        try {
          final homeData = await apiService.getHome();
          if (homeData['items'] != null) {
            appState.updateRecentEvents(
              List<Map<String, dynamic>>.from(homeData['items']),
            );
          }
          appState.updateStatusSummary(homeData);
        } catch (_) {}

        // Get connector status
        try {
          final connectors = await apiService.getConnectorStatus();
          appState.updateConnectors(connectors);
        } catch (_) {}

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
    return Consumer<AppState>(
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
                // Server Status Card
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
                if (appState.errorMessage != null) ...[
                  _buildErrorBanner(appState.errorMessage!),
                  const SizedBox(height: 12),
                ],

                // Connector Status
                if (appState.connectors.isNotEmpty) ...[
                  ConnectorCard(connectors: appState.connectors),
                  const SizedBox(height: 12),
                ],

                // Summary Stats
                if (appState.isConnected) ...[
                  _buildSummaryRow(appState),
                  const SizedBox(height: 12),
                ],

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
    );
  }

  Widget _buildErrorBanner(String message) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.red.shade900.withOpacity(0.3),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.red.shade700),
      ),
      child: Row(
        children: [
          Icon(Icons.error_outline, color: Colors.red.shade300),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              message,
              style: TextStyle(color: Colors.red.shade200),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSummaryRow(AppState appState) {
    return Row(
      children: [
        Expanded(
          child: _buildSummaryCard(
            'Connectors',
            '${appState.connectedCount}/${appState.totalConnectors}',
            Icons.cable,
            appState.connectedCount == appState.totalConnectors
                ? Colors.green
                : Colors.orange,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: _buildSummaryCard(
            'Orders Today',
            appState.recentEvents.length.toString(),
            Icons.receipt_long,
            Colors.blue,
          ),
        ),
      ],
    );
  }

  Widget _buildSummaryCard(String title, String value, IconData icon, Color color) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            Icon(icon, color: color, size: 28),
            const SizedBox(height: 8),
            Text(
              value,
              style: TextStyle(
                fontSize: 24,
                fontWeight: FontWeight.bold,
                color: color,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              title,
              style: TextStyle(
                fontSize: 12,
                color: Colors.grey.shade500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  String _formatTime(DateTime dt) {
    return '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
  }
}
