# MOBILE_APP_SPEC.md (SSOT)
- Last updated: 2026-02-04 KST
- Owner: 기훈(작가님)
- Status: Week 18 Day 1 (TF 권장 고지 추가)

> NOTE: 이 파일은 모바일 앱 스펙의 '진실(SSOT)'입니다.
> PC 앱 스펙은 docs/PC_APP_SPEC.md 참조.

---

# 1) 기술 선정

## 1-1) 프레임워크 비교

| 항목 | Flutter | React Native |
|------|---------|--------------|
| 언어 | Dart | JavaScript/TypeScript |
| 성능 | 네이티브 수준 (Skia 렌더링) | JS Bridge 오버헤드 |
| UI 일관성 | 플랫폼 무관 동일 UI | 플랫폼별 네이티브 컴포넌트 |
| 개발 속도 | Hot Reload 우수 | Hot Reload 우수 |
| 에코시스템 | Google 지원, 성장 중 | Facebook, 성숙함 |
| 웹뷰 지원 | webview_flutter | react-native-webview |
| 보안 저장소 | flutter_secure_storage | react-native-keychain |

## 1-2) 선정: Flutter (Dart)

**선정 이유**:
1. **UI 일관성**: iOS/Android 동일한 디자인 보장 (TradingView embed 포함)
2. **성능**: Skia 기반 렌더링으로 복잡한 타임라인/차트 뷰에 적합
3. **보안**: flutter_secure_storage로 안전한 토큰 저장
4. **PC 앱 연계**: Tauri(PC)와 별개지만 API 연동 패턴 통일 가능
5. **WebView**: webview_flutter로 TradingView 차트 embed 용이

---

# 2) 앱 역할 (SSOT: PRODUCT_SPEC.md 1-8)

## 2-1) 허용 기능 (읽기 중심)

| 기능 | 설명 |
|------|------|
| 대시보드 조회 | 계좌 요약, 자산 현황, 최근 주문 |
| 타임라인 조회 | 이벤트 목록, 근거 확인 (reason_code, snapshot_id) |
| TradingView 차트 | WebView로 차트 표시 (embed 방식) |
| E-STOP 제어 | 긴급 정지 ON/OFF |
| Premium 이벤트 조회 | signal_events 목록, 스냅샷 확인 |

## 2-2) 금지 기능 (보안)

| 금지 | 이유 |
|------|------|
| API 키 등록/수정 | PC에서만 허용 (보안) |
| 계좌 추가/삭제 | PC에서만 허용 |
| 전략 설정 변경 | PC에서만 허용 |
| 수동 주문 | Hub 원칙 위반 방지 |

---

# 3) 인증/토큰 저장 정책

## 3-1) 인증 흐름

```
1. 로그인 (서버 → 토큰 발급)
   POST /api/auth/login
   Request: { email, password }
   Response: { access_token, refresh_token, expires_at }

2. 토큰 저장 (로컬 보안 저장소)
   flutter_secure_storage 사용
   - iOS: Keychain
   - Android: EncryptedSharedPreferences (API 23+) / Keystore

3. API 요청 (토큰 헤더)
   Authorization: Bearer {access_token}

4. 토큰 갱신 (자동)
   POST /api/auth/refresh
   Request: { refresh_token }
   Response: { access_token, expires_at }

5. 로그아웃 (토큰 삭제)
   로컬 저장소에서 토큰 제거
   서버에 로그아웃 알림 (선택)
```

## 3-2) 토큰 저장 규칙

| 항목 | 값 |
|------|-----|
| 저장 위치 | flutter_secure_storage |
| 키 이름 | `auth_access_token`, `auth_refresh_token` |
| 암호화 | OS 레벨 (Keychain/Keystore) |
| 만료 처리 | access_token 만료 시 refresh_token으로 갱신 |
| 오프라인 | 로컬 토큰으로 제한된 조회 허용 (최대 24시간) |

## 3-3) 보안 체크리스트

- [ ] 토큰은 메모리에 오래 보관하지 않음
- [ ] 로그에 토큰 출력 금지
- [ ] HTTPS 필수 (HTTP 차단)
- [ ] Certificate Pinning 적용 (선택, 고급)
- [ ] 루팅/탈옥 기기 경고 (선택)

---

# 4) 디렉토리 구조 (Flutter)

```
autobot_app/
├── android/                 # Android 네이티브
├── ios/                     # iOS 네이티브
├── lib/
│   ├── main.dart           # 앱 진입점
│   ├── app.dart            # MaterialApp 설정
│   ├── config/
│   │   ├── api_config.dart # API 베이스 URL
│   │   └── constants.dart  # 상수 정의
│   ├── models/
│   │   ├── account.dart    # 계좌 모델
│   │   ├── asset.dart      # 자산 모델
│   │   ├── timeline_event.dart
│   │   └── signal_event.dart
│   ├── services/
│   │   ├── api_service.dart      # HTTP 클라이언트
│   │   ├── auth_service.dart     # 인증 관리
│   │   └── storage_service.dart  # 보안 저장소
│   ├── providers/
│   │   ├── auth_provider.dart
│   │   ├── dashboard_provider.dart
│   │   └── timeline_provider.dart
│   ├── screens/
│   │   ├── login_screen.dart
│   │   ├── dashboard_screen.dart
│   │   ├── timeline_screen.dart
│   │   ├── chart_screen.dart     # TradingView WebView
│   │   └── settings_screen.dart  # E-STOP 포함
│   └── widgets/
│       ├── timeline_item.dart
│       ├── signal_card.dart
│       └── estop_button.dart
├── test/                    # 테스트
├── pubspec.yaml            # 의존성
└── README.md
```

---

# 5) 의존성 (pubspec.yaml)

```yaml
dependencies:
  flutter:
    sdk: flutter

  # 상태 관리
  provider: ^6.0.0

  # HTTP
  dio: ^5.0.0

  # 보안 저장소
  flutter_secure_storage: ^9.0.0

  # WebView (TradingView 차트)
  webview_flutter: ^4.0.0

  # 유틸리티
  intl: ^0.18.0           # 날짜/시간 포맷
  json_annotation: ^4.8.0  # JSON 직렬화

dev_dependencies:
  flutter_test:
    sdk: flutter
  build_runner: ^2.4.0
  json_serializable: ^6.7.0
```

---

# 6) API 연동

## 6-1) 베이스 URL

```dart
// lib/config/api_config.dart
class ApiConfig {
  static const String baseUrl = 'http://127.0.0.1:8000';  // 개발
  // static const String baseUrl = 'https://api.autobot.com';  // 운영

  static const Duration timeout = Duration(seconds: 15);
}
```

## 6-2) 주요 엔드포인트

| 화면 | Method | Endpoint | 설명 |
|------|--------|----------|------|
| 대시보드 | GET | /api/home | 전광판 요약 |
| 타임라인 | GET | /api/timeline | 이벤트 목록 |
| E-STOP 조회 | GET | /api/system/estop | 현재 상태 |
| E-STOP 설정 | POST | /api/system/estop | ON/OFF 토글 |
| Premium 상태 | GET | /api/premium/status | Premium 활성화 여부 |
| Premium 신호 | GET | /api/premium/signals | 신호 목록 |
| Premium 스냅샷 | GET | /api/premium/snapshots/{id} | 스냅샷 상세 |
| 구독 정보 | GET | /api/subscription/me | Plan/Entitlement |

## 6-3) 에러 처리

```dart
// 공통 응답 형식
{
  "ok": true/false,
  "code": "error_code",    // ok=false 시
  "detail": "상세 메시지"   // ok=false 시
}

// 에러 코드별 처리
switch (response['code']) {
  case 'unauthorized':
    // 로그인 화면으로 이동
    break;
  case 'premium_disabled':
    // Premium 비활성화 안내
    break;
  case 'estop_on':
    // E-STOP 활성화 안내
    break;
  default:
    // 일반 에러 표시
}
```

---

# 7) 화면 설계

## 7-1) 로그인 화면

```
┌─────────────────────────┐
│      AutoBot Login      │
├─────────────────────────┤
│  ┌───────────────────┐  │
│  │ Email             │  │
│  └───────────────────┘  │
│  ┌───────────────────┐  │
│  │ Password          │  │
│  └───────────────────┘  │
│                         │
│  ┌───────────────────┐  │
│  │      로그인       │  │
│  └───────────────────┘  │
│                         │
│  PC에서 계정 등록 필요   │
└─────────────────────────┘
```

## 7-2) 대시보드 화면

```
┌─────────────────────────┐
│ 대시보드        [E-STOP]│
├─────────────────────────┤
│ 계좌 요약               │
│ ┌─────────────────────┐ │
│ │ OKX: 197.72 USDT    │ │
│ │ KIS: 10,000,000 KRW │ │
│ └─────────────────────┘ │
├─────────────────────────┤
│ 자산 현황 (3개)         │
│ ┌─────────────────────┐ │
│ │ ETH-USDT [활성]     │ │
│ │ BTC-USDT [대기]     │ │
│ │ ...                 │ │
│ └─────────────────────┘ │
├─────────────────────────┤
│ 최근 이벤트             │
│ ┌─────────────────────┐ │
│ │ [MR] entry: BTC     │ │
│ │ [TREND] exit: ETH   │ │
│ └─────────────────────┘ │
└─────────────────────────┘
[대시보드] [타임라인] [차트] [설정]
```

## 7-3) 타임라인 화면

```
┌─────────────────────────┐
│ 타임라인         [필터] │
├─────────────────────────┤
│ 2026-02-04 15:30        │
│ ┌─────────────────────┐ │
│ │ [MR] entry          │ │
│ │ BTC-USDT @ OKX      │ │
│ │ reason: MR_ENTRY_OSC│ │
│ │ TF: 1h              │ │
│ │ [스냅샷 보기]       │ │
│ └─────────────────────┘ │
│                         │
│ 2026-02-04 14:00        │
│ ┌─────────────────────┐ │
│ │ [ORDER] filled      │ │
│ │ ETH-USDT @ OKX      │ │
│ │ qty: 0.01 @ 2500.0  │ │
│ └─────────────────────┘ │
│         ...             │
└─────────────────────────┘
[대시보드] [타임라인] [차트] [설정]
```

## 7-4) 차트 화면 (TradingView WebView)

```
┌─────────────────────────┐
│ 차트    [심볼▼] [TF▼]  │
├─────────────────────────┤
│                         │
│   ┌─────────────────┐   │
│   │                 │   │
│   │   TradingView   │   │
│   │     WebView     │   │
│   │                 │   │
│   │                 │   │
│   └─────────────────┘   │
│                         │
└─────────────────────────┘
[대시보드] [타임라인] [차트] [설정]
```

## 7-5) 설정 화면

```
┌─────────────────────────┐
│ 설정                    │
├─────────────────────────┤
│ 긴급 정지 (E-STOP)      │
│ ┌─────────────────────┐ │
│ │ [    OFF    ]       │ │  ← 토글 스위치
│ │ 활성화 시 모든 주문  │ │
│ │ 전송이 차단됩니다    │ │
│ └─────────────────────┘ │
├─────────────────────────┤
│ 구독 정보               │
│ ┌─────────────────────┐ │
│ │ Plan: Hub           │ │
│ │ 만료: 2026-03-03    │ │
│ │ Premium: 비활성     │ │
│ └─────────────────────┘ │
├─────────────────────────┤
│ 계정                    │
│ ┌─────────────────────┐ │
│ │ user@example.com    │ │
│ │ [로그아웃]          │ │
│ └─────────────────────┘ │
└─────────────────────────┘
[대시보드] [타임라인] [차트] [설정]
```

---

# 8) E-STOP 구현

## 8-1) UI 요구사항

- 대시보드 헤더에 E-STOP 버튼 (항상 표시)
- 설정 화면에 E-STOP 토글 스위치
- E-STOP ON 시 빨간색 강조
- E-STOP OFF 시 초록색/회색

## 8-2) API 연동

```dart
// E-STOP 조회
Future<bool> getEstopStatus() async {
  final response = await dio.get('/api/system/estop');
  return response.data['estop'] == true;
}

// E-STOP 설정
Future<bool> setEstop(bool value, String reason) async {
  final response = await dio.post('/api/system/estop', data: {
    'estop': value ? '1' : '0',
    'reason': reason,
  });
  return response.data['ok'] == true;
}
```

## 8-3) 확인 다이얼로그

```
E-STOP ON 시:
┌─────────────────────────┐
│   긴급 정지 활성화?     │
├─────────────────────────┤
│ 모든 주문 전송이        │
│ 즉시 차단됩니다.        │
│                         │
│ 사유 입력:              │
│ ┌───────────────────┐   │
│ │ 시장 급변동 대응   │   │
│ └───────────────────┘   │
│                         │
│ [취소]        [확인]    │
└─────────────────────────┘
```

---

# 9) TradingView 차트 Embed

## 9-1) WebView 구현

```dart
// lib/screens/chart_screen.dart
import 'package:webview_flutter/webview_flutter.dart';

class ChartScreen extends StatefulWidget {
  final String symbol;  // e.g., "BINANCE:BTCUSDT"
  final String interval; // e.g., "60" (1시간)

  @override
  _ChartScreenState createState() => _ChartScreenState();
}

class _ChartScreenState extends State<ChartScreen> {
  late WebViewController _controller;

  String get _chartUrl {
    // TradingView 위젯 URL
    return 'https://s.tradingview.com/widgetembed/?'
        'symbol=${widget.symbol}&'
        'interval=${widget.interval}&'
        'theme=dark&'
        'style=1&'
        'locale=ko_KR';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.symbol),
        actions: [
          // 심볼/TF 선택 버튼
        ],
      ),
      body: WebViewWidget(controller: _controller),
    );
  }
}
```

## 9-2) 심볼 변환

```dart
// 내부 심볼 → TradingView 심볼
String toTradingViewSymbol(String symbol, String exchange) {
  // BTC-USDT @ OKX → OKX:BTCUSDT
  final base = symbol.split('-')[0];
  final quote = symbol.split('-')[1];
  return '$exchange:$base$quote';
}
```

---

# 10) 오프라인 모드

## 10-1) 정책

| 상황 | 동작 |
|------|------|
| 토큰 유효 + 오프라인 | 캐시된 데이터 표시 (최대 24시간) |
| 토큰 만료 + 오프라인 | 로그인 필요 안내 |
| E-STOP 변경 | 온라인 필수 (오프라인 불가) |

## 10-2) 캐시 전략

```dart
// 캐시 키
const cacheKeys = {
  'dashboard': 'cache_dashboard',
  'timeline': 'cache_timeline',
  'subscription': 'cache_subscription',
};

// 캐시 만료 시간
const cacheTTL = Duration(hours: 24);
```

---

# 11) Day 2: 대시보드/타임라인 상세 스펙

## 11-1) 대시보드 데이터 구조

```dart
// lib/models/dashboard_data.dart
class DashboardData {
  final List<AccountSummary> accounts;
  final List<AssetSummary> assets;
  final List<TimelineEvent> recentEvents;
  final SystemStatus systemStatus;

  DashboardData({
    required this.accounts,
    required this.assets,
    required this.recentEvents,
    required this.systemStatus,
  });
}

class AccountSummary {
  final int id;
  final String name;
  final String exchange;  // OKX, KIS, BINANCE, BYBIT, UPBIT
  final bool isActive;
  final double? tradingBalance;
  final String currency;  // USDT, KRW

  String get displayBalance {
    if (tradingBalance == null) return '---';
    if (currency == 'KRW') {
      return '${NumberFormat('#,###').format(tradingBalance)} $currency';
    }
    return '${tradingBalance?.toStringAsFixed(2)} $currency';
  }
}

class AssetSummary {
  final int id;
  final String symbol;
  final String market;
  final String exchange;
  final bool isActive;
  final String? lastSignalAt;
  final String? lastOrderStatus;
}

class SystemStatus {
  final bool estopOn;
  final bool premiumEnabled;
  final List<String> premiumModes;  // ['trend', 'mr']
}
```

## 11-2) 대시보드 API 연동

```dart
// lib/services/dashboard_service.dart
class DashboardService {
  final Dio dio;

  Future<DashboardData> fetchDashboard() async {
    // 1. /api/home 호출
    final homeResponse = await dio.get('/api/home');

    // 2. /api/system/estop 호출
    final estopResponse = await dio.get('/api/system/estop');

    // 3. /api/premium/status 호출
    final premiumResponse = await dio.get('/api/premium/status');

    // 4. /api/timeline?limit=5 호출
    final timelineResponse = await dio.get('/api/timeline?limit=5');

    return DashboardData(
      accounts: _parseAccounts(homeResponse.data),
      assets: _parseAssets(homeResponse.data),
      recentEvents: _parseEvents(timelineResponse.data),
      systemStatus: SystemStatus(
        estopOn: estopResponse.data['estop'] == true,
        premiumEnabled: premiumResponse.data['premium_enabled'] == true,
        premiumModes: List<String>.from(premiumResponse.data['available_modes'] ?? []),
      ),
    );
  }
}
```

## 11-3) 대시보드 UI 위젯

```dart
// lib/screens/dashboard_screen.dart
class DashboardScreen extends StatefulWidget {
  @override
  _DashboardScreenState createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  @override
  Widget build(BuildContext context) {
    return Consumer<DashboardProvider>(
      builder: (context, provider, _) {
        if (provider.isLoading) {
          return Center(child: CircularProgressIndicator());
        }

        return RefreshIndicator(
          onRefresh: provider.refresh,
          child: ListView(
            children: [
              // E-STOP 배너 (활성화 시)
              if (provider.data?.systemStatus.estopOn == true)
                _EstopBanner(),

              // 계좌 요약 카드
              _AccountsCard(accounts: provider.data?.accounts ?? []),

              // 자산 현황 카드
              _AssetsCard(assets: provider.data?.assets ?? []),

              // 최근 이벤트 카드
              _RecentEventsCard(events: provider.data?.recentEvents ?? []),

              // Premium 상태 카드
              if (provider.data?.systemStatus.premiumEnabled == true)
                _PremiumStatusCard(modes: provider.data?.systemStatus.premiumModes ?? []),
            ],
          ),
        );
      },
    );
  }
}
```

## 11-4) 타임라인 데이터 구조

```dart
// lib/models/timeline_event.dart
class TimelineEvent {
  final int id;
  final String eventType;  // signal, order_sent, order_filled, ...
  final int? assetId;
  final int? orderId;
  final int? accountId;
  final String? exchange;
  final String summary;
  final Map<String, dynamic>? detail;
  final String? reasonCode;
  final String? reasonText;
  final String? snapshotId;
  final DateTime createdAt;

  // Premium 신호인지 확인
  bool get isPremiumSignal => eventType == 'signal_created';

  // 아이콘 결정
  IconData get icon {
    switch (eventType) {
      case 'signal':
      case 'signal_created':
        return Icons.lightbulb;
      case 'order_sent':
        return Icons.send;
      case 'order_filled':
        return Icons.check_circle;
      case 'order_failed':
        return Icons.error;
      case 'estop_on':
        return Icons.stop_circle;
      case 'estop_off':
        return Icons.play_circle;
      default:
        return Icons.info;
    }
  }

  // 색상 결정
  Color get color {
    switch (eventType) {
      case 'order_filled':
        return Colors.green;
      case 'order_failed':
        return Colors.red;
      case 'estop_on':
        return Colors.red;
      default:
        return Colors.blue;
    }
  }
}
```

## 11-5) 타임라인 API 연동

```dart
// lib/services/timeline_service.dart
class TimelineService {
  final Dio dio;

  Future<TimelineResponse> fetchTimeline({
    int? assetId,
    int limit = 20,
    int offset = 0,
  }) async {
    final params = <String, dynamic>{
      'limit': limit,
      'offset': offset,
    };
    if (assetId != null) {
      params['asset_id'] = assetId;
    }

    final response = await dio.get('/api/timeline', queryParameters: params);

    return TimelineResponse(
      items: (response.data['items'] as List)
          .map((e) => TimelineEvent.fromJson(e))
          .toList(),
      total: response.data['total'],
      hasMore: offset + limit < response.data['total'],
    );
  }

  // Premium 스냅샷 조회
  Future<SignalSnapshot?> fetchSnapshot(String snapshotId) async {
    try {
      final response = await dio.get('/api/premium/snapshots/$snapshotId');
      if (response.data['ok'] == true) {
        return SignalSnapshot.fromJson(response.data['snapshot']);
      }
    } catch (e) {
      // 스냅샷 없음 또는 Premium 비활성화
    }
    return null;
  }
}
```

## 11-6) 타임라인 UI 위젯

```dart
// lib/screens/timeline_screen.dart
class TimelineScreen extends StatefulWidget {
  @override
  _TimelineScreenState createState() => _TimelineScreenState();
}

class _TimelineScreenState extends State<TimelineScreen> {
  final ScrollController _scrollController = ScrollController();

  @override
  void initState() {
    super.initState();
    // 무한 스크롤
    _scrollController.addListener(() {
      if (_scrollController.position.pixels >=
          _scrollController.position.maxScrollExtent - 200) {
        context.read<TimelineProvider>().loadMore();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<TimelineProvider>(
      builder: (context, provider, _) {
        return Scaffold(
          appBar: AppBar(
            title: Text('타임라인'),
            actions: [
              // 필터 버튼
              IconButton(
                icon: Icon(Icons.filter_list),
                onPressed: () => _showFilterDialog(context),
              ),
            ],
          ),
          body: RefreshIndicator(
            onRefresh: provider.refresh,
            child: ListView.builder(
              controller: _scrollController,
              itemCount: provider.events.length + (provider.hasMore ? 1 : 0),
              itemBuilder: (context, index) {
                if (index >= provider.events.length) {
                  return Center(child: CircularProgressIndicator());
                }
                return _TimelineEventCard(
                  event: provider.events[index],
                  onSnapshotTap: (snapshotId) => _showSnapshotDialog(snapshotId),
                );
              },
            ),
          ),
        );
      },
    );
  }
}

// lib/widgets/timeline_event_card.dart
class _TimelineEventCard extends StatelessWidget {
  final TimelineEvent event;
  final Function(String)? onSnapshotTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      child: ListTile(
        leading: CircleAvatar(
          backgroundColor: event.color.withOpacity(0.2),
          child: Icon(event.icon, color: event.color),
        ),
        title: Text(event.summary),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (event.exchange != null)
              Text('${event.exchange}', style: TextStyle(fontSize: 12)),
            if (event.reasonCode != null)
              Text('reason: ${event.reasonCode}', style: TextStyle(fontSize: 12)),
            Text(
              _formatDateTime(event.createdAt),
              style: TextStyle(fontSize: 11, color: Colors.grey),
            ),
          ],
        ),
        trailing: event.snapshotId != null
            ? IconButton(
                icon: Icon(Icons.camera_alt),
                onPressed: () => onSnapshotTap?.call(event.snapshotId!),
                tooltip: '스냅샷 보기',
              )
            : null,
        isThreeLine: true,
      ),
    );
  }
}
```

## 11-7) 스냅샷 상세 다이얼로그

```dart
// lib/widgets/snapshot_dialog.dart
class SnapshotDialog extends StatelessWidget {
  final SignalSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('신호 근거 스냅샷'),
      content: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            _InfoRow('심볼', snapshot.symbol),
            _InfoRow('거래소', snapshot.exchange),
            _InfoRow('TF', snapshot.tf),
            _InfoRow('모드', snapshot.premiumMode),
            Divider(),
            Text('OHLCV', style: TextStyle(fontWeight: FontWeight.bold)),
            _InfoRow('Open', snapshot.ohlcv['o']?.toString() ?? '-'),
            _InfoRow('High', snapshot.ohlcv['h']?.toString() ?? '-'),
            _InfoRow('Low', snapshot.ohlcv['l']?.toString() ?? '-'),
            _InfoRow('Close', snapshot.ohlcv['c']?.toString() ?? '-'),
            _InfoRow('Volume', snapshot.ohlcv['v']?.toString() ?? '-'),
            Divider(),
            Text('지표', style: TextStyle(fontWeight: FontWeight.bold)),
            ...snapshot.indicators.entries.map(
              (e) => _InfoRow(e.key, e.value?.toString() ?? '-'),
            ),
            Divider(),
            _InfoRow('reason_code', snapshot.reasonCode),
            if (snapshot.reasonText != null)
              _InfoRow('reason_text', snapshot.reasonText!),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: Text('닫기'),
        ),
      ],
    );
  }
}
```

---

# 12) Day 4: TradingView 차트 Embed 상세

## 12-1) WebView 설정

```dart
// lib/screens/chart_screen.dart
import 'package:webview_flutter/webview_flutter.dart';

class ChartScreen extends StatefulWidget {
  final String symbol;    // 내부 심볼: BTC-USDT
  final String exchange;  // OKX, BINANCE, BYBIT, UPBIT
  final String interval;  // 1, 5, 15, 60, 240, D, W

  const ChartScreen({
    Key? key,
    required this.symbol,
    required this.exchange,
    this.interval = '60',  // 기본 1시간
  }) : super(key: key);

  @override
  State<ChartScreen> createState() => _ChartScreenState();
}

class _ChartScreenState extends State<ChartScreen> {
  late final WebViewController _controller;

  @override
  void initState() {
    super.initState();
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFF131722))
      ..loadRequest(Uri.parse(_buildChartUrl()));
  }

  String _buildChartUrl() {
    final tvSymbol = _toTradingViewSymbol(widget.symbol, widget.exchange);
    return 'https://s.tradingview.com/widgetembed/?'
        'symbol=$tvSymbol&'
        'interval=${widget.interval}&'
        'theme=dark&'
        'style=1&'              // 캔들스틱
        'locale=ko_KR&'
        'toolbar_bg=%23131722&'
        'enable_publishing=false&'
        'hide_top_toolbar=false&'
        'hide_legend=false&'
        'save_image=false&'
        'container_id=tradingview_chart';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.symbol),
        actions: [
          // 심볼 선택
          PopupMenuButton<String>(
            icon: const Icon(Icons.currency_exchange),
            onSelected: (symbol) => _changeSymbol(symbol),
            itemBuilder: (context) => _buildSymbolMenu(),
          ),
          // TF 선택
          PopupMenuButton<String>(
            icon: const Icon(Icons.access_time),
            onSelected: (tf) => _changeInterval(tf),
            itemBuilder: (context) => _buildIntervalMenu(),
          ),
        ],
      ),
      body: WebViewWidget(controller: _controller),
    );
  }
}
```

## 12-2) 심볼 변환 테이블

| 내부 심볼 | 거래소 | TradingView 심볼 |
|----------|--------|------------------|
| BTC-USDT | OKX | OKX:BTCUSDT |
| BTC-USDT | BINANCE | BINANCE:BTCUSDT |
| BTC-USDT | BYBIT | BYBIT:BTCUSDT |
| BTC-KRW | UPBIT | UPBIT:BTCKRW |
| ETH-USDT | OKX | OKX:ETHUSDT |

```dart
// lib/utils/symbol_converter.dart
String _toTradingViewSymbol(String symbol, String exchange) {
  // BTC-USDT → BTCUSDT
  final normalized = symbol.replaceAll('-', '');

  // 거래소별 매핑
  switch (exchange.toUpperCase()) {
    case 'OKX':
      return 'OKX:$normalized';
    case 'BINANCE':
      return 'BINANCE:$normalized';
    case 'BYBIT':
      return 'BYBIT:$normalized';
    case 'UPBIT':
      return 'UPBIT:$normalized';
    case 'KIS':
      // KIS는 한국 주식 (다른 형식)
      return 'KRX:${symbol.split("-")[0]}';
    default:
      return 'BINANCE:$normalized';  // 기본값
  }
}
```

## 12-3) 타임프레임 변환

| UI 표시 | TradingView interval |
|--------|---------------------|
| 1분 | 1 |
| 5분 | 5 |
| 15분 | 15 |
| 1시간 | 60 |
| 4시간 | 240 |
| 1일 | D |
| 1주 | W |

```dart
final List<Map<String, String>> intervals = [
  {'label': '1분', 'value': '1'},
  {'label': '5분', 'value': '5'},
  {'label': '15분', 'value': '15'},
  {'label': '1시간', 'value': '60'},
  {'label': '4시간', 'value': '240'},
  {'label': '1일', 'value': 'D'},
  {'label': '1주', 'value': 'W'},
];
```

## 12-4) 타임라인에서 차트로 이동

```dart
// 타임라인 이벤트에서 차트 화면으로 이동
void _navigateToChart(TimelineEvent event) {
  if (event.exchange == null) return;

  // 심볼 추출 (detail에서 또는 summary에서)
  final symbol = event.detail?['symbol'] ??
                 _extractSymbolFromSummary(event.summary);

  if (symbol == null) return;

  Navigator.push(
    context,
    MaterialPageRoute(
      builder: (context) => ChartScreen(
        symbol: symbol,
        exchange: event.exchange!,
        interval: _tfToInterval(event.detail?['tf'] ?? '1h'),
      ),
    ),
  );
}

String _tfToInterval(String tf) {
  switch (tf.toLowerCase()) {
    case '1m': return '1';
    case '5m': return '5';
    case '15m': return '15';
    case '1h': return '60';
    case '4h': return '240';
    case '1d': return 'D';
    case '1w': return 'W';
    default: return '60';
  }
}
```

## 12-5) 차트 화면 네비게이션 플로우

```
[대시보드]
    │
    └─→ [자산 탭] → 자산 선택 → [차트 화면]
    │
    └─→ [최근 이벤트] → 이벤트 탭 → [차트 화면]

[타임라인]
    │
    └─→ [이벤트 카드] → 차트 아이콘 탭 → [차트 화면]
    │
    └─→ [스냅샷 다이얼로그] → "차트에서 보기" 버튼 → [차트 화면]

[차트 화면]
    │
    ├─→ [심볼 메뉴] → 다른 심볼 선택 → 차트 새로고침
    │
    └─→ [TF 메뉴] → 다른 TF 선택 → 차트 새로고침
```

---

# 13) Entitlement 연동 (Week 17)

## 13-1) 실행 시 구독 동기화

> 앱은 서버 연결 필수 (오프라인 모드 미지원)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 앱 실행                                                   │
│    ↓                                                        │
│ 2. flutter_secure_storage에서 access_token 확인             │
│    ├─ 없음 → 로그인 화면 표시                                │
│    └─ 있음 → 3단계로                                        │
│    ↓                                                        │
│ 3. GET /api/subscription/me 호출                            │
│    ↓                                                        │
│ 4. 응답 처리                                                 │
│    ├─ ok=true → entitlements 저장 → 메인 화면               │
│    ├─ code=unauthorized → 토큰 삭제 → 로그인 화면            │
│    ├─ code=expired → 기능 잠금 → 갱신 안내                  │
│    └─ 네트워크 오류 → 재시도 화면 표시                       │
└─────────────────────────────────────────────────────────────┘
```

## 13-2) Dart 모델

```dart
// lib/models/entitlements.dart
import 'package:json_annotation/json_annotation.dart';

part 'entitlements.g.dart';

@JsonSerializable()
class PremiumEntitlements {
  final bool premiumTrend;
  final bool premiumMr;
  final bool premiumCustom;
  final bool customAdvanced;

  PremiumEntitlements({
    required this.premiumTrend,
    required this.premiumMr,
    required this.premiumCustom,
    required this.customAdvanced,
  });

  factory PremiumEntitlements.fromJson(Map<String, dynamic> json) =>
      _$PremiumEntitlementsFromJson(json);
}

@JsonSerializable()
class EntitlementsV2 {
  final bool hubEnabled;
  final bool premiumEnabled;
  final int maxSymbols;
  final int logRetentionDays;
  final bool batchTemplate;
  final bool exportCsv;
  final PremiumEntitlements? premium;
  final int maxRules;
  final double customComplexityMultiplier;

  EntitlementsV2({
    required this.hubEnabled,
    required this.premiumEnabled,
    required this.maxSymbols,
    required this.logRetentionDays,
    required this.batchTemplate,
    required this.exportCsv,
    this.premium,
    required this.maxRules,
    required this.customComplexityMultiplier,
  });

  factory EntitlementsV2.fromJson(Map<String, dynamic> json) =>
      _$EntitlementsV2FromJson(json);

  // 권한 체크 헬퍼
  bool get canUseHub => hubEnabled;
  bool get canUsePremium => premiumEnabled;
  bool get canUseCustomRules => premium?.premiumCustom ?? false;
  bool get canUseAdvancedCustom => premium?.customAdvanced ?? false;
}

@JsonSerializable()
class SubscriptionResponse {
  final bool ok;
  final String? userId;
  final String? plan;
  final String? expiresAt;
  final EntitlementsV2? entitlements;
  final String? offlineCacheValidUntil;
  final String? code;
  final String? detail;

  SubscriptionResponse({
    required this.ok,
    this.userId,
    this.plan,
    this.expiresAt,
    this.entitlements,
    this.offlineCacheValidUntil,
    this.code,
    this.detail,
  });

  factory SubscriptionResponse.fromJson(Map<String, dynamic> json) =>
      _$SubscriptionResponseFromJson(json);
}
```

## 13-3) Entitlement Provider

```dart
// lib/providers/entitlement_provider.dart
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../services/api_service.dart';
import '../models/entitlements.dart';

final entitlementProvider = StateNotifierProvider<EntitlementNotifier, EntitlementState>((ref) {
  return EntitlementNotifier(ref.read(apiServiceProvider));
});

class EntitlementState {
  final EntitlementsV2? entitlements;
  final bool isLoading;
  final String? errorCode;

  EntitlementState({
    this.entitlements,
    this.isLoading = false,
    this.errorCode,
  });

  EntitlementState copyWith({
    EntitlementsV2? entitlements,
    bool? isLoading,
    String? errorCode,
  }) {
    return EntitlementState(
      entitlements: entitlements ?? this.entitlements,
      isLoading: isLoading ?? this.isLoading,
      errorCode: errorCode,
    );
  }
}

class EntitlementNotifier extends StateNotifier<EntitlementState> {
  final ApiService _api;
  Timer? _syncTimer;

  EntitlementNotifier(this._api) : super(EntitlementState());

  Future<void> fetchEntitlements() async {
    state = state.copyWith(isLoading: true, errorCode: null);

    try {
      final resp = await _api.getSubscription();

      if (resp.ok && resp.entitlements != null) {
        state = state.copyWith(
          entitlements: resp.entitlements,
          isLoading: false,
        );
      } else {
        state = state.copyWith(
          isLoading: false,
          errorCode: resp.code ?? 'unknown_error',
        );
      }
    } catch (e) {
      state = state.copyWith(
        isLoading: false,
        errorCode: 'network_error',
      );
    }
  }

  void startPeriodicSync() {
    // 즉시 1회 실행
    fetchEntitlements();

    // 15분마다 동기화 (앱은 PC보다 짧은 주기)
    _syncTimer = Timer.periodic(
      const Duration(minutes: 15),
      (_) => fetchEntitlements(),
    );
  }

  void stopPeriodicSync() {
    _syncTimer?.cancel();
    _syncTimer = null;
  }

  @override
  void dispose() {
    stopPeriodicSync();
    super.dispose();
  }
}
```

## 13-4) 기능 잠금/해제 매핑

| entitlement | 잠금 시 동작 |
|-------------|--------------|
| hub_enabled=false | 대시보드만 표시, 상세 기능 숨김 |
| premium_enabled=false | 프리미엄 탭 숨김 |
| premium.premium_custom=false | 커스텀 규칙 목록 숨김 |

> 앱은 읽기 중심이므로 PC보다 잠금 기능이 적음

## 13-5) UI 가드 위젯

```dart
// lib/widgets/entitlement_guard.dart
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../providers/entitlement_provider.dart';

class EntitlementGuard extends ConsumerWidget {
  final Widget child;
  final bool Function(EntitlementsV2?) check;
  final Widget? fallback;

  const EntitlementGuard({
    Key? key,
    required this.child,
    required this.check,
    this.fallback,
  }) : super(key: key);

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(entitlementProvider);
    final hasPermission = check(state.entitlements);

    if (hasPermission) {
      return child;
    }

    return fallback ?? const SizedBox.shrink();
  }
}

// 사용 예시
EntitlementGuard(
  check: (e) => e?.canUsePremium ?? false,
  fallback: UpgradePrompt(),
  child: PremiumDashboard(),
)
```

---

# 14) 15분봉 권장 고지 (TF Policy)

## 14-1) 고지 원칙

> ⚠️ **필수 고지**: 모든 Premium 전략(추세/역추세/커스텀)은 **15분봉(15m) 이상** 사용을 권장합니다.

### 표시 위치

| 위치 | 표시 방식 |
|------|----------|
| 타임라인 이벤트 | tf_warning=true 시 경고 아이콘 |
| 스냅샷 상세 | TF 경고 배너 |
| 대시보드 | 단기봉 사용 중 경고 표시 |

## 14-2) 경고 문구 (고정)

### 타임라인 이벤트 경고

```dart
class TfWarningBadge extends StatelessWidget {
  final String tf;

  const TfWarningBadge({required this.tf});

  @override
  Widget build(BuildContext context) {
    final level = _getWarningLevel(tf);

    if (level == TfWarningLevel.none) {
      return const SizedBox.shrink();
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: level == TfWarningLevel.red
            ? Colors.red.shade100
            : Colors.amber.shade100,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(
          color: level == TfWarningLevel.red
              ? Colors.red
              : Colors.amber,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            level == TfWarningLevel.red
                ? Icons.warning_rounded
                : Icons.warning_amber_rounded,
            size: 14,
            color: level == TfWarningLevel.red
                ? Colors.red.shade700
                : Colors.amber.shade700,
          ),
          const SizedBox(width: 4),
          Text(
            '단기봉',
            style: TextStyle(
              fontSize: 11,
              color: level == TfWarningLevel.red
                  ? Colors.red.shade700
                  : Colors.amber.shade700,
            ),
          ),
        ],
      ),
    );
  }

  TfWarningLevel _getWarningLevel(String tf) {
    final minutes = _parseTfMinutes(tf);
    if (minutes < 5) return TfWarningLevel.red;
    if (minutes < 15) return TfWarningLevel.amber;
    return TfWarningLevel.none;
  }

  int _parseTfMinutes(String tf) {
    final match = RegExp(r'^(\d+)(m|h|d)$').firstMatch(tf);
    if (match == null) return 0;
    final value = int.parse(match.group(1)!);
    final unit = match.group(2)!;
    if (unit == 'h') return value * 60;
    if (unit == 'd') return value * 1440;
    return value;
  }
}

enum TfWarningLevel { none, amber, red }
```

### 스냅샷 상세 경고 배너

```dart
class TfWarningBanner extends StatelessWidget {
  final String tf;

  const TfWarningBanner({required this.tf});

  @override
  Widget build(BuildContext context) {
    final level = _getWarningLevel(tf);

    if (level == TfWarningLevel.none) {
      return const SizedBox.shrink();
    }

    final isRed = level == TfWarningLevel.red;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        color: isRed ? Colors.red.shade50 : Colors.amber.shade50,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: isRed ? Colors.red.shade300 : Colors.amber.shade300,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                isRed ? Icons.warning_rounded : Icons.warning_amber_rounded,
                color: isRed ? Colors.red.shade700 : Colors.amber.shade700,
                size: 20,
              ),
              const SizedBox(width: 8),
              Text(
                isRed ? '1분봉 강한 경고' : '5분봉 경고',
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: isRed ? Colors.red.shade700 : Colors.amber.shade700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            isRed
                ? '1분봉은 체결 품질이 크게 저하될 수 있습니다. '
                  '과도한 신호 발생, 높은 수수료 비용으로 손실 가능성이 높습니다.'
                : '5분봉은 슬리피지 및 체결 괴리 위험이 있습니다. '
                  '예상과 다른 가격에 체결될 수 있습니다.',
            style: TextStyle(
              fontSize: 13,
              color: isRed ? Colors.red.shade700 : Colors.amber.shade700,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '💡 15분봉(15m) 이상 사용을 권장합니다.',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w500,
              color: isRed ? Colors.red.shade700 : Colors.amber.shade700,
            ),
          ),
        ],
      ),
    );
  }

  TfWarningLevel _getWarningLevel(String tf) {
    final minutes = _parseTfMinutes(tf);
    if (minutes < 5) return TfWarningLevel.red;
    if (minutes < 15) return TfWarningLevel.amber;
    return TfWarningLevel.none;
  }

  int _parseTfMinutes(String tf) {
    final match = RegExp(r'^(\d+)(m|h|d)$').firstMatch(tf);
    if (match == null) return 0;
    final value = int.parse(match.group(1)!);
    final unit = match.group(2)!;
    if (unit == 'h') return value * 60;
    if (unit == 'd') return value * 1440;
    return value;
  }
}
```

## 14-3) 타임라인 통합

```dart
class TimelineItem extends StatelessWidget {
  final TimelineEvent event;

  const TimelineItem({required this.event});

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        leading: _buildStatusIcon(),
        title: Row(
          children: [
            Text(event.symbol),
            const SizedBox(width: 8),
            // TF 경고 배지 표시
            if (event.tfWarning == true)
              TfWarningBadge(tf: event.tf),
          ],
        ),
        subtitle: Text('${event.side} • ${event.reasonCode}'),
        trailing: Text(
          _formatTime(event.timestamp),
          style: Theme.of(context).textTheme.bodySmall,
        ),
        onTap: () => _showDetail(context),
      ),
    );
  }

  void _showDetail(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (context) => SnapshotDetailSheet(
        event: event,
      ),
    );
  }
}
```

## 14-4) 스냅샷 상세 화면

```dart
class SnapshotDetailSheet extends StatelessWidget {
  final TimelineEvent event;

  const SnapshotDetailSheet({required this.event});

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.7,
      minChildSize: 0.5,
      maxChildSize: 0.95,
      builder: (context, scrollController) => Container(
        decoration: const BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
        ),
        child: ListView(
          controller: scrollController,
          padding: const EdgeInsets.all(16),
          children: [
            // 헤더
            Center(
              child: Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.grey.shade300,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ),
            const SizedBox(height: 16),

            // TF 경고 배너 (해당 시)
            if (event.tfWarning == true)
              TfWarningBanner(tf: event.tf),

            // 기본 정보
            _buildInfoSection('기본 정보', [
              _buildInfoRow('심볼', event.symbol),
              _buildInfoRow('거래소', event.exchange),
              _buildInfoRow('방향', event.side),
              _buildInfoRow('타임프레임', event.tf),
              _buildInfoRow('시간', _formatDateTime(event.timestamp)),
            ]),

            // 근거 정보
            _buildInfoSection('신호 근거', [
              _buildInfoRow('코드', event.reasonCode),
              _buildInfoRow('설명', event.reasonText),
            ]),

            // 스냅샷 정보
            if (event.snapshot != null)
              _buildSnapshotSection(event.snapshot!),

            // 차트 보기 버튼
            const SizedBox(height: 24),
            ElevatedButton.icon(
              onPressed: () => _openChart(context),
              icon: const Icon(Icons.show_chart),
              label: const Text('TradingView에서 보기'),
            ),
          ],
        ),
      ),
    );
  }

  // ... helper methods
}
```

---

# 15) 참조

- docs/PRODUCT_SPEC.md (제품 아키텍처)
- docs/PC_APP_SPEC.md (PC 앱 스펙)
- docs/AUTH_SPEC.md (인증 스펙)
- docs/TIMELINE_SPEC.md (타임라인 스키마)
- docs/PREMIUM_ENGINE_SPEC.md (Premium API)
- docs/ENTITLEMENT_SPEC.md (Week 17)
- docs/ONBOARDING.md (Week 18)

---

[END OF MOBILE_APP_SPEC]
