/// Connector status model for exchange connections
class ConnectorStatus {
  final String exchange;
  final String account;
  final bool isConnected;
  final String? error;
  final DateTime? lastCheck;

  ConnectorStatus({
    required this.exchange,
    required this.account,
    required this.isConnected,
    this.error,
    this.lastCheck,
  });

  factory ConnectorStatus.fromJson(Map<String, dynamic> json) {
    return ConnectorStatus(
      exchange: json['exchange'] ?? '--',
      account: json['account'] ?? '--',
      isConnected: json['connected'] == true,
      error: json['error'],
      lastCheck: json['last_check'] != null
          ? DateTime.tryParse(json['last_check'])
          : null,
    );
  }
}
