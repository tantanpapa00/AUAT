/// Timeline event model for order/trade history
class TimelineEvent {
  final String symbol;
  final String exchange;
  final String side;
  final double qty;
  final String status;
  final String? orderId;
  final DateTime? timestamp;

  TimelineEvent({
    required this.symbol,
    required this.exchange,
    required this.side,
    required this.qty,
    required this.status,
    this.orderId,
    this.timestamp,
  });

  factory TimelineEvent.fromJson(Map<String, dynamic> json) {
    return TimelineEvent(
      symbol: json['symbol'] ?? '--',
      exchange: json['exchange'] ?? '--',
      side: json['side'] ?? '--',
      qty: (json['qty'] ?? 0).toDouble(),
      status: json['last_order_status'] ?? json['status'] ?? '--',
      orderId: json['order_id'],
      timestamp: json['last_order_at'] != null
          ? DateTime.tryParse(json['last_order_at'])
          : null,
    );
  }

  bool get isBuy => side.toLowerCase() == 'buy';
  bool get isFilled => status.toLowerCase() == 'filled';
  bool get isFailed => status.toLowerCase() == 'failed';
}
