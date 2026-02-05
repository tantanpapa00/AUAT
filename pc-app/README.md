# BBooster PC Application

큐브시스템 (QUBE System) — Tauri 기반 Windows 설치형 애플리케이션

## Quick Start (Windows)

```powershell
# 1. Rust 설치 (처음 한번만)
powershell -ExecutionPolicy Bypass -File scripts\install-rust.ps1
# 설치 후 터미널 재시작 필요!

# 2. 프로젝트 셋업
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1

# 3. 개발 모드 실행
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1

# 4. 프로덕션 빌드
powershell -ExecutionPolicy Bypass -File scripts\build.ps1
```

## Prerequisites

- [Node.js](https://nodejs.org/) v18+
- [Rust](https://www.rust-lang.org/tools/install) 1.70+
- [Tauri CLI](https://tauri.app/v1/guides/getting-started/prerequisites)
- Windows 10/11 (64-bit)

## Manual Setup

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
cd src-tauri
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
- `src-tauri/target/release/bundle/msi/BBooster_x.x.x_x64.msi` (MSI 패키지)

## Structure

```
pc-app/
├── scripts/             # 빌드 스크립트
│   ├── install-rust.ps1 # Rust 설치
│   ├── setup.ps1        # 프로젝트 셋업
│   ├── dev.ps1          # 개발 모드 실행
│   └── build.ps1        # 프로덕션 빌드
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
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.js
│       ├── style.css
│       └── assets/
└── README.md
```

## Pages

| Page | Description |
|------|-------------|
| Dashboard | 서버 상태, E-STOP, 커넥터 상태, 타임라인, 최근 이벤트 |
| Accounts | 거래소 계좌 등록, API 키 관리 (OKX, KIS, Binance, Bybit, Upbit) |
| Templates | TradingView 웹훅 템플릿 생성기, JSON 복사 |
| Settings | E-STOP 제어, 시스템 상태, 서버 연결 설정 |
| Logs | 거래 로그 조회, 필터링, CSV 내보내기 |

## Features

### Core
- Server Control: 서버 시작/정지
- System Tray: 트레이 아이콘 + 메뉴
- E-STOP: 비상 정지 ON/OFF (사유 입력)
- Dashboard: 웹 대시보드 열기
- Diagnostic: 진단 리포트 zip 내보내기

### Security
- API Key Storage: OS 자격증명 관리자 연동
- AES-256-GCM 암호화 모듈
- 키 값 UI 마스킹

### Monitoring
- Timeline: 거래 타임라인 조회
- Connector Status: 거래소 연결 상태 확인
- Subscription: 구독 정보 조회
- Trade Logs: 상세 거래 로그 + CSV 내보내기

### Templates
- TradingView 웹훅 템플릿 생성
- 다중 자산 선택
- 클립보드 복사

## Tray Menu

- Status: 서버 상태 표시
- Start/Stop Server
- Open Dashboard
- Open Logs Folder
- Export Diagnostic
- E-STOP ON/OFF
- Quit

## Tauri Commands

| Command | Description |
|---------|-------------|
| start_server | 서버 시작 |
| stop_server | 서버 정지 |
| get_server_status | 서버 상태 조회 |
| set_estop | E-STOP 설정 |
| get_home_data | 홈 데이터 조회 |
| save_account_keys | 계좌 키 저장 |
| get_account_keys | 계좌 키 조회 |
| delete_account_keys | 계좌 키 삭제 |
| list_local_accounts | 로컬 계좌 목록 |
| fetch_server_accounts | 서버 계좌 목록 |
| test_account_connection | 연결 테스트 |
| fetch_timeline | 타임라인 조회 |
| fetch_connector_status | 커넥터 상태 |
| fetch_subscription | 구독 정보 |
| export_diagnostic | 진단 내보내기 |
| open_dashboard | 대시보드 열기 |
| open_logs_folder | 로그 폴더 열기 |

## Icons

아이콘 파일은 `src-tauri/icons/` 폴더에 배치:
- icon.ico (Windows)
- icon.png (기타)
- 32x32.png, 128x128.png, 128x128@2x.png

## Notes

- 서버(AUAT)가 `C:\autobot` 또는 프로젝트 폴더에 있어야 합니다
- VPS 환경에서는 Docker Compose로 서버 실행
- 로컬 테스트 시 Python + uvicorn 필요
