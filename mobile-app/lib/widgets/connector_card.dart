import 'package:flutter/material.dart';

class ConnectorCard extends StatelessWidget {
  final List<Map<String, dynamic>> connectors;

  const ConnectorCard({super.key, required this.connectors});

  @override
  Widget build(BuildContext context) {
    final connectedCount = connectors.where((c) => c['connected'] == true).length;
    final totalCount = connectors.length;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  'Connectors',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: connectedCount == totalCount
                        ? Colors.green.withOpacity(0.1)
                        : Colors.orange.withOpacity(0.1),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    '$connectedCount/$totalCount',
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: connectedCount == totalCount
                          ? Colors.green
                          : Colors.orange,
                    ),
                  ),
                ),
              ],
            ),
            if (connectors.isEmpty)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 16),
                child: Center(
                  child: Text(
                    'No connectors configured',
                    style: TextStyle(color: Colors.grey.shade500),
                  ),
                ),
              )
            else ...[
              const Divider(),
              ...connectors.map((c) => _buildConnectorItem(c)),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildConnectorItem(Map<String, dynamic> connector) {
    final exchange = connector['exchange'] ?? '--';
    final account = connector['account'] ?? '--';
    final connected = connector['connected'] == true;
    final error = connector['error'];

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Container(
            width: 10,
            height: 10,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: connected ? Colors.green : Colors.red,
              boxShadow: [
                BoxShadow(
                  color: (connected ? Colors.green : Colors.red).withOpacity(0.4),
                  blurRadius: 4,
                  spreadRadius: 1,
                ),
              ],
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '${exchange.toUpperCase()} - $account',
                  style: const TextStyle(
                    fontWeight: FontWeight.w500,
                    fontSize: 14,
                  ),
                ),
                if (error != null && error.toString().isNotEmpty)
                  Text(
                    error.toString(),
                    style: TextStyle(
                      fontSize: 11,
                      color: Colors.red.shade400,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
              ],
            ),
          ),
          Icon(
            connected ? Icons.check_circle : Icons.error,
            color: connected ? Colors.green : Colors.red,
            size: 20,
          ),
        ],
      ),
    );
  }
}
