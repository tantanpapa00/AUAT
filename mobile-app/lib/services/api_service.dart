import 'dart:convert';
import 'package:http/http.dart' as http;

/// API service for communicating with BBooster server
class ApiService {
  String baseUrl = 'http://192.168.1.100:8000';
  final Duration timeout = const Duration(seconds: 10);

  void setBaseUrl(String url) {
    baseUrl = url;
  }

  /// Get home/dashboard data
  Future<Map<String, dynamic>> getHome() async {
    final response = await http
        .get(Uri.parse('$baseUrl/api/diag/home'))
        .timeout(timeout);

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('Failed to load home data: ${response.statusCode}');
    }
  }

  /// Get E-STOP status
  Future<Map<String, dynamic>> getEstopStatus() async {
    final response = await http
        .get(Uri.parse('$baseUrl/api/system/estop'))
        .timeout(timeout);

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('Failed to get E-STOP status: ${response.statusCode}');
    }
  }

  /// Set E-STOP
  Future<Map<String, dynamic>> setEstop(bool enabled) async {
    final response = await http
        .post(
          Uri.parse('$baseUrl/api/system/estop'),
          headers: {'Content-Type': 'application/json'},
          body: json.encode({'estop': enabled}),
        )
        .timeout(timeout);

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('Failed to set E-STOP: ${response.statusCode}');
    }
  }

  /// Get timeline events
  Future<Map<String, dynamic>> getTimeline({int limit = 20}) async {
    final response = await http
        .get(Uri.parse('$baseUrl/api/timeline?limit=$limit'))
        .timeout(timeout);

    if (response.statusCode == 200) {
      return json.decode(response.body);
    } else {
      throw Exception('Failed to load timeline: ${response.statusCode}');
    }
  }

  /// Health check
  Future<bool> healthCheck() async {
    try {
      final response = await http
          .get(Uri.parse('$baseUrl/health'))
          .timeout(const Duration(seconds: 5));
      return response.statusCode == 200;
    } catch (e) {
      return false;
    }
  }
}
