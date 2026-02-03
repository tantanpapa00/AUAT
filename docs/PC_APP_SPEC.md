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

# 7) Day 2 상세: 계좌/키 등록 (Week 11 Day 2)

## 7-1) UI 구성 (Accounts.vue)

```
┌─────────────────────────────────────────────────────────────┐
│  계좌 관리                                        [+ 추가]  │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────┐    │
│  │ okx-main (OKX)                           [활성] [편집] │
│  │ API Key: ****d38                                    │    │
│  │ 마지막 헬스체크: 2026-02-03 14:30                    │    │
│  └─────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ kis-vps (KIS)                          [비활성] [편집] │
│  │ API Key: ****abc                                    │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 7-2) Tauri 커맨드 (Rust)

```rust
// src/commands/keys.rs

use keyring::Entry;
use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
pub struct AccountKeys {
    pub api_key: String,
    pub api_secret: String,
    pub passphrase: Option<String>,
}

#[tauri::command]
pub fn save_account_keys(
    account_name: String,
    exchange: String,
    keys: AccountKeys
) -> Result<(), String> {
    let service = format!("bbooster-{}", exchange.to_lowercase());

    // API Key 저장
    let key_entry = Entry::new(&service, &format!("{}_key", account_name))
        .map_err(|e| e.to_string())?;
    key_entry.set_password(&keys.api_key).map_err(|e| e.to_string())?;

    // API Secret 저장
    let secret_entry = Entry::new(&service, &format!("{}_secret", account_name))
        .map_err(|e| e.to_string())?;
    secret_entry.set_password(&keys.api_secret).map_err(|e| e.to_string())?;

    // Passphrase 저장 (OKX만)
    if let Some(pass) = keys.passphrase {
        let pass_entry = Entry::new(&service, &format!("{}_passphrase", account_name))
            .map_err(|e| e.to_string())?;
        pass_entry.set_password(&pass).map_err(|e| e.to_string())?;
    }

    Ok(())
}

#[tauri::command]
pub fn get_account_keys(
    account_name: String,
    exchange: String
) -> Result<AccountKeys, String> {
    let service = format!("bbooster-{}", exchange.to_lowercase());

    let key_entry = Entry::new(&service, &format!("{}_key", account_name))
        .map_err(|e| e.to_string())?;
    let secret_entry = Entry::new(&service, &format!("{}_secret", account_name))
        .map_err(|e| e.to_string())?;

    let api_key = key_entry.get_password().map_err(|e| e.to_string())?;
    let api_secret = secret_entry.get_password().map_err(|e| e.to_string())?;

    // Passphrase는 optional
    let passphrase = Entry::new(&service, &format!("{}_passphrase", account_name))
        .ok()
        .and_then(|e| e.get_password().ok());

    Ok(AccountKeys { api_key, api_secret, passphrase })
}

#[tauri::command]
pub fn delete_account_keys(account_name: String, exchange: String) -> Result<(), String> {
    let service = format!("bbooster-{}", exchange.to_lowercase());

    // 모든 키 삭제
    for suffix in ["key", "secret", "passphrase"] {
        if let Ok(entry) = Entry::new(&service, &format!("{}_{}", account_name, suffix)) {
            let _ = entry.delete_credential();
        }
    }

    Ok(())
}
```

## 7-3) API 연동

| 작업 | Tauri 커맨드 | 서버 API |
|------|--------------|----------|
| 계좌 목록 조회 | - | GET /api/accounts |
| 계좌 등록 | save_account_keys | POST /api/accounts |
| 키 검증 | - | GET /api/diag/okx-preflight, /api/diag/kis-preflight |

## 7-4) 보안 체크리스트

- [x] OS 자격증명 관리자 사용 (Windows Credential Manager)
- [x] 키 값 UI에 마스킹 (****d38)
- [x] 키 값 로그 출력 금지
- [x] 메모리에서 키 사용 후 즉시 삭제

---

# 8) Day 3 상세: 템플릿 생성 UI (Week 11 Day 3)

## 8-1) 개요

PC 앱에서 TradingView 얼러트 템플릿을 쉽게 생성하고 복사할 수 있는 UI.

**지원 기능**:
1. **자산별 템플릿**: 단일 자산 선택 → 템플릿 생성
2. **배치 생성**: 여러 자산 선택 → 한번에 템플릿 생성
3. **ShortMsg 템플릿**: 간소화된 short_id 기반 템플릿

## 8-2) UI 구성 (Templates.vue)

```
┌─────────────────────────────────────────────────────────────────────┐
│  TradingView 템플릿 생성                                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  [탭: 자산별 템플릿] [탭: 배치 생성] [탭: ShortMsg]                    │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  자산 선택                                                    │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │ [v] okx-main / momentum / BTC-USDT                      │  │  │
│  │  │ [ ] okx-main / momentum / ETH-USDT                      │  │  │
│  │  │ [v] kis-vps / swing / 삼성전자                           │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  │                                                                │  │
│  │  옵션                                                          │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │  │
│  │  │ Side: [buy▼] │  │ Qty: [1    ] │  │ Type: [market▼]│       │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘         │  │
│  │                                                                │  │
│  │  [템플릿 생성]                                                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  생성된 템플릿 (2개)                                          │  │
│  │                                                                │  │
│  │  ▼ BTC-USDT (okx-main / momentum)                 [복사 📋]   │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │ {                                                       │  │  │
│  │  │   "secret": "abc123...",                               │  │  │
│  │  │   "symbol": "BTC-USDT",                                │  │  │
│  │  │   "side": "buy",                                       │  │  │
│  │  │   "qty": 1,                                            │  │  │
│  │  │   "alert_id": "{{timenow}}",                           │  │  │
│  │  │   "type": "market"                                     │  │  │
│  │  │ }                                                       │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  │                                                                │  │
│  │  ▼ 삼성전자 (kis-vps / swing)                      [복사 📋]   │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │ { ... }                                                 │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  💡 TradingView 얼러트 > Message에 위 JSON을 붙여넣으세요          │
└─────────────────────────────────────────────────────────────────────┘
```

## 8-3) API 연동

| 작업 | HTTP | 엔드포인트 | 설명 |
|------|------|------------|------|
| 옵션 목록 조회 | GET | /api/templates/tradingview/options | 활성 계좌/전략/자산 목록 |
| 단일 자산 템플릿 | GET | /api/assets/{asset_id}/template/tradingview?side=buy&qty=1 | 개별 생성 |
| 배치 생성 | POST | /api/templates/tradingview/generate | 다중 자산 한번에 |
| ShortMsg 템플릿 | GET | /api/shortmsg/{short_id}/template/tradingview | ShortMsg용 |

## 8-4) API 응답 스키마

### GET /api/templates/tradingview/options

```json
{
  "ok": true,
  "count": 3,
  "options": [
    {
      "asset_id": 1,
      "symbol": "BTC-USDT",
      "market": "spot",
      "account_id": 1,
      "account_name": "okx-main",
      "exchange": "OKX",
      "strategy_id": 1,
      "strategy_name": "momentum",
      "label": "okx-main / momentum / BTC-USDT"
    }
  ]
}
```

### POST /api/templates/tradingview/generate

**Request:**
```json
{
  "asset_ids": [1, 2, 3],
  "side": "buy",
  "qty": 1,
  "type": "market"
}
```

**Response:**
```json
{
  "ok": true,
  "count": 3,
  "results": [
    {
      "asset_id": 1,
      "ok": true,
      "symbol": "BTC-USDT",
      "exchange": "OKX",
      "account_name": "okx-main",
      "strategy_name": "momentum",
      "template": {
        "secret": "abc123",
        "symbol": "BTC-USDT",
        "side": "buy",
        "qty": 1,
        "alert_id": "{{timenow}}",
        "type": "market"
      },
      "template_json": "{\n  \"secret\": \"abc123\",\n  ...}"
    }
  ]
}
```

## 8-5) Tauri 커맨드 (Rust)

```rust
// src/commands/clipboard.rs

use tauri::Manager;

#[tauri::command]
pub async fn copy_to_clipboard(app: tauri::AppHandle, text: String) -> Result<(), String> {
    use arboard::Clipboard;

    let mut clipboard = Clipboard::new().map_err(|e| e.to_string())?;
    clipboard.set_text(&text).map_err(|e| e.to_string())?;

    // 성공 알림 (optional)
    app.emit_all("clipboard_copied", ()).ok();

    Ok(())
}

#[tauri::command]
pub fn format_template_preview(template_json: String, max_lines: usize) -> String {
    // 미리보기용 축약
    let lines: Vec<&str> = template_json.lines().collect();
    if lines.len() <= max_lines {
        template_json
    } else {
        let preview: Vec<&str> = lines.iter().take(max_lines - 1).cloned().collect();
        format!("{}\n  ...", preview.join("\n"))
    }
}
```

## 8-6) 프론트엔드 컴포넌트 (Vue)

```vue
<!-- ui/src/pages/Templates.vue -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { invoke } from '@tauri-apps/api/tauri'

interface AssetOption {
  asset_id: number
  symbol: string
  market: string
  account_name: string
  exchange: string
  strategy_name: string
  label: string
}

interface GeneratedTemplate {
  asset_id: number
  ok: boolean
  symbol: string
  exchange: string
  template_json: string
  error?: string
}

const options = ref<AssetOption[]>([])
const selected = ref<number[]>([])
const side = ref<'buy' | 'sell'>('buy')
const qty = ref(1)
const orderType = ref('market')
const templates = ref<GeneratedTemplate[]>([])
const loading = ref(false)

onMounted(async () => {
  // 옵션 목록 로드
  const resp = await fetch('http://127.0.0.1:8000/api/templates/tradingview/options')
  const data = await resp.json()
  if (data.ok) {
    options.value = data.options
  }
})

async function generateTemplates() {
  if (selected.value.length === 0) return

  loading.value = true
  try {
    const resp = await fetch('http://127.0.0.1:8000/api/templates/tradingview/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        asset_ids: selected.value,
        side: side.value,
        qty: qty.value,
        type: orderType.value
      })
    })
    const data = await resp.json()
    if (data.ok) {
      templates.value = data.results
    }
  } finally {
    loading.value = false
  }
}

async function copyTemplate(templateJson: string) {
  await invoke('copy_to_clipboard', { text: templateJson })
  // Toast 알림 표시
}
</script>
```

## 8-7) 워크플로우

```
┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│ 1. 옵션 로드   │ ──► │ 2. 자산 선택   │ ──► │ 3. 옵션 설정   │
│ GET /options   │     │ (체크박스)     │     │ side/qty/type  │
└────────────────┘     └────────────────┘     └────────────────┘
                                                      │
                                                      ▼
┌────────────────┐     ┌────────────────┐     ┌────────────────┐
│ 6. 완료       │ ◄── │ 5. 클립보드    │ ◄── │ 4. 템플릿 생성 │
│ TV에 붙여넣기 │     │ 복사           │     │ POST /generate │
└────────────────┘     └────────────────┘     └────────────────┘
```

## 8-8) ShortMsg 탭 UI

```
┌─────────────────────────────────────────────────────────────────────┐
│  ShortMsg 템플릿                                                    │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  등록된 ShortMsg                                                    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ ID: XyZ12345  │ 이름: BTC 롱                    [템플릿 보기] │    │
│  │ OKX / spot / BTC-USDT                                      │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │ ID: AbC67890  │ 이름: 삼성전자 매수              [템플릿 보기] │    │
│  │ KIS / stock / 005930                                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                     │
│  ShortMsg 템플릿 장점:                                              │
│  • TV 변수 최소화 (short_id가 모든 설정 포함)                        │
│  • 설정 변경 시 템플릿 재생성 불필요                                  │
│  • 여러 자산에 동일 템플릿 재사용 가능                                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## 8-9) 에러 처리

| 상황 | UI 표시 | 처리 |
|------|---------|------|
| 활성 자산 없음 | "활성 자산이 없습니다. 계좌/전략/자산을 먼저 설정하세요." | 계좌 페이지 링크 |
| tv_secret 미설정 | "전략에 tv_secret이 설정되지 않았습니다." | 해당 자산 결과에 error 표시 |
| 네트워크 오류 | "서버 연결 실패. 서버가 실행 중인지 확인하세요." | 재시도 버튼 |

## 8-10) 보안 체크리스트

- [x] secret 값은 템플릿 JSON에만 포함 (UI에 직접 표시 X)
- [x] 클립보드 복사 후 자동 만료 옵션 (선택적)
- [x] 템플릿 로그 저장 시 secret 마스킹

---

# 9) 구현 계획

| Day | 작업 | 상태 |
|-----|------|------|
| Day 1 | 기술선정 + 빌드/런 구조 문서화 | DONE |
| Day 2 | 계좌/키 등록 UI + 암호화 저장 | DONE (spec) |
| Day 3 | 템플릿 생성 UI 연결 | DONE (spec) |
| Day 4 | 시스템 설정 UI 연결 | TODO |
| Day 5 | 회귀 테스트 + 실측 로그 | TODO |

---

# 10) 참조

- [Tauri 공식 문서](https://tauri.app/v1/guides/)
- [Tauri + Vue 예제](https://github.com/tauri-apps/tauri/tree/dev/examples)
- docs/PRODUCT_SPEC.md 1-6 B) PC 프로그램 역할
- docs/AUTH_SPEC.md 5-7) 로컬 저장 보안

---

[END OF PC_APP_SPEC]
