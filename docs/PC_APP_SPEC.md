# PC_APP_SPEC.md (SSOT)
- Last updated: 2026-02-03 KST
- Owner: 기훈(작가님)
- Status: DRAFT (Week 11 Day 1)

> NOTE: 이 파일은 PC 프로그램 기술 스펙의 '진실(SSOT)'입니다.

---

# 1) 기술 선정

## 1-1) 후보 비교

| 기준 | Tauri | Electron | .NET (WPF) |
|------|-------|----------|------------|
| 언어 | Rust + Web | Node.js + Web | C# |
| 바이너리 크기 | ~10MB | ~150MB+ | ~20MB |
| 메모리 사용 | 낮음 | 높음 | 중간 |
| 크로스 플랫폼 | O (Win/Mac/Linux) | O | X (Windows only) |
| 보안 (키 암호화) | 우수 (Rust) | 보통 | 우수 |
| 웹 UI 재사용 | O | O | X |
| 학습 곡선 | 중간 | 낮음 | 높음 |
| 생태계 | 성장 중 | 성숙 | 성숙 |

## 1-2) 선정: Tauri (권장)

### 선정 이유
1. **가벼움**: 바이너리 ~10MB, 메모리 효율적
2. **보안**: Rust 기반, API 키 암호화에 적합
3. **웹 UI 재사용**: 기존 FastAPI 프론트엔드 활용 가능
4. **크로스 플랫폼**: Windows 우선, 향후 Mac/Linux 지원 가능
5. **현대적**: 활발한 개발, 좋은 DX

### 대안 (필요 시)
- Electron: 빠른 개발 필요 시
- .NET: Windows 전용 + 네이티브 성능 필요 시

---

# 2) 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    PC App (Tauri)                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────────────────────┐ │
│  │   Frontend      │    │   Backend (Rust)                │ │
│  │   (Web: React/  │◄──►│   - API 호출                    │ │
│  │    Vue/Svelte)  │    │   - 키 암호화/복호화            │ │
│  │                 │    │   - 로컬 설정 저장              │ │
│  └─────────────────┘    │   - OS 자격증명 관리자 연동     │ │
│                         └─────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │   Server (FastAPI)            │
              │   http://127.0.0.1:8000       │
              │   - /api/home                 │
              │   - /api/subscription/me      │
              │   - /api/timeline             │
              │   - /api/diag/*               │
              └───────────────────────────────┘
```

---

# 3) 디렉토리 구조

```
pc-app/
├── src/
│   ├── main.rs              # Tauri 백엔드 엔트리
│   ├── commands/            # Tauri 커맨드 (Rust)
│   │   ├── mod.rs
│   │   ├── auth.rs          # 로그인/토큰 관리
│   │   ├── keys.rs          # API 키 암호화/저장
│   │   └── settings.rs      # 설정 관리
│   └── lib.rs
├── src-tauri/
│   ├── Cargo.toml
│   ├── tauri.conf.json      # Tauri 설정
│   └── icons/
├── ui/                      # 프론트엔드
│   ├── src/
│   │   ├── App.vue          # 또는 App.tsx
│   │   ├── pages/
│   │   │   ├── Dashboard.vue
│   │   │   ├── Accounts.vue
│   │   │   ├── Templates.vue
│   │   │   ├── Settings.vue
│   │   │   └── Logs.vue
│   │   └── components/
│   ├── package.json
│   └── vite.config.ts
├── .env.example
└── README.md
```

---

# 4) 빌드/런 구조

## 4-1) 개발 환경 설정

### 필수 요구사항
- Node.js 18+
- Rust 1.70+
- Tauri CLI

### 설치
```bash
# Rust 설치
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Tauri CLI 설치
cargo install tauri-cli

# 프로젝트 클론
git clone <repo> pc-app
cd pc-app

# 의존성 설치
npm install
```

## 4-2) 개발 모드

```bash
# 개발 서버 실행 (핫 리로드)
npm run tauri dev
```

## 4-3) 프로덕션 빌드

```bash
# Windows 빌드 (.msi, .exe)
npm run tauri build

# 출력 위치
# src-tauri/target/release/bundle/
```

## 4-4) 빌드 산출물

| 파일 | 설명 |
|------|------|
| `bbooster-hub_x.x.x_x64.msi` | Windows 설치 패키지 |
| `bbooster-hub_x.x.x_x64-setup.exe` | NSIS 설치 프로그램 |
| `bbooster-hub.exe` | 포터블 실행 파일 |

---

# 5) 핵심 기능 매핑

| 기능 | UI 페이지 | API 엔드포인트 | Tauri 커맨드 |
|------|-----------|----------------|--------------|
| 대시보드 | Dashboard | /api/home, /api/timeline | - |
| 계좌 등록 | Accounts | /api/accounts | save_account |
| API 키 등록 | Accounts | - | encrypt_key, save_key |
| 전략 설정 | Templates | /api/strategies | - |
| 템플릿 생성 | Templates | /api/templates/tradingview/generate | - |
| 시스템 설정 | Settings | /api/system/estop | save_settings |
| 로그 조회 | Logs | /api/timeline | - |
| CSV 내보내기 | Logs | - | export_csv |

---

# 6) 보안 고려사항

## 6-1) API 키 저장

```rust
// Windows: Credential Manager 사용
// Mac: Keychain 사용
// Linux: libsecret 사용

use keyring::Entry;

fn save_api_key(service: &str, username: &str, key: &str) -> Result<()> {
    let entry = Entry::new(service, username)?;
    entry.set_password(key)?;
    Ok(())
}
```

## 6-2) 보안 원칙

1. **키 값 로그 금지**: API 키/시크릿은 절대 로그에 출력하지 않음
2. **메모리 보호**: 키 사용 후 즉시 메모리에서 삭제
3. **HTTPS 필수**: 서버 통신은 HTTPS만 허용
4. **토큰 암호화 저장**: access_token도 OS 자격증명 관리자에 저장

---

# 7) 구현 계획

| Day | 작업 | 상태 |
|-----|------|------|
| Day 1 | 기술선정 + 빌드/런 구조 문서화 | DONE |
| Day 2 | 계좌/키 등록 UI + 암호화 저장 | TODO |
| Day 3 | 템플릿 생성 UI 연결 | TODO |
| Day 4 | 시스템 설정 UI 연결 | TODO |
| Day 5 | 회귀 테스트 + 실측 로그 | TODO |

---

# 8) 참조

- [Tauri 공식 문서](https://tauri.app/v1/guides/)
- [Tauri + Vue 예제](https://github.com/tauri-apps/tauri/tree/dev/examples)
- docs/PRODUCT_SPEC.md 1-6 B) PC 프로그램 역할
- docs/AUTH_SPEC.md 5-7) 로컬 저장 보안

---

[END OF PC_APP_SPEC]
