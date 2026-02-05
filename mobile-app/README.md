# BBooster Mobile App

Flutter 기반 Android 앱 (v0.1) — 큐브시스템 (QUBE System)

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

- **Server Status**: 서버 연결 상태 모니터링
- **E-STOP Control**: 비상 정지 ON/OFF
- **Recent Orders**: 최근 주문 상태 확인
- **Settings**: 서버 URL 설정

## Prerequisites

- [Flutter SDK](https://flutter.dev/docs/get-started/install) 3.0+
- Android Studio or VS Code with Flutter extension
- Android SDK (API 21+)
- Java JDK 11+

## Manual Setup

```bash
# 1. Flutter 설치 확인
flutter --version
flutter doctor

# 2. 의존성 설치
cd mobile-app
flutter pub get

# 3. 개발 서버 실행 (Android 에뮬레이터 또는 실제 기기)
flutter run
```

## Build APK

```bash
# Debug APK
flutter build apk --debug

# Release APK
flutter build apk --release

# APK 위치
# build/app/outputs/flutter-apk/app-release.apk
```

## Project Structure

```
mobile-app/
├── scripts/                 # 빌드 스크립트
│   ├── setup.ps1            # Flutter 셋업
│   └── build-apk.ps1        # APK 빌드
├── android/                 # Android 네이티브
│   ├── app/
│   │   ├── build.gradle
│   │   └── src/main/
│   │       ├── AndroidManifest.xml
│   │       ├── kotlin/...   # MainActivity.kt
│   │       └── res/         # 아이콘, 스타일
│   ├── build.gradle
│   └── settings.gradle
├── assets/                  # 앱 에셋
│   └── logo.png
├── lib/                     # Dart 소스코드
│   ├── main.dart            # App entry point
│   ├── models/              # 데이터 모델
│   │   ├── timeline_event.dart
│   │   └── connector_status.dart
│   ├── providers/           # 상태 관리
│   │   └── app_state.dart
│   ├── services/            # API 클라이언트
│   │   └── api_service.dart
│   ├── screens/             # 화면
│   │   ├── home_screen.dart
│   │   └── settings_screen.dart
│   └── widgets/             # UI 컴포넌트
│       ├── status_card.dart
│       ├── estop_button.dart
│       └── event_list.dart
├── pubspec.yaml             # Dependencies
├── analysis_options.yaml    # Lint rules
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

## Permissions

v0.1은 최소 권한으로 동작:
- `INTERNET`: 서버 통신

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| /health | GET | 서버 헬스체크 |
| /api/diag/home | GET | 홈 데이터 |
| /api/system/estop | GET | E-STOP 상태 |
| /api/system/estop | POST | E-STOP 설정 |
| /api/timeline | GET | 타임라인 |

## Security Notes

- API 키는 앱에 저장하지 않음 (PC에서만 관리)
- 서버 URL만 로컬 저장
- E-STOP만 제어 가능 (주문 직접 발행 불가)

## v0.1 Limitations

- PlayStore 배포 아님 (APK 직접 설치)
- 알림(Push Notification) 미구현
- 오프라인 캐시 미구현
- 로그인/인증 미구현 (서버 URL만 설정)

## Next Steps (v0.2+)

- 로그인/토큰 인증
- Push Notification
- 오프라인 캐시
- TradingView 차트 WebView
- iOS 지원
