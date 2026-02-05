import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

class ChartScreen extends StatefulWidget {
  const ChartScreen({super.key});

  @override
  State<ChartScreen> createState() => _ChartScreenState();
}

class _ChartScreenState extends State<ChartScreen> {
  late WebViewController _controller;
  bool _isLoading = true;
  String _currentSymbol = 'BINANCE:BTCUSDT';

  final List<Map<String, String>> _symbols = [
    {'label': 'BTC/USDT', 'symbol': 'BINANCE:BTCUSDT'},
    {'label': 'ETH/USDT', 'symbol': 'BINANCE:ETHUSDT'},
    {'label': 'SOL/USDT', 'symbol': 'BINANCE:SOLUSDT'},
    {'label': 'XRP/USDT', 'symbol': 'BINANCE:XRPUSDT'},
    {'label': 'BNB/USDT', 'symbol': 'BINANCE:BNBUSDT'},
  ];

  @override
  void initState() {
    super.initState();
    _initWebView();
  }

  void _initWebView() {
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFF1A1A1A))
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageStarted: (String url) {
            setState(() => _isLoading = true);
          },
          onPageFinished: (String url) {
            setState(() => _isLoading = false);
          },
          onWebResourceError: (WebResourceError error) {
            setState(() => _isLoading = false);
          },
        ),
      )
      ..loadHtmlString(_buildChartHtml(_currentSymbol));
  }

  String _buildChartHtml(String symbol) {
    return '''
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    html, body {
      width: 100%;
      height: 100%;
      background: #1A1A1A;
      overflow: hidden;
    }
    .tradingview-widget-container {
      width: 100%;
      height: 100%;
    }
  </style>
</head>
<body>
  <div class="tradingview-widget-container">
    <div id="tradingview_chart" style="width: 100%; height: 100%;"></div>
  </div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
    new TradingView.widget({
      "autosize": true,
      "symbol": "$symbol",
      "interval": "15",
      "timezone": "Asia/Seoul",
      "theme": "dark",
      "style": "1",
      "locale": "kr",
      "toolbar_bg": "#1A1A1A",
      "enable_publishing": false,
      "hide_top_toolbar": false,
      "hide_legend": false,
      "save_image": false,
      "container_id": "tradingview_chart",
      "studies": [
        "RSI@tv-basicstudies",
        "MASimple@tv-basicstudies"
      ]
    });
  </script>
</body>
</html>
''';
  }

  void _changeSymbol(String symbol) {
    setState(() {
      _currentSymbol = symbol;
      _isLoading = true;
    });
    _controller.loadHtmlString(_buildChartHtml(symbol));
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Symbol selector
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: const Color(0xFF252525),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.2),
                blurRadius: 4,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: _symbols.map((s) {
                final isSelected = _currentSymbol == s['symbol'];
                return Padding(
                  padding: const EdgeInsets.only(right: 8),
                  child: ChoiceChip(
                    label: Text(s['label']!),
                    selected: isSelected,
                    onSelected: (_) => _changeSymbol(s['symbol']!),
                    selectedColor: const Color(0xFFE53935),
                    labelStyle: TextStyle(
                      color: isSelected ? Colors.white : Colors.grey,
                      fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                    ),
                  ),
                );
              }).toList(),
            ),
          ),
        ),

        // Chart
        Expanded(
          child: Stack(
            children: [
              WebViewWidget(controller: _controller),
              if (_isLoading)
                Container(
                  color: const Color(0xFF1A1A1A),
                  child: const Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        CircularProgressIndicator(color: Color(0xFFE53935)),
                        SizedBox(height: 16),
                        Text(
                          'Loading chart...',
                          style: TextStyle(color: Colors.grey),
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ),

        // Quick actions bar
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: const Color(0xFF252525),
            border: Border(
              top: BorderSide(color: Colors.grey.shade800),
            ),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              _buildTimeframeButton('1m'),
              _buildTimeframeButton('5m'),
              _buildTimeframeButton('15m'),
              _buildTimeframeButton('1h'),
              _buildTimeframeButton('4h'),
              _buildTimeframeButton('1D'),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildTimeframeButton(String tf) {
    return TextButton(
      onPressed: () {
        // Note: TradingView widget doesn't support dynamic interval change
        // This would require reloading the chart with new interval
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Timeframe: $tf (reload to change)'),
            duration: const Duration(seconds: 1),
          ),
        );
      },
      style: TextButton.styleFrom(
        foregroundColor: Colors.grey.shade400,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      ),
      child: Text(tf),
    );
  }
}
