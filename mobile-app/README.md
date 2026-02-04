# BBooster Mobile App

Flutter 기반 Android/iOS 앱 (v0.1)

## Features (v0.1)

- **Server Status**: 서버 연결 상태 모니터링
- **E-STOP Control**: 비상 정지 ON/OFF
- **Recent Orders**: 최근 주문 상태 확인
- **Settings**: 서버 URL 설정

## Prerequisites

- [Flutter SDK](https://flutter.dev/docs/get-started/install) 3.0+
- Android Studio or VS Code with Flutter extension
- Android SDK (for Android build)
- Xcode (for iOS build, macOS only)

## Setup

```bash
# 1. Flutter 설치 확인
flutter --version

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
├── lib/
│   ├── main.dart              # App entry point
│   ├── providers/
│   │   └── app_state.dart     # State management
│   ├── services/
│   │   └── api_service.dart   # API client
│   ├── screens/
│   │   ├── home_screen.dart   # Main dashboard
│   │   └── settings_screen.dart
│   └── widgets/
│       ├── status_card.dart   # Status indicator
│       ├── estop_button.dart  # E-STOP control
│       └── event_list.dart    # Order list
├── pubspec.yaml               # Dependencies
└── README.md
```

## Permissions

v0.1은 최소 권한으로 동작:
- `INTERNET`: 서버 통신

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
