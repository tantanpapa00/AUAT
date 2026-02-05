import 'package:flutter/foundation.dart';

/// App-wide state management
class AppState extends ChangeNotifier {
  // Server connection status
  bool _isConnected = false;
  bool get isConnected => _isConnected;

  // E-STOP status
  bool _estopActive = false;
  bool get estopActive => _estopActive;

  // Server URL (configurable)
  String _serverUrl = 'http://192.168.1.100:8000';
  String get serverUrl => _serverUrl;

  // Last update timestamp
  DateTime? _lastUpdate;
  DateTime? get lastUpdate => _lastUpdate;

  // Recent events (for dashboard)
  List<Map<String, dynamic>> _recentEvents = [];
  List<Map<String, dynamic>> get recentEvents => _recentEvents;

  // Timeline events (full list)
  List<Map<String, dynamic>> _timelineEvents = [];
  List<Map<String, dynamic>> get timelineEvents => _timelineEvents;

  // Connector status
  List<Map<String, dynamic>> _connectors = [];
  List<Map<String, dynamic>> get connectors => _connectors;

  // Status summary
  Map<String, dynamic>? _statusSummary;
  Map<String, dynamic>? get statusSummary => _statusSummary;

  // Error state
  String? _errorMessage;
  String? get errorMessage => _errorMessage;

  // Loading states
  bool _isLoadingTimeline = false;
  bool get isLoadingTimeline => _isLoadingTimeline;

  void setServerUrl(String url) {
    _serverUrl = url;
    notifyListeners();
  }

  void updateConnectionStatus(bool connected) {
    _isConnected = connected;
    _lastUpdate = DateTime.now();
    notifyListeners();
  }

  void updateEstopStatus(bool active) {
    _estopActive = active;
    notifyListeners();
  }

  void updateRecentEvents(List<Map<String, dynamic>> events) {
    _recentEvents = events;
    _lastUpdate = DateTime.now();
    notifyListeners();
  }

  void updateTimelineEvents(List<Map<String, dynamic>> events) {
    _timelineEvents = events;
    _lastUpdate = DateTime.now();
    notifyListeners();
  }

  void updateConnectors(List<Map<String, dynamic>> connectors) {
    _connectors = connectors;
    notifyListeners();
  }

  void updateStatusSummary(Map<String, dynamic> summary) {
    _statusSummary = summary;
    _lastUpdate = DateTime.now();
    notifyListeners();
  }

  void setLoadingTimeline(bool loading) {
    _isLoadingTimeline = loading;
    notifyListeners();
  }

  void setError(String? message) {
    _errorMessage = message;
    notifyListeners();
  }

  void clearError() {
    _errorMessage = null;
    notifyListeners();
  }

  // Computed properties
  int get connectedCount => _connectors.where((c) => c['connected'] == true).length;
  int get totalConnectors => _connectors.length;

  int get filledCount => _timelineEvents.where((e) =>
    (e['last_order_status'] ?? e['status'] ?? '').toString().toLowerCase() == 'filled'
  ).length;

  int get failedCount => _timelineEvents.where((e) =>
    (e['last_order_status'] ?? e['status'] ?? '').toString().toLowerCase() == 'failed'
  ).length;
}
