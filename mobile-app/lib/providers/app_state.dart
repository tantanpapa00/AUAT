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

  // Recent events
  List<Map<String, dynamic>> _recentEvents = [];
  List<Map<String, dynamic>> get recentEvents => _recentEvents;

  // Status summary
  Map<String, dynamic>? _statusSummary;
  Map<String, dynamic>? get statusSummary => _statusSummary;

  // Error state
  String? _errorMessage;
  String? get errorMessage => _errorMessage;

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

  void updateStatusSummary(Map<String, dynamic> summary) {
    _statusSummary = summary;
    _lastUpdate = DateTime.now();
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
}
