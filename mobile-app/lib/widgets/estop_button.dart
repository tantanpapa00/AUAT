import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../providers/app_state.dart';
import '../services/api_service.dart';

class EstopButton extends StatefulWidget {
  const EstopButton({super.key});

  @override
  State<EstopButton> createState() => _EstopButtonState();
}

class _EstopButtonState extends State<EstopButton>
    with SingleTickerProviderStateMixin {
  bool _isLoading = false;
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);
    _pulseAnimation = Tween<double>(begin: 1.0, end: 1.1).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  Future<void> _activateEstop() async {
    final appState = context.read<AppState>();
    final apiService = context.read<ApiService>();

    if (!appState.isConnected) {
      _showSnackBar('Server not connected', Colors.red);
      return;
    }

    // Show reason input dialog
    final reason = await showDialog<String>(
      context: context,
      builder: (context) => _EstopReasonDialog(),
    );

    if (reason == null) return;

    setState(() => _isLoading = true);
    HapticFeedback.heavyImpact();

    try {
      await apiService.setEstop(true, reason: reason);
      appState.updateEstopStatus(true);
      appState.setEstopReason(reason);
      _showSnackBar('E-STOP ACTIVATED', Colors.red);
    } catch (e) {
      _showSnackBar('Failed: $e', Colors.red);
    }

    setState(() => _isLoading = false);
  }

  Future<void> _deactivateEstop() async {
    final appState = context.read<AppState>();
    final apiService = context.read<ApiService>();

    if (!appState.isConnected) {
      _showSnackBar('Server not connected', Colors.red);
      return;
    }

    // Confirm deactivation
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF252525),
        title: Row(
          children: [
            Icon(Icons.warning_amber, color: Colors.orange.shade400),
            const SizedBox(width: 12),
            const Text('Confirm E-STOP OFF'),
          ],
        ),
        content: const Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Are you sure you want to deactivate E-STOP?',
              style: TextStyle(fontWeight: FontWeight.w500),
            ),
            SizedBox(height: 12),
            Text(
              '• Trading will resume immediately\n'
              '• New orders will be allowed\n'
              '• All connectors will be active',
              style: TextStyle(fontSize: 13, color: Colors.grey),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () {
              HapticFeedback.mediumImpact();
              Navigator.pop(context, true);
            },
            style: FilledButton.styleFrom(backgroundColor: Colors.green),
            child: const Text('Resume Trading'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    setState(() => _isLoading = true);

    try {
      await apiService.setEstop(false);
      appState.updateEstopStatus(false);
      appState.setEstopReason(null);
      _showSnackBar('E-STOP deactivated - Trading resumed', Colors.green);
    } catch (e) {
      _showSnackBar('Failed: $e', Colors.red);
    }

    setState(() => _isLoading = false);
  }

  void _showSnackBar(String message, Color color) {
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: color,
          behavior: SnackBarBehavior.floating,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(
      builder: (context, appState, child) {
        final isActive = appState.estopActive;

        if (isActive) {
          return _buildActiveEstopCard(appState);
        } else {
          return _buildInactiveEstopCard(appState);
        }
      },
    );
  }

  Widget _buildActiveEstopCard(AppState appState) {
    return Card(
      color: Colors.red.shade900.withOpacity(0.4),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Colors.red.shade700, width: 2),
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          children: [
            // Pulsing icon
            AnimatedBuilder(
              animation: _pulseAnimation,
              builder: (context, child) {
                return Transform.scale(
                  scale: _pulseAnimation.value,
                  child: Container(
                    width: 64,
                    height: 64,
                    decoration: BoxDecoration(
                      color: Colors.red,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: Colors.red.withOpacity(0.5),
                          blurRadius: 20,
                          spreadRadius: 5,
                        ),
                      ],
                    ),
                    child: const Icon(
                      Icons.pan_tool,
                      color: Colors.white,
                      size: 32,
                    ),
                  ),
                );
              },
            ),
            const SizedBox(height: 16),
            const Text(
              'E-STOP ACTIVE',
              style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.bold,
                color: Colors.red,
                letterSpacing: 2,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              'All trading is blocked',
              style: TextStyle(
                color: Colors.red.shade200,
                fontSize: 14,
              ),
            ),
            if (appState.estopReason != null &&
                appState.estopReason!.isNotEmpty) ...[
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.black26,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  children: [
                    Icon(Icons.notes, size: 16, color: Colors.red.shade300),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        appState.estopReason!,
                        style: TextStyle(
                          fontSize: 13,
                          color: Colors.red.shade200,
                          fontStyle: FontStyle.italic,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 20),
            SizedBox(
              width: double.infinity,
              height: 48,
              child: _isLoading
                  ? const Center(child: CircularProgressIndicator())
                  : ElevatedButton.icon(
                      onPressed:
                          appState.isConnected ? _deactivateEstop : null,
                      icon: const Icon(Icons.play_arrow),
                      label: const Text('RESUME TRADING'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.green,
                        foregroundColor: Colors.white,
                        textStyle: const TextStyle(
                          fontWeight: FontWeight.bold,
                          letterSpacing: 1,
                        ),
                      ),
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInactiveEstopCard(AppState appState) {
    return Card(
      color: Colors.green.shade900.withOpacity(0.2),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: Colors.green.shade700, width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          children: [
            Container(
              width: 48,
              height: 48,
              decoration: BoxDecoration(
                color: Colors.green.withOpacity(0.2),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(
                Icons.play_circle,
                color: Colors.green,
                size: 28,
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Trading Active',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.bold,
                      color: Colors.green,
                    ),
                  ),
                  Text(
                    'E-STOP is OFF',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.green.shade300,
                    ),
                  ),
                ],
              ),
            ),
            _isLoading
                ? const SizedBox(
                    width: 24,
                    height: 24,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : FilledButton(
                    onPressed: appState.isConnected ? _activateEstop : null,
                    style: FilledButton.styleFrom(
                      backgroundColor: Colors.red,
                      foregroundColor: Colors.white,
                    ),
                    child: const Text('E-STOP'),
                  ),
          ],
        ),
      ),
    );
  }
}

class _EstopReasonDialog extends StatefulWidget {
  @override
  State<_EstopReasonDialog> createState() => _EstopReasonDialogState();
}

class _EstopReasonDialogState extends State<_EstopReasonDialog> {
  final _controller = TextEditingController();
  String? _selectedReason;

  final _quickReasons = [
    'Market volatility',
    'Technical issue',
    'Manual intervention',
    'Risk management',
  ];

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: const Color(0xFF252525),
      title: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: Colors.red.withOpacity(0.2),
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Icon(Icons.pan_tool, color: Colors.red),
          ),
          const SizedBox(width: 12),
          const Text('Activate E-STOP'),
        ],
      ),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'This will immediately block all trading.',
              style: TextStyle(color: Colors.grey.shade400),
            ),
            const SizedBox(height: 16),
            const Text(
              'Reason (optional):',
              style: TextStyle(fontWeight: FontWeight.w500),
            ),
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: _quickReasons.map((reason) {
                final isSelected = _selectedReason == reason;
                return ChoiceChip(
                  label: Text(reason),
                  selected: isSelected,
                  onSelected: (selected) {
                    setState(() {
                      _selectedReason = selected ? reason : null;
                      if (selected) {
                        _controller.text = reason;
                      }
                    });
                  },
                  selectedColor: Colors.red.shade700,
                );
              }).toList(),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _controller,
              decoration: const InputDecoration(
                hintText: 'Or enter custom reason...',
                border: OutlineInputBorder(),
                isDense: true,
              ),
              maxLines: 2,
              onChanged: (value) {
                setState(() => _selectedReason = null);
              },
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: () {
            HapticFeedback.heavyImpact();
            Navigator.pop(context, _controller.text);
          },
          style: FilledButton.styleFrom(backgroundColor: Colors.red),
          child: const Text('ACTIVATE E-STOP'),
        ),
      ],
    );
  }
}
