# BBooster Mobile App

Flutter 기반 Android 앱 (v0.1.0) — 큐브시스템 (QUBE System)

## Quick Start (Windows)

```powershell
# 1. Flutter 설치 후 셋업
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

# 2. 개발 모드 실행
flutter run

# 3. APK 빌드
powershell -ExecutionPolicy Bypass -File scripts\build-apk.ps1
```

## Features (v0.1)

| Feature | Description |
|---------|-------------|
| Dashboard | 서버 상태, 커넥터 상태, 요약 통계 |
| E-STOP | 비상 정지 ON/OFF (사유 입력, 햅틱 피드백) |
| Timeline | 주문 이력, 필터링 (Status/Exchange) |
| Chart | TradingView 차트 (BTC, ETH, SOL 등) |
| Settings | 서버 URL 설정, Quick Connect |

## Prerequisites

- [Flutter SDK](https://flutter.dev/docs/get-started/install) 3.0+
- Android Studio or VS Code with Flutter extension
- Android SDK (API 21+)
- Java JDK 11+ (for keystore generation)

## Installation

### 1. Flutter 설치

```powershell
# Windows (winget)
winget install Google.Flutter

# 설치 확인
flutter doctor
```

### 2. 프로젝트 셋업

```powershell
cd mobile-app
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
```

### 3. 개발 모드 실행

```powershell
# 에뮬레이터 또는 실제 기기 연결 후
flutter run

# 또는 디버그 APK 빌드
flutter build apk --debug
```

## Build APK

### Debug Build

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-apk.ps1 -Debug
```

### Release Build

```powershell
# 1. 키스토어 생성 (처음 한번만)
powershell -ExecutionPolicy Bypass -File scripts\create-keystore.ps1

# 2. key.properties 설정
copy android\key.properties.example android\key.properties
# key.properties 파일에 비밀번호 입력

# 3. 릴리즈 빌드
powershell -ExecutionPolicy Bypass -File scripts\build-apk.ps1
```

### Build Output

빌드 후 `release/` 폴더에 APK 파일 생성:

| File | Architecture | Description |
|------|--------------|-------------|
| BBooster-v0.1.0-arm64.apk | ARM64 | 최신 기기 (권장) |
| BBooster-v0.1.0-arm32.apk | ARM32 | 구형 기기 |
| BBooster-v0.1.0-x64.apk | x86_64 | 에뮬레이터/ChromeOS |
| BBooster-v0.1.0-universal.apk | All | 모든 아키텍처 (용량 큼) |

## Project Structure

```
mobile-app/
├── scripts/                 # 빌드 스크립트
│   ├── setup.ps1            # Flutter 셋업
│   ├── build-apk.ps1        # APK 빌드
│   └── create-keystore.ps1  # 키스토어 생성
├── android/                 # Android 네이티브
│   ├── app/
│   │   ├── build.gradle     # 빌드 설정
│   │   ├── proguard-rules.pro
│   │   └── src/main/
│   │       ├── AndroidManifest.xml
│   │       ├── kotlin/...
│   │       └── res/
│   ├── key.properties.example  # 서명 설정 템플릿
│   └── keystore/            # 키스토어 (gitignore)
├── assets/
│   └── logo.png
├── lib/
│   ├── main.dart            # App entry (4탭 네비게이션)
│   ├── models/
│   ├── providers/
│   │   └── app_state.dart   # 상태 관리
│   ├── services/
│   │   └── api_service.dart # API 클라이언트
│   ├── screens/
│   │   ├── home_screen.dart      # Dashboard
│   │   ├── timeline_screen.dart  # Timeline
│   │   ├── chart_screen.dart     # TradingView Chart
│   │   └── settings_screen.dart  # Settings
│   └── widgets/
│       ├── estop_button.dart     # E-STOP (애니메이션, 사유 입력)
│       ├── connector_card.dart
│       ├── status_card.dart
│       └── event_list.dart
├── release/                 # 빌드 출력 (gitignore)
├── pubspec.yaml
├── analysis_options.yaml
└── README.md
```

## Dependencies

| Package | Version | Description |
|---------|---------|-------------|
| http | ^1.1.0 | HTTP client |
| flutter_secure_storage | ^9.0.0 | Secure token storage |
| provider | ^6.1.0 | State management |
| webview_flutter | ^4.4.0 | TradingView charts |
| pull_to_refresh | ^2.0.0 | Pull to refresh |
| cupertino_icons | ^1.0.6 | iOS style icons |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| /health | GET | 서버 헬스체크 |
| /api/diag/home | GET | 홈 데이터 |
| /api/diag/connectors | GET | 커넥터 상태 |
| /api/system/estop | GET | E-STOP 상태 |
| /api/system/estop | POST | E-STOP 설정 (reason 지원) |
| /api/timeline | GET | 타임라인 |
| /api/subscription | GET | 구독 정보 |

## Security

- API 키는 앱에 저장하지 않음 (PC에서만 관리)
- 서버 URL만 로컬 저장
- E-STOP만 제어 가능 (주문 직접 발행 불가)
- key.properties, keystore 파일 절대 커밋 금지

## Permissions

```xml
<uses-permission android:name="android.permission.INTERNET"/>
```

## Troubleshooting

### Flutter doctor 오류

```powershell
flutter doctor --android-licenses
flutter doctor
```

### 빌드 실패

```powershell
# 캐시 정리
flutter clean
flutter pub get
flutter build apk --release
```

### WebView 로딩 안됨

- 인터넷 연결 확인
- `android:usesCleartextTraffic="true"` 확인 (HTTP 사용 시)

## Version History

- **v0.1.0** (2026-02)
  - 초기 릴리즈
  - Dashboard, Timeline, Chart, Settings
  - E-STOP with reason input
  - TradingView WebView

## Next Steps (v0.2+)

- 로그인/토큰 인증
- Push Notification
- 오프라인 캐시
- iOS 지원
