import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/app_state.dart';
import '../services/api_service.dart';

class TimelineScreen extends StatefulWidget {
  const TimelineScreen({super.key});

  @override
  State<TimelineScreen> createState() => _TimelineScreenState();
}

class _TimelineScreenState extends State<TimelineScreen> {
  String _filterStatus = 'all';
  String _filterExchange = 'all';

  @override
  void initState() {
    super.initState();
    _loadTimeline();
  }

  Future<void> _loadTimeline() async {
    final appState = context.read<AppState>();
    final apiService = context.read<ApiService>();
    apiService.setBaseUrl(appState.serverUrl);

    appState.setLoadingTimeline(true);

    try {
      final events = await apiService.getTimeline(limit: 100);
      appState.updateTimelineEvents(events);
    } catch (e) {
      // Silent fail - will show empty list
    }

    appState.setLoadingTimeline(false);
  }

  List<Map<String, dynamic>> _getFilteredEvents(List<Map<String, dynamic>> events) {
    return events.where((e) {
      final status = (e['last_order_status'] ?? e['status'] ?? '').toString().toLowerCase();
      final exchange = (e['exchange'] ?? '').toString().toLowerCase();

      if (_filterStatus != 'all' && status != _filterStatus) {
        return false;
      }
      if (_filterExchange != 'all' && exchange != _filterExchange) {
        return false;
      }
      return true;
    }).toList();
  }

  Set<String> _getUniqueExchanges(List<Map<String, dynamic>> events) {
    return events
        .map((e) => (e['exchange'] ?? '').toString())
        .where((e) => e.isNotEmpty)
        .toSet();
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<AppState>(
      builder: (context, appState, child) {
        final filteredEvents = _getFilteredEvents(appState.timelineEvents);
        final exchanges = _getUniqueExchanges(appState.timelineEvents);

        return Column(
          children: [
            // Filter bar
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              decoration: BoxDecoration(
                color: Theme.of(context).cardColor,
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withOpacity(0.1),
                    blurRadius: 4,
                    offset: const Offset(0, 2),
                  ),
                ],
              ),
              child: Row(
                children: [
                  // Status filter
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      value: _filterStatus,
                      decoration: const InputDecoration(
                        labelText: 'Status',
                        contentPadding: EdgeInsets.symmetric(horizontal: 12),
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                      items: const [
                        DropdownMenuItem(value: 'all', child: Text('All')),
                        DropdownMenuItem(value: 'filled', child: Text('Filled')),
                        DropdownMenuItem(value: 'sent', child: Text('Sent')),
                        DropdownMenuItem(value: 'failed', child: Text('Failed')),
                      ],
                      onChanged: (value) {
                        setState(() => _filterStatus = value ?? 'all');
                      },
                    ),
                  ),
                  const SizedBox(width: 12),
                  // Exchange filter
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      value: _filterExchange,
                      decoration: const InputDecoration(
                        labelText: 'Exchange',
                        contentPadding: EdgeInsets.symmetric(horizontal: 12),
                        border: OutlineInputBorder(),
                        isDense: true,
                      ),
                      items: [
                        const DropdownMenuItem(value: 'all', child: Text('All')),
                        ...exchanges.map((e) => DropdownMenuItem(
                          value: e.toLowerCase(),
                          child: Text(e.toUpperCase()),
                        )),
                      ],
                      onChanged: (value) {
                        setState(() => _filterExchange = value ?? 'all');
                      },
                    ),
                  ),
                ],
              ),
            ),

            // Stats row
            Container(
              padding: const EdgeInsets.all(12),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _buildStatChip('Total', filteredEvents.length, Colors.blue),
                  _buildStatChip('Filled', appState.filledCount, Colors.green),
                  _buildStatChip('Failed', appState.failedCount, Colors.red),
                ],
              ),
            ),

            // Timeline list
            Expanded(
              child: appState.isLoadingTimeline
                  ? const Center(child: CircularProgressIndicator())
                  : filteredEvents.isEmpty
                      ? Center(
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.history, size: 64, color: Colors.grey.shade400),
                              const SizedBox(height: 16),
                              Text(
                                'No events found',
                                style: TextStyle(color: Colors.grey.shade600),
                              ),
                            ],
                          ),
                        )
                      : RefreshIndicator(
                          onRefresh: _loadTimeline,
                          child: ListView.builder(
                            padding: const EdgeInsets.all(16),
                            itemCount: filteredEvents.length,
                            itemBuilder: (context, index) {
                              return _buildTimelineItem(filteredEvents[index]);
                            },
                          ),
                        ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildStatChip(String label, int count, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            count.toString(),
            style: TextStyle(
              fontWeight: FontWeight.bold,
              fontSize: 16,
              color: color,
            ),
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTimelineItem(Map<String, dynamic> event) {
    final symbol = event['symbol'] ?? '--';
    final exchange = event['exchange'] ?? '--';
    final side = event['side'] ?? '--';
    final qty = event['qty']?.toString() ?? '--';
    final status = event['last_order_status'] ?? event['status'] ?? '--';
    final orderAt = event['last_order_at'];
    final orderId = event['order_id'] ?? '--';

    final statusColor = _getStatusColor(status);
    final sideColor = side.toString().toLowerCase() == 'buy' ? Colors.green : Colors.red;

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Header row
            Row(
              children: [
                // Side indicator
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: sideColor.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    side.toUpperCase(),
                    style: TextStyle(
                      color: sideColor,
                      fontWeight: FontWeight.bold,
                      fontSize: 12,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                // Symbol
                Expanded(
                  child: Text(
                    symbol,
                    style: const TextStyle(
                      fontWeight: FontWeight.bold,
                      fontSize: 16,
                    ),
                  ),
                ),
                // Status badge
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: statusColor.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    status.toUpperCase(),
                    style: TextStyle(
                      color: statusColor,
                      fontWeight: FontWeight.w600,
                      fontSize: 11,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            // Details row
            Row(
              children: [
                _buildDetailItem(Icons.business, exchange.toUpperCase()),
                const SizedBox(width: 16),
                _buildDetailItem(Icons.numbers, 'Qty: $qty'),
              ],
            ),
            const SizedBox(height: 8),
            // Footer row
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  'ID: ${orderId.toString().length > 12 ? '${orderId.toString().substring(0, 12)}...' : orderId}',
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.grey.shade500,
                    fontFamily: 'monospace',
                  ),
                ),
                Text(
                  _formatDateTime(orderAt),
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.grey.shade600,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDetailItem(IconData icon, String text) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: Colors.grey.shade600),
        const SizedBox(width: 4),
        Text(
          text,
          style: TextStyle(
            fontSize: 13,
            color: Colors.grey.shade700,
          ),
        ),
      ],
    );
  }

  Color _getStatusColor(String status) {
    switch (status.toLowerCase()) {
      case 'filled':
        return Colors.green;
      case 'sent':
      case 'pending':
        return Colors.orange;
      case 'failed':
      case 'error':
        return Colors.red;
      case 'partial':
        return Colors.purple;
      default:
        return Colors.grey;
    }
  }

  String _formatDateTime(String? isoString) {
    if (isoString == null) return '--';
    try {
      final dt = DateTime.parse(isoString);
      final now = DateTime.now();
      final isToday = dt.year == now.year && dt.month == now.month && dt.day == now.day;

      if (isToday) {
        return '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}:${dt.second.toString().padLeft(2, '0')}';
      }
      return '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (e) {
      return '--';
    }
  }
}
