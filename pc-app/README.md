# BBooster PC Application

큐브시스템 (QUBE System) — Tauri 기반 Windows 설치형 애플리케이션

## Prerequisites

- [Node.js](https://nodejs.org/) v18+
- [Rust](https://www.rust-lang.org/tools/install)
- [Tauri CLI](https://tauri.app/v1/guides/getting-started/prerequisites)

## Setup

```bash
# 1. Install Node dependencies
cd ui
npm install

# 2. Install Rust dependencies (자동)
cd ../src-tauri
cargo build
```

## Development

```bash
# UI 개발 서버 + Tauri 앱 실행
cd ui
npm run dev

# 다른 터미널에서
cd ../src-tauri
cargo tauri dev
```

## Build

```bash
# Windows 설치파일 생성
cd src-tauri
cargo tauri build
```

빌드 결과물:
- `src-tauri/target/release/BBooster.exe` (실행파일)
- `src-tauri/target/release/bundle/nsis/BBooster_x.x.x_x64-setup.exe` (설치파일)

## Structure

```
pc-app/
├── src-tauri/           # Tauri 백엔드 (Rust)
│   ├── Cargo.toml       # Rust 의존성
│   ├── tauri.conf.json  # Tauri 설정
│   ├── icons/           # 앱 아이콘
│   └── src/
│       ├── main.rs      # 엔트리포인트
│       ├── commands.rs  # Tauri 커맨드
│       └── crypto.rs    # AES-GCM 암호화
├── ui/                  # 프론트엔드
│   ├── package.json
│   ├── index.html
│   └── src/
│       ├── main.js
│       └── style.css
└── README.md
```

## Features

- Server Control: 서버 시작/정지
- System Tray: 트레이 아이콘 + 메뉴
- E-STOP: 비상 정지 ON/OFF
- Dashboard: 웹 대시보드 열기
- Diagnostic: 진단 리포트 zip 내보내기
- API Key Storage: OS 자격증명 관리자에 암호화 저장 (AES-256-GCM)
- Timeline: 거래 타임라인 조회
- Connector Status: 거래소 연결 상태 확인
- Subscription: 구독 정보 조회

## Tray Menu

- Status: 서버 상태 표시
- Start/Stop Server
- Open Dashboard
- Open Logs Folder
- Export Diagnostic
- E-STOP ON/OFF
- Quit

## Icons

아이콘 파일은 `src-tauri/icons/` 폴더에 배치:
- icon.ico (Windows)
- icon.png (기타)
- 32x32.png, 128x128.png, 128x128@2x.png

## Notes

- 서버(autobot)가 `C:\autobot`에 있어야 합니다
- 또는 빌드 시 서버를 앱과 함께 번들링
