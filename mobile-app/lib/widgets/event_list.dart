import 'package:flutter/material.dart';

class EventList extends StatelessWidget {
  final List<Map<String, dynamic>> events;

  const EventList({super.key, required this.events});

  @override
  Widget build(BuildContext context) {
    if (events.isEmpty) {
      return const Padding(
        padding: EdgeInsets.all(16),
        child: Center(
          child: Text(
            'No recent events',
            style: TextStyle(color: Colors.grey),
          ),
        ),
      );
    }

    return Column(
      children: events.take(5).map((event) => _buildEventItem(event)).toList(),
    );
  }

  Widget _buildEventItem(Map<String, dynamic> event) {
    final symbol = event['symbol'] ?? '--';
    final status = event['last_order_status'] ?? '--';
    final orderAt = event['last_order_at'];

    final statusColor = _getStatusColor(status);

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: statusColor,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  symbol,
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                ),
                Text(
                  status.toUpperCase(),
                  style: TextStyle(
                    fontSize: 12,
                    color: statusColor,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
          Text(
            _formatDateTime(orderAt),
            style: TextStyle(
              fontSize: 12,
              color: Colors.grey.shade600,
              fontFamily: 'monospace',
            ),
          ),
        ],
      ),
    );
  }

  Color _getStatusColor(String status) {
    switch (status.toLowerCase()) {
      case 'filled':
        return Colors.green;
      case 'sent':
        return Colors.orange;
      case 'failed':
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
      final isToday = dt.year == now.year &&
          dt.month == now.month &&
          dt.day == now.day;

      if (isToday) {
        return '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
      }
      return '${dt.month}/${dt.day} ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
    } catch (e) {
      return '--';
    }
  }
}
