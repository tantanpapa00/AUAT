import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_state.dart';
import '../services/api_service.dart';

class EstopButton extends StatefulWidget {
  const EstopButton({super.key});

  @override
  State<EstopButton> createState() => _EstopButtonState();
}

class _EstopButtonState extends State<EstopButton> {
  bool _isLoading = false;

  Future<void> _toggleEstop() async {
    final appState = context.read<AppState>();
    final apiService = context.read<ApiService>();

    if (!appState.isConnected) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Server not connected')),
      );
      return;
    }

    final newState = !appState.estopActive;

    // Confirm E-STOP OFF action
    if (!newState) {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Confirm E-STOP OFF'),
          content: const Text(
            'Are you sure you want to deactivate E-STOP?\n\n'
            'Trading will resume and new orders will be allowed.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Confirm'),
            ),
          ],
        ),
      );

      if (confirmed != true) return;
    }

    setState(() => _isLoading = true);

    try {
      await apiService.setEstop(newState);
      appState.updateEstopStatus(newState);

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(newState ? 'E-STOP activated' : 'E-STOP deactivated'),
            backgroundColor: newState ? Colors.red : Colors.green,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed: $e')),
        );
      }
    }

    setState(() => _isLoading = false);
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(
      builder: (context, appState, child) {
        final isActive = appState.estopActive;
        final color = isActive ? Colors.red : Colors.green;

        return Card(
          color: color.withOpacity(0.1),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Row(
                  children: [
                    Icon(
                      isActive ? Icons.pan_tool : Icons.play_circle,
                      color: color,
                      size: 32,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          const Text(
                            'E-STOP',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                          Text(
                            isActive ? 'ACTIVE - Trading Blocked' : 'OFF - Trading Active',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                              color: color,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                SizedBox(
                  width: double.infinity,
                  child: _isLoading
                      ? const Center(child: CircularProgressIndicator())
                      : ElevatedButton.icon(
                          onPressed: appState.isConnected ? _toggleEstop : null,
                          icon: Icon(isActive ? Icons.play_arrow : Icons.stop),
                          label: Text(isActive ? 'Deactivate E-STOP' : 'Activate E-STOP'),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: isActive ? Colors.green : Colors.red,
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(vertical: 12),
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
}
