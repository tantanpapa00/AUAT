use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use std::process::Command;
use tauri::AppHandle;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

// =====================================================
// Server Management (VPS 연결 방식 - 로컬 서버 시작 불필요)
// =====================================================

const VPS_SERVER_URL: &str = "http://76.13.180.30";

#[tauri::command]
pub async fn start_server() -> Result<String, String> {
    // VPS 서버에 연결하므로 로컬 서버 시작 불필요
    // VPS 연결 상태만 확인
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    match client
        .get(format!("{}/api/diag/home", VPS_SERVER_URL))
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
    {
        Ok(resp) if resp.status().is_success() => {
            Ok("VPS 서버 연결됨".to_string())
        }
        Ok(_) => Err("VPS 서버 응답 오류".to_string()),
        Err(e) => Err(format!("VPS 서버 연결 실패: {}", e)),
    }
}

pub async fn start_server_internal(_app: &AppHandle) -> Result<String, String> {
    start_server().await
}

#[tauri::command]
pub async fn stop_server() -> Result<String, String> {
    // VPS 서버 사용 시 로컬 서버 종료 불필요
    // 연결 해제 메시지만 반환
    Ok("VPS 서버 연결 해제 (서버는 계속 실행 중)".to_string())
}

pub async fn stop_server_internal(_app: &AppHandle) -> Result<String, String> {
    stop_server().await
}

#[derive(Serialize, Deserialize)]
pub struct HealthCheckResult {
    pub ok: bool,
    pub message: String,
    pub latency_ms: u64,
}

#[tauri::command]
pub async fn check_server_health() -> Result<HealthCheckResult, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let start = std::time::Instant::now();

    match client
        .get(format!("{}/api/health", VPS_SERVER_URL))
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
    {
        Ok(resp) => {
            let latency = start.elapsed().as_millis() as u64;
            if resp.status().is_success() {
                Ok(HealthCheckResult {
                    ok: true,
                    message: "VPS 서버 연결 성공".to_string(),
                    latency_ms: latency,
                })
            } else {
                Ok(HealthCheckResult {
                    ok: false,
                    message: format!("서버 응답 오류: {}", resp.status()),
                    latency_ms: latency,
                })
            }
        }
        Err(e) => {
            let latency = start.elapsed().as_millis() as u64;
            Ok(HealthCheckResult {
                ok: false,
                message: format!("연결 실패: {}", e),
                latency_ms: latency,
            })
        }
    }
}

#[tauri::command]
pub async fn get_server_status() -> Result<ServerStatus, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    match client
        .get(format!("{}/api/diag/home", VPS_SERVER_URL))
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .await
    {
        Ok(resp) => {
            if resp.status().is_success() {
                let data: serde_json::Value = resp.json().await.unwrap_or_default();
                Ok(ServerStatus {
                    running: true,
                    estop: data.get("estop").and_then(|v| v.as_bool()).unwrap_or(false),
                    dry_run: data.get("dry_run").and_then(|v| v.as_bool()).unwrap_or(false),
                })
            } else {
                Ok(ServerStatus {
                    running: false,
                    estop: false,
                    dry_run: false,
                })
            }
        }
        Err(_) => Ok(ServerStatus {
            running: false,
            estop: false,
            dry_run: false,
        }),
    }
}

#[derive(Serialize, Deserialize)]
pub struct ServerStatus {
    pub running: bool,
    pub estop: bool,
    pub dry_run: bool,
}

// =====================================================
// Dashboard & Logs
// =====================================================

#[tauri::command]
pub async fn open_dashboard() -> Result<(), String> {
    open::that(VPS_SERVER_URL).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn open_logs_folder() -> Result<(), String> {
    let logs_path = get_logs_path()?;
    fs::create_dir_all(&logs_path).map_err(|e| e.to_string())?;
    open::that(&logs_path).map_err(|e| e.to_string())
}

// =====================================================
// Diagnostic Export
// =====================================================

#[tauri::command]
pub async fn export_diagnostic() -> Result<String, String> {
    let diagnostic_path = create_diagnostic_zip().await?;
    Ok(diagnostic_path)
}

pub async fn export_diagnostic_internal(_app: &AppHandle) -> Result<String, String> {
    export_diagnostic().await
}

async fn create_diagnostic_zip() -> Result<String, String> {
    let timestamp = chrono::Local::now().format("%Y%m%d_%H%M%S");
    let downloads_dir = dirs::download_dir().ok_or("Downloads folder not found")?;
    let zip_path = downloads_dir.join(format!("bbooster_diagnostic_{}.zip", timestamp));

    let file = fs::File::create(&zip_path).map_err(|e| e.to_string())?;
    let mut zip = zip::ZipWriter::new(file);
    let options = zip::write::FileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);

    // 시스템 정보
    let system_info = format!(
        "OS: {}\nArch: {}\nTimestamp: {}\n",
        std::env::consts::OS,
        std::env::consts::ARCH,
        chrono::Local::now().to_rfc3339()
    );
    zip.start_file("system_info.txt", options).map_err(|e| e.to_string())?;
    use std::io::Write;
    zip.write_all(system_info.as_bytes()).map_err(|e| e.to_string())?;

    // 서버 상태
    let server_status = get_server_status().await.unwrap_or(ServerStatus {
        running: false,
        estop: false,
        dry_run: false,
    });
    let status_json = serde_json::to_string_pretty(&server_status).unwrap_or_default();
    zip.start_file("server_status.json", options).map_err(|e| e.to_string())?;
    zip.write_all(status_json.as_bytes()).map_err(|e| e.to_string())?;

    // 로그 파일 (있는 경우)
    if let Ok(logs_path) = get_logs_path() {
        if let Ok(entries) = fs::read_dir(&logs_path) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_file() && path.extension().map_or(false, |e| e == "log") {
                    if let Ok(content) = fs::read_to_string(&path) {
                        let file_name = format!("logs/{}", path.file_name().unwrap().to_string_lossy());
                        let _ = zip.start_file(&file_name, options);
                        let _ = zip.write_all(content.as_bytes());
                    }
                }
            }
        }
    }

    zip.finish().map_err(|e| e.to_string())?;

    // zip 파일 위치 열기
    let _ = open::that(&downloads_dir);

    Ok(zip_path.to_string_lossy().to_string())
}

// =====================================================
// E-STOP
// =====================================================

#[tauri::command]
pub async fn set_estop(enabled: bool) -> Result<bool, String> {
    set_estop_api(enabled).await
}

pub async fn set_estop_api(enabled: bool) -> Result<bool, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!(
        "{}/api/system/estop?value={}",
        VPS_SERVER_URL,
        if enabled { "1" } else { "0" }
    );

    client
        .post(&url)
        .send()
        .await
        .map_err(|e| e.to_string())?;

    Ok(enabled)
}

// =====================================================
// Home Data
// =====================================================

#[tauri::command]
pub async fn get_home_data() -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let resp = client
        .get(format!("{}/api/diag/home", VPS_SERVER_URL))
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
        .map_err(|e| e.to_string())?;

    let data: serde_json::Value = resp.json().await.map_err(|e| e.to_string())?;
    Ok(data)
}

// =====================================================
// API Key Management (Secure Storage)
// =====================================================

#[tauri::command]
pub async fn save_api_key(exchange: String, key_type: String, value: String) -> Result<(), String> {
    let service = format!("bbooster_{}", exchange.to_lowercase());
    let entry = keyring::Entry::new(&service, &key_type).map_err(|e| e.to_string())?;
    entry.set_password(&value).map_err(|e| e.to_string())?;
    Ok(())
}

#[tauri::command]
pub async fn get_api_key(exchange: String, key_type: String) -> Result<String, String> {
    let service = format!("bbooster_{}", exchange.to_lowercase());
    let entry = keyring::Entry::new(&service, &key_type).map_err(|e| e.to_string())?;
    entry.get_password().map_err(|e| e.to_string())
}

// =====================================================
// Account Management (Full Account Keys)
// =====================================================

#[derive(Serialize, Deserialize, Clone)]
pub struct AccountKeys {
    pub api_key: String,
    pub api_secret: String,
    pub passphrase: Option<String>,
}

#[derive(Serialize, Deserialize, Clone)]
pub struct AccountInfo {
    pub id: Option<i64>,
    pub name: String,
    pub exchange: String,
    pub is_active: bool,
    pub has_keys: bool,
    pub last_health_check: Option<String>,
    pub health_status: Option<String>,
}

#[tauri::command]
pub async fn save_account_keys(
    account_name: String,
    exchange: String,
    keys: AccountKeys,
) -> Result<(), String> {
    let service = format!("bbooster-{}", exchange.to_lowercase());

    // Save API Key
    let key_entry = keyring::Entry::new(&service, &format!("{}_key", account_name))
        .map_err(|e| e.to_string())?;
    key_entry.set_password(&keys.api_key).map_err(|e| e.to_string())?;

    // Save API Secret
    let secret_entry = keyring::Entry::new(&service, &format!("{}_secret", account_name))
        .map_err(|e| e.to_string())?;
    secret_entry.set_password(&keys.api_secret).map_err(|e| e.to_string())?;

    // Save Passphrase (OKX only)
    if let Some(pass) = keys.passphrase {
        if !pass.is_empty() {
            let pass_entry = keyring::Entry::new(&service, &format!("{}_passphrase", account_name))
                .map_err(|e| e.to_string())?;
            pass_entry.set_password(&pass).map_err(|e| e.to_string())?;
        }
    }

    // Save account to local registry
    save_account_to_registry(&account_name, &exchange)?;

    Ok(())
}

#[tauri::command]
pub async fn get_account_keys(
    account_name: String,
    exchange: String,
) -> Result<AccountKeys, String> {
    let service = format!("bbooster-{}", exchange.to_lowercase());

    let key_entry = keyring::Entry::new(&service, &format!("{}_key", account_name))
        .map_err(|e| e.to_string())?;
    let secret_entry = keyring::Entry::new(&service, &format!("{}_secret", account_name))
        .map_err(|e| e.to_string())?;

    let api_key = key_entry.get_password().map_err(|e| e.to_string())?;
    let api_secret = secret_entry.get_password().map_err(|e| e.to_string())?;

    // Passphrase is optional
    let passphrase = keyring::Entry::new(&service, &format!("{}_passphrase", account_name))
        .ok()
        .and_then(|e| e.get_password().ok());

    Ok(AccountKeys {
        api_key,
        api_secret,
        passphrase,
    })
}

#[tauri::command]
pub async fn delete_account_keys(account_name: String, exchange: String) -> Result<(), String> {
    let service = format!("bbooster-{}", exchange.to_lowercase());

    // Delete all keys
    for suffix in ["key", "secret", "passphrase"] {
        if let Ok(entry) = keyring::Entry::new(&service, &format!("{}_{}", account_name, suffix)) {
            let _ = entry.delete_password();
        }
    }

    // Remove from local registry
    remove_account_from_registry(&account_name, &exchange)?;

    Ok(())
}

#[tauri::command]
pub async fn list_local_accounts() -> Result<Vec<AccountInfo>, String> {
    let accounts = load_account_registry()?;
    Ok(accounts)
}

#[tauri::command]
pub async fn fetch_server_accounts() -> Result<Vec<AccountInfo>, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let resp = client
        .get(format!("{}/api/accounts", VPS_SERVER_URL))
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await;

    match resp {
        Ok(r) => {
            if r.status().is_success() {
                let data: serde_json::Value = r.json().await.map_err(|e| e.to_string())?;
                let accounts_array = data.get("accounts").and_then(|a| a.as_array());

                if let Some(accounts) = accounts_array {
                    let result: Vec<AccountInfo> = accounts
                        .iter()
                        .filter_map(|a| {
                            Some(AccountInfo {
                                id: a.get("id").and_then(|v| v.as_i64()),
                                name: a.get("name").and_then(|v| v.as_str())?.to_string(),
                                exchange: a.get("exchange").and_then(|v| v.as_str())?.to_string(),
                                is_active: a.get("is_active").and_then(|v| v.as_bool()).unwrap_or(false),
                                has_keys: true,
                                last_health_check: a.get("last_health_check").and_then(|v| v.as_str()).map(String::from),
                                health_status: a.get("health_status").and_then(|v| v.as_str()).map(String::from),
                            })
                        })
                        .collect();
                    Ok(result)
                } else {
                    Ok(vec![])
                }
            } else {
                Ok(vec![])
            }
        }
        Err(_) => Ok(vec![]),
    }
}

#[tauri::command]
pub async fn test_account_connection(exchange: String, account_name: String) -> Result<String, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();

    // 거래소별 테스트 엔드포인트 매핑
    let endpoint = match exchange.to_uppercase().as_str() {
        "OKX" => format!("{}/api/accounts/test?exchange=okx&account={}", VPS_SERVER_URL, account_name),
        "BINANCE" => format!("{}/api/accounts/test?exchange=binance&account={}", VPS_SERVER_URL, account_name),
        "BYBIT" => format!("{}/api/accounts/test?exchange=bybit&account={}", VPS_SERVER_URL, account_name),
        "UPBIT" => format!("{}/api/accounts/test?exchange=upbit&account={}", VPS_SERVER_URL, account_name),
        "KIS_KR" | "KIS" => format!("{}/api/accounts/test?exchange=kis_kr&account={}", VPS_SERVER_URL, account_name),
        "KIS_US" => format!("{}/api/accounts/test?exchange=kis_us&account={}", VPS_SERVER_URL, account_name),
        _ => return Err(format!("지원하지 않는 거래소: {}", exchange)),
    };

    let resp = client
        .get(&endpoint)
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        Ok("연결 성공".to_string())
    } else {
        let error_text = resp.text().await.unwrap_or_default();
        Err(format!("연결 실패: {}", error_text))
    }
}

// Local account registry helpers
fn get_registry_path() -> Result<PathBuf, String> {
    let data_dir = dirs::data_dir().ok_or("Data directory not found")?;
    Ok(data_dir.join("BBooster").join("accounts.json"))
}

fn load_account_registry() -> Result<Vec<AccountInfo>, String> {
    let path = get_registry_path()?;
    if !path.exists() {
        return Ok(vec![]);
    }

    let content = fs::read_to_string(&path).map_err(|e| e.to_string())?;
    let accounts: Vec<AccountInfo> = serde_json::from_str(&content).unwrap_or_default();
    Ok(accounts)
}

fn save_account_registry(accounts: &[AccountInfo]) -> Result<(), String> {
    let path = get_registry_path()?;

    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }

    let content = serde_json::to_string_pretty(accounts).map_err(|e| e.to_string())?;
    fs::write(&path, content).map_err(|e| e.to_string())
}

fn save_account_to_registry(name: &str, exchange: &str) -> Result<(), String> {
    let mut accounts = load_account_registry()?;

    // Check if already exists
    let exists = accounts.iter().any(|a| a.name == name && a.exchange == exchange);
    if !exists {
        accounts.push(AccountInfo {
            id: None,
            name: name.to_string(),
            exchange: exchange.to_string(),
            is_active: true,
            has_keys: true,
            last_health_check: None,
            health_status: None,
        });
        save_account_registry(&accounts)?;
    }

    Ok(())
}

fn remove_account_from_registry(name: &str, exchange: &str) -> Result<(), String> {
    let mut accounts = load_account_registry()?;
    accounts.retain(|a| !(a.name == name && a.exchange == exchange));
    save_account_registry(&accounts)
}

// =====================================================
// API Key Registration (VPS 서버에 등록)
// =====================================================

#[derive(Serialize, Deserialize)]
pub struct RegisterApiKeyRequest {
    pub name: String,
    pub exchange: String,
    pub api_key: String,
    pub api_secret: String,
    pub api_passphrase: Option<String>,
    pub account_number: Option<String>,
}

#[derive(Serialize, Deserialize)]
pub struct RegisterApiKeyResponse {
    pub ok: bool,
    pub account_id: Option<i64>,
    pub message: String,
}

#[tauri::command]
pub async fn register_api_key(
    access_token: String,
    name: String,
    exchange: String,
    api_key: String,
    api_secret: String,
    api_passphrase: Option<String>,
    account_number: Option<String>,
) -> Result<RegisterApiKeyResponse, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/user/accounts", VPS_SERVER_URL);

    let body = serde_json::json!({
        "name": name,
        "exchange": exchange,
        "api_key": api_key,
        "api_secret": api_secret,
        "api_passphrase": api_passphrase,
        "account_number": account_number,
        "is_active": true
    });

    let resp = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .json(&body)
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        let account_id = data.get("id").and_then(|v| v.as_i64());

        // 로컬 레지스트리에도 저장
        let _ = save_account_to_registry(&name, &exchange);

        Ok(RegisterApiKeyResponse {
            ok: true,
            account_id,
            message: "API 키가 성공적으로 등록되었습니다".to_string(),
        })
    } else {
        let error_text = resp.text().await.unwrap_or_default();
        Err(format!("API 키 등록 실패: {}", error_text))
    }
}

#[tauri::command]
pub async fn delete_api_key(
    access_token: String,
    account_id: i64,
    account_name: String,
    exchange: String,
) -> Result<String, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/user/accounts/{}", VPS_SERVER_URL, account_id);

    let resp = client
        .delete(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        // 로컬 레지스트리에서도 삭제
        let _ = remove_account_from_registry(&account_name, &exchange);
        Ok("계정이 삭제되었습니다".to_string())
    } else {
        let error_text = resp.text().await.unwrap_or_default();
        Err(format!("계정 삭제 실패: {}", error_text))
    }
}

#[tauri::command]
pub async fn get_accounts_list(access_token: String) -> Result<Vec<AccountInfo>, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/user/accounts", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;

        // accounts 필드가 있으면 그것을 사용, 아니면 배열 직접 파싱
        let accounts_array = data.get("accounts")
            .and_then(|a| a.as_array())
            .or_else(|| data.as_array());

        if let Some(accounts) = accounts_array {
            let result: Vec<AccountInfo> = accounts
                .iter()
                .filter_map(|a| {
                    Some(AccountInfo {
                        id: a.get("id").and_then(|v| v.as_i64()),
                        name: a.get("name").and_then(|v| v.as_str())?.to_string(),
                        exchange: a.get("exchange").and_then(|v| v.as_str())?.to_string(),
                        is_active: a.get("is_active").and_then(|v| v.as_bool()).unwrap_or(false),
                        has_keys: true,
                        last_health_check: a.get("last_health_check").and_then(|v| v.as_str()).map(String::from),
                        health_status: a.get("health_status").and_then(|v| v.as_str()).map(String::from),
                    })
                })
                .collect();
            Ok(result)
        } else {
            Ok(vec![])
        }
    } else {
        Err("계정 목록을 가져올 수 없습니다".to_string())
    }
}

// =====================================================
// Timeline & Connector Status
// =====================================================

#[derive(Serialize, Deserialize)]
pub struct TimelineEvent {
    pub id: i64,
    pub timestamp: String,
    pub event_type: String,
    pub message: String,
    pub exchange: Option<String>,
    pub symbol: Option<String>,
}

#[tauri::command]
pub async fn fetch_timeline(limit: Option<i64>) -> Result<Vec<TimelineEvent>, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!(
        "{}/api/timeline?limit={}",
        VPS_SERVER_URL,
        limit.unwrap_or(50)
    );

    let resp = client
        .get(&url)
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
        .map_err(|e| e.to_string())?;

    let data: Vec<TimelineEvent> = resp.json().await.map_err(|e| e.to_string())?;
    Ok(data)
}

#[derive(Serialize, Deserialize)]
pub struct ConnectorStatus {
    pub exchange: String,
    pub connected: bool,
    pub last_ping: Option<String>,
    pub error: Option<String>,
}

#[tauri::command]
pub async fn fetch_connector_status() -> Result<Vec<ConnectorStatus>, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let resp = client
        .get(format!("{}/api/connectors/status", VPS_SERVER_URL))
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
        .map_err(|e| e.to_string())?;

    let data: Vec<ConnectorStatus> = resp.json().await.map_err(|e| e.to_string())?;
    Ok(data)
}

// =====================================================
// Subscription Info
// =====================================================

#[derive(Serialize, Deserialize)]
pub struct SubscriptionInfo {
    pub plan: String,
    pub status: String,
    pub expires_at: Option<String>,
    pub features: Vec<String>,
}

#[tauri::command]
pub async fn fetch_subscription() -> Result<SubscriptionInfo, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let resp = client
        .get(format!("{}/api/subscription", VPS_SERVER_URL))
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await;

    match resp {
        Ok(r) => {
            if r.status().is_success() {
                r.json().await.map_err(|e| e.to_string())
            } else {
                // Default free plan if endpoint not available
                Ok(SubscriptionInfo {
                    plan: "Free".to_string(),
                    status: "active".to_string(),
                    expires_at: None,
                    features: vec!["basic".to_string()],
                })
            }
        }
        Err(_) => {
            // Default free plan if server not running
            Ok(SubscriptionInfo {
                plan: "Free".to_string(),
                status: "active".to_string(),
                expires_at: None,
                features: vec!["basic".to_string()],
            })
        }
    }
}

// =====================================================
// Authentication Commands (VPS API 호출)
// =====================================================

#[derive(Serialize, Deserialize)]
pub struct AuthTokens {
    pub access_token: String,
    pub refresh_token: String,
    pub token_type: String,
    pub expires_in: i64,
}

#[derive(Serialize, Deserialize)]
pub struct UserInfo {
    pub id: i64,
    pub email: String,
    pub name: Option<String>,
    pub picture: Option<String>,
    pub role: String,
    pub plan: String,
    pub plan_expires_at: Option<String>,
    pub created_at: String,
}

#[derive(Serialize, Deserialize)]
pub struct AuthError {
    pub detail: String,
}

#[tauri::command]
pub async fn login_with_email(email: String, password: String) -> Result<AuthTokens, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/auth/login", VPS_SERVER_URL);

    let body = serde_json::json!({
        "email": email,
        "password": password
    });

    let resp = client
        .post(&url)
        .json(&body)
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let tokens: AuthTokens = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(tokens)
    } else {
        let error: AuthError = resp.json().await.unwrap_or(AuthError {
            detail: "로그인 실패".to_string(),
        });
        Err(error.detail)
    }
}

#[tauri::command]
pub async fn register_with_email(
    email: String,
    password: String,
    name: Option<String>,
) -> Result<AuthTokens, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/auth/register", VPS_SERVER_URL);

    let body = serde_json::json!({
        "email": email,
        "password": password,
        "name": name
    });

    let resp = client
        .post(&url)
        .json(&body)
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let tokens: AuthTokens = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(tokens)
    } else {
        let error: AuthError = resp.json().await.unwrap_or(AuthError {
            detail: "회원가입 실패".to_string(),
        });
        Err(error.detail)
    }
}

#[tauri::command]
pub async fn get_user_info(access_token: String) -> Result<UserInfo, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/auth/me", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let user: UserInfo = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(user)
    } else if resp.status().as_u16() == 401 {
        Err("토큰이 만료되었습니다".to_string())
    } else {
        Err("사용자 정보를 가져올 수 없습니다".to_string())
    }
}

#[tauri::command]
pub async fn refresh_auth_token(refresh_token: String) -> Result<AuthTokens, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/auth/refresh", VPS_SERVER_URL);

    let body = serde_json::json!({
        "refresh_token": refresh_token
    });

    let resp = client
        .post(&url)
        .json(&body)
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let tokens: AuthTokens = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(tokens)
    } else {
        Err("토큰 갱신 실패".to_string())
    }
}

// =====================================================
// Portfolio API (Home Page Data)
// =====================================================

#[derive(Serialize, Deserialize, Default)]
pub struct Allocation {
    pub domestic: i32,
    pub foreign: i32,
    pub crypto: i32,
    pub cash: i32,
    pub domestic_value: f64,
    pub foreign_value: f64,
    pub crypto_value: f64,
    pub cash_value: f64,
}

#[derive(Serialize, Deserialize)]
pub struct PortfolioSummary {
    pub total_assets: f64,
    pub total_assets_formatted: String,
    pub total_profit_rate: f64,
    pub daily_change: f64,
    pub daily_change_formatted: String,
    pub daily_change_rate: f64,
    pub active_strategies: i32,
    pub currency: String,
    #[serde(default)]
    pub allocation: Option<Allocation>,
}

#[tauri::command]
pub async fn get_portfolio_summary(access_token: String) -> Result<PortfolioSummary, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/portfolio/summary", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            // serde_json::Value로 파싱 후 수동 매핑 (추가 필드 무시)
            let data: serde_json::Value = r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;

            // allocation 파싱
            let allocation = if let Some(alloc) = data.get("allocation") {
                Some(Allocation {
                    domestic: alloc.get("domestic").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
                    foreign: alloc.get("foreign").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
                    crypto: alloc.get("crypto").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
                    cash: alloc.get("cash").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
                    domestic_value: alloc.get("domestic_value").and_then(|v| v.as_f64()).unwrap_or(0.0),
                    foreign_value: alloc.get("foreign_value").and_then(|v| v.as_f64()).unwrap_or(0.0),
                    crypto_value: alloc.get("crypto_value").and_then(|v| v.as_f64()).unwrap_or(0.0),
                    cash_value: alloc.get("cash_value").and_then(|v| v.as_f64()).unwrap_or(0.0),
                })
            } else {
                None
            };

            Ok(PortfolioSummary {
                total_assets: data.get("total_assets").and_then(|v| v.as_f64()).unwrap_or(0.0),
                total_assets_formatted: data.get("total_assets_formatted").and_then(|v| v.as_str()).unwrap_or("₩0").to_string(),
                total_profit_rate: data.get("total_profit_rate").and_then(|v| v.as_f64()).unwrap_or(0.0),
                daily_change: data.get("daily_change").and_then(|v| v.as_f64()).unwrap_or(0.0),
                daily_change_formatted: data.get("daily_change_formatted").and_then(|v| v.as_str()).unwrap_or("₩0").to_string(),
                daily_change_rate: data.get("daily_change_rate").and_then(|v| v.as_f64()).unwrap_or(0.0),
                active_strategies: data.get("active_strategies").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
                currency: data.get("currency").and_then(|v| v.as_str()).unwrap_or("KRW").to_string(),
                allocation,
            })
        }
        Ok(_) | Err(_) => {
            // 더미 데이터 반환 (API 미구현 시)
            Ok(PortfolioSummary {
                total_assets: 0.0,
                total_assets_formatted: "₩0".to_string(),
                total_profit_rate: 0.0,
                daily_change: 0.0,
                daily_change_formatted: "₩0".to_string(),
                daily_change_rate: 0.0,
                active_strategies: 0,
                currency: "KRW".to_string(),
                allocation: Some(Allocation {
                    domestic: 0, foreign: 0, crypto: 0, cash: 100,
                    domestic_value: 0.0, foreign_value: 0.0, crypto_value: 0.0, cash_value: 0.0,
                }),
            })
        }
    }
}

#[derive(Serialize, Deserialize)]
pub struct ChartDataPoint {
    pub date: String,
    pub value: f64,
}

#[derive(Serialize, Deserialize)]
pub struct PortfolioChart {
    pub period: String,
    pub data: Vec<ChartDataPoint>,
    pub period_profit_rate: f64,
}

#[tauri::command]
pub async fn get_portfolio_chart(access_token: String, period: String) -> Result<PortfolioChart, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/portfolio/chart?period={}", VPS_SERVER_URL, period);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
        }
        Ok(_) | Err(_) => {
            // 더미 데이터 반환
            let dummy_data = generate_dummy_chart_data(&period);
            Ok(PortfolioChart {
                period: period.clone(),
                data: dummy_data,
                period_profit_rate: 3.25,
            })
        }
    }
}

fn generate_dummy_chart_data(period: &str) -> Vec<ChartDataPoint> {
    let count = match period {
        "1d" => 24,
        "1w" => 7,
        "1m" => 30,
        "3m" => 90,
        "1y" => 365,
        _ => 7,
    };

    let mut data = Vec::new();
    let mut value: f64 = 0.0;
    let now = chrono::Local::now();

    for i in 0..count {
        let date = now - chrono::Duration::days((count - i - 1) as i64);
        value += (rand::random::<f64>() - 0.45) * 0.5;
        data.push(ChartDataPoint {
            date: date.format("%m/%d").to_string(),
            value: (value * 100.0).round() / 100.0,
        });
    }
    data
}

#[derive(Serialize, Deserialize)]
pub struct Holding {
    pub symbol: String,
    pub name: String,
    pub exchange: String,
    pub quantity: f64,
    pub avg_price: f64,
    pub current_price: f64,
    pub profit_loss: f64,
    pub profit_rate: f64,
    pub currency: String,
}

#[tauri::command]
pub async fn get_holdings(access_token: String) -> Result<Vec<Holding>, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/portfolio/holdings", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            let data: serde_json::Value = r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
            let holdings = data.get("holdings").and_then(|h| h.as_array());

            if let Some(arr) = holdings {
                let result: Vec<Holding> = arr.iter().filter_map(|h| {
                    Some(Holding {
                        symbol: h.get("symbol")?.as_str()?.to_string(),
                        name: h.get("name").and_then(|n| n.as_str()).unwrap_or("").to_string(),
                        exchange: h.get("exchange")?.as_str()?.to_string(),
                        quantity: h.get("quantity")?.as_f64()?,
                        avg_price: h.get("avg_price").and_then(|v| v.as_f64()).unwrap_or(0.0),
                        current_price: h.get("current_price").and_then(|v| v.as_f64()).unwrap_or(0.0),
                        profit_loss: h.get("profit_loss").and_then(|v| v.as_f64()).unwrap_or(0.0),
                        profit_rate: h.get("profit_rate").and_then(|v| v.as_f64()).unwrap_or(0.0),
                        currency: h.get("currency").and_then(|c| c.as_str()).unwrap_or("USD").to_string(),
                    })
                }).collect();
                Ok(result)
            } else {
                Ok(vec![])
            }
        }
        Ok(_) | Err(_) => Ok(vec![]), // 빈 배열 반환
    }
}

// =====================================================
// Day14: 환율 조회
// =====================================================
#[derive(Serialize, Deserialize)]
pub struct ExchangeRateResponse {
    pub usd_krw: f64,
    pub updated: String,
}

#[tauri::command]
pub async fn get_exchange_rate() -> Result<ExchangeRateResponse, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/exchange-rate", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
        }
        Ok(_) | Err(_) => {
            // 기본값 반환
            Ok(ExchangeRateResponse {
                usd_krw: 1450.0,
                updated: chrono::Local::now().format("%Y-%m-%d %H:%M").to_string(),
            })
        }
    }
}

// =====================================================
// Day14: 매매 내역 조회
// =====================================================
#[derive(Serialize, Deserialize)]
pub struct TradeItem {
    pub id: i64,
    pub exchange: String,
    pub symbol: String,
    pub side: String,
    pub quantity: f64,
    pub price: f64,
    pub total_amount: f64,
    pub currency: String,
    pub fee: f64,
    pub strategy_name: Option<String>,
    pub executed_at: Option<String>,
}

#[derive(Serialize, Deserialize)]
pub struct TradeHistoryResponse {
    pub trades: Vec<TradeItem>,
}

#[tauri::command]
pub async fn get_trade_history(
    access_token: String,
    exchange: Option<String>,
    symbol: Option<String>,
    limit: Option<i32>,
) -> Result<TradeHistoryResponse, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let mut url = format!("{}/api/trades?limit={}", VPS_SERVER_URL, limit.unwrap_or(50));
    if let Some(ex) = exchange {
        url.push_str(&format!("&exchange={}", ex));
    }
    if let Some(sym) = symbol {
        url.push_str(&format!("&symbol={}", sym));
    }

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
        }
        Ok(_) | Err(_) => Ok(TradeHistoryResponse { trades: vec![] }),
    }
}

// =====================================================
// Day14: 포트폴리오 히스토리 (수익률 추이)
// =====================================================
#[derive(Serialize, Deserialize)]
pub struct PortfolioHistoryItem {
    pub date: String,
    pub value: f64,
    pub return_pct: f64,
}

#[derive(Serialize, Deserialize)]
pub struct PortfolioHistoryResponse {
    pub data: Vec<PortfolioHistoryItem>,
    pub total_return: f64,
    pub period: String,
}

#[tauri::command]
pub async fn get_portfolio_history(
    access_token: String,
    period: String,
) -> Result<PortfolioHistoryResponse, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/portfolio/history?period={}", VPS_SERVER_URL, period);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
        }
        Ok(_) | Err(_) => {
            // 빈 데이터 반환
            Ok(PortfolioHistoryResponse {
                data: vec![],
                total_return: 0.0,
                period,
            })
        }
    }
}

#[derive(Serialize, Deserialize)]
pub struct ActiveStrategy {
    pub id: i64,
    pub name: String,
    pub symbol: String,
    pub exchange: String,
    pub status: String,
    pub trades_today: i32,
}

#[tauri::command]
pub async fn get_active_strategies(access_token: String) -> Result<Vec<ActiveStrategy>, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/strategies/active", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            let data: serde_json::Value = r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
            let strategies = data.get("strategies").and_then(|s| s.as_array());

            if let Some(arr) = strategies {
                let result: Vec<ActiveStrategy> = arr.iter().filter_map(|s| {
                    Some(ActiveStrategy {
                        id: s.get("id")?.as_i64()?,
                        name: s.get("name")?.as_str()?.to_string(),
                        symbol: s.get("symbol")?.as_str()?.to_string(),
                        exchange: s.get("exchange")?.as_str()?.to_string(),
                        status: s.get("status").and_then(|st| st.as_str()).unwrap_or("running").to_string(),
                        trades_today: s.get("trades_today").and_then(|t| t.as_i64()).unwrap_or(0) as i32,
                    })
                }).collect();
                Ok(result)
            } else {
                Ok(vec![])
            }
        }
        Ok(_) | Err(_) => Ok(vec![]), // 빈 배열 반환
    }
}

#[tauri::command]
pub async fn emergency_stop(access_token: String) -> Result<bool, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/system/emergency-stop", VPS_SERVER_URL);

    let resp = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        Ok(true)
    } else {
        // fallback: 기존 estop API 사용
        set_estop_api(true).await
    }
}

// =====================================================
// Webhook Logs (PHASE 4)
// =====================================================

#[derive(Serialize, Deserialize)]
pub struct WebhookLogItem {
    pub id: i64,
    pub received_at: String,
    pub status: String,
    pub exchange: String,
    pub symbol: String,
    pub action: String,
    pub error_message: Option<String>,
}

#[tauri::command]
pub async fn get_webhook_logs(access_token: String, limit: Option<i32>) -> Result<Vec<WebhookLogItem>, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/webhook/logs?limit={}", VPS_SERVER_URL, limit.unwrap_or(20));

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            let data: serde_json::Value = r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
            let logs = data.get("logs").and_then(|l| l.as_array());

            if let Some(arr) = logs {
                let result: Vec<WebhookLogItem> = arr.iter().filter_map(|l| {
                    Some(WebhookLogItem {
                        id: l.get("id")?.as_i64()?,
                        received_at: l.get("received_at")?.as_str()?.to_string(),
                        status: l.get("status")?.as_str()?.to_string(),
                        exchange: l.get("exchange").and_then(|e| e.as_str()).unwrap_or("").to_string(),
                        symbol: l.get("symbol").and_then(|s| s.as_str()).unwrap_or("").to_string(),
                        action: l.get("action").and_then(|a| a.as_str()).unwrap_or("").to_string(),
                        error_message: l.get("error_message").and_then(|e| e.as_str()).map(String::from),
                    })
                }).collect();
                Ok(result)
            } else {
                Ok(vec![])
            }
        }
        Ok(_) | Err(_) => Ok(vec![]),
    }
}

#[derive(Serialize, Deserialize)]
pub struct WebhookUrlInfo {
    pub webhook_url: String,
    pub user_id: i64,
}

#[tauri::command]
pub async fn get_webhook_url(access_token: String) -> Result<WebhookUrlInfo, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/webhook/url", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(WebhookUrlInfo {
            webhook_url: data.get("webhook_url").and_then(|u| u.as_str()).unwrap_or("").to_string(),
            user_id: data.get("user_id").and_then(|u| u.as_i64()).unwrap_or(0),
        })
    } else {
        Err("웹훅 URL을 가져올 수 없습니다".to_string())
    }
}

// =====================================================
// Symbols API (PHASE 5)
// =====================================================

#[derive(Serialize, Deserialize)]
pub struct SymbolInfo {
    pub symbol: String,
    pub name: String,
    pub exchange: String,
    pub price: f64,
    pub price_formatted: String,
    pub change: f64,
    pub change_formatted: String,
    pub volume: i64,
    pub volume_formatted: String,
    pub high_24h: Option<f64>,
    pub low_24h: Option<f64>,
}

#[tauri::command]
pub async fn search_symbols(
    access_token: String,
    query: String,
    exchange: Option<String>,
) -> Result<Vec<SymbolInfo>, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let mut url = format!("{}/api/symbols/search?q={}", VPS_SERVER_URL, query);
    if let Some(ex) = exchange {
        url = format!("{}&exchange={}", url, ex);
    }

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            let data: serde_json::Value = r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
            let symbols = data.get("symbols").and_then(|s| s.as_array());

            if let Some(arr) = symbols {
                let result: Vec<SymbolInfo> = arr.iter().filter_map(|s| {
                    // symbol은 필수, 나머지는 기본값 사용
                    let symbol = s.get("symbol")?.as_str()?.to_string();
                    Some(SymbolInfo {
                        symbol: symbol.clone(),
                        name: s.get("name").and_then(|n| n.as_str()).unwrap_or(&symbol).to_string(),
                        exchange: s.get("exchange").and_then(|e| e.as_str()).unwrap_or("").to_string(),
                        price: s.get("price").and_then(|p| p.as_f64()).unwrap_or(0.0),
                        price_formatted: s.get("price_formatted").and_then(|p| p.as_str()).unwrap_or("N/A").to_string(),
                        change: s.get("change").and_then(|c| c.as_f64()).unwrap_or(0.0),
                        change_formatted: s.get("change_formatted").and_then(|c| c.as_str()).unwrap_or("0.00%").to_string(),
                        volume: s.get("volume").and_then(|v| v.as_f64()).map(|v| v as i64).unwrap_or(0),
                        volume_formatted: s.get("volume_formatted").and_then(|v| v.as_str()).unwrap_or("0").to_string(),
                        high_24h: s.get("high_24h").and_then(|h| h.as_f64()),
                        low_24h: s.get("low_24h").and_then(|l| l.as_f64()),
                    })
                }).collect();
                Ok(result)
            } else {
                Ok(vec![])
            }
        }
        Ok(_) | Err(_) => Ok(vec![]),
    }
}

/// 심볼 상세 정보 (미니 종목보고서) — JSON 전달
#[tauri::command]
pub async fn get_symbol_detail(
    access_token: String,
    symbol: String,
    exchange: String,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/symbols/{}/{}", VPS_SERVER_URL, exchange, symbol);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(data)
    } else {
        Err("심볼 정보를 가져올 수 없습니다".to_string())
    }
}

// =====================================================
// Stock Detail Renewal APIs (Phase 2)
// =====================================================

/// 종목 재무 요약 (요약 탭)
#[tauri::command]
pub async fn get_stock_financial_summary(
    access_token: String,
    code: String,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/stock/{}/financial-summary", VPS_SERVER_URL, code);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(data)
    } else {
        Err("재무 요약 정보를 가져올 수 없습니다".to_string())
    }
}

/// 종목 실적 추이 (재무 탭)
#[tauri::command]
pub async fn get_stock_financial_trend(
    access_token: String,
    code: String,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/stock/{}/financial-trend", VPS_SERVER_URL, code);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(data)
    } else {
        Err("실적 추이 정보를 가져올 수 없습니다".to_string())
    }
}

/// 기업 정보 (기업 탭)
#[tauri::command]
pub async fn get_stock_company(
    access_token: String,
    code: String,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/stock/{}/company", VPS_SERVER_URL, code);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(data)
    } else {
        Err("기업 정보를 가져올 수 없습니다".to_string())
    }
}

/// 재무제표 상세 (재무 탭)
#[tauri::command]
pub async fn get_stock_financial_statement(
    access_token: String,
    code: String,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/stock/{}/financial-statement", VPS_SERVER_URL, code);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(data)
    } else {
        Err("재무제표 정보를 가져올 수 없습니다".to_string())
    }
}

/// 종목 뉴스 (소식 탭)
#[tauri::command]
pub async fn get_stock_news(
    access_token: String,
    code: String,
    limit: Option<i32>,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let limit_val = limit.unwrap_or(20);
    let url = format!("{}/api/stock/{}/news?limit={}", VPS_SERVER_URL, code, limit_val);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(data)
    } else {
        Err("뉴스 정보를 가져올 수 없습니다".to_string())
    }
}

/// 공시 정보 (소식 탭)
#[tauri::command]
pub async fn get_stock_disclosures(
    access_token: String,
    code: String,
    limit: Option<i32>,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let limit_val = limit.unwrap_or(20);
    let url = format!("{}/api/stock/{}/disclosures?limit={}", VPS_SERVER_URL, code, limit_val);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(data)
    } else {
        Err("공시 정보를 가져올 수 없습니다".to_string())
    }
}

/// 투자의견/컨센서스 (요약 탭)
#[tauri::command]
pub async fn get_stock_consensus(
    access_token: String,
    code: String,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/stock/{}/consensus", VPS_SERVER_URL, code);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(data)
    } else {
        Err("컨센서스 정보를 가져올 수 없습니다".to_string())
    }
}

/// 각 거래소별 인기 종목 목록
#[derive(Serialize, Deserialize, Default)]
pub struct PopularSymbols {
    #[serde(default)]
    pub okx: Vec<SymbolInfo>,
    #[serde(default)]
    pub binance: Vec<SymbolInfo>,
    #[serde(default)]
    pub bybit: Vec<SymbolInfo>,
    #[serde(default)]
    pub upbit: Vec<SymbolInfo>,
    #[serde(default)]
    pub kis_kr: Vec<SymbolInfo>,
    #[serde(default)]
    pub kis_kr_etf: Vec<SymbolInfo>,
    #[serde(default)]
    pub kis_us: Vec<SymbolInfo>,
    #[serde(default)]
    pub kis_us_etf: Vec<SymbolInfo>,
}

fn parse_symbol_list(data: &serde_json::Value, key: &str) -> Vec<SymbolInfo> {
    data.get(key)
        .and_then(|arr| arr.as_array())
        .map(|arr| arr.iter().filter_map(|s| {
            Some(SymbolInfo {
                symbol: s.get("symbol")?.as_str()?.to_string(),
                name: s.get("name").and_then(|n| n.as_str()).unwrap_or("").to_string(),
                exchange: s.get("exchange").and_then(|e| e.as_str()).unwrap_or("").to_string(),
                price: s.get("price").and_then(|p| p.as_f64()).unwrap_or(0.0),
                price_formatted: s.get("price_formatted").and_then(|p| p.as_str()).unwrap_or("N/A").to_string(),
                change: s.get("change").and_then(|c| c.as_f64()).unwrap_or(0.0),
                change_formatted: s.get("change_formatted").and_then(|c| c.as_str()).unwrap_or("0.00%").to_string(),
                volume: s.get("volume").and_then(|v| v.as_f64()).map(|v| v as i64).unwrap_or(0),
                volume_formatted: s.get("volume_formatted").and_then(|v| v.as_str()).unwrap_or("0").to_string(),
                high_24h: s.get("high_24h").and_then(|h| h.as_f64()),
                low_24h: s.get("low_24h").and_then(|l| l.as_f64()),
            })
        }).collect())
        .unwrap_or_default()
}

#[tauri::command]
pub async fn get_popular_symbols(
    access_token: String,
    exchange: Option<String>,
) -> Result<PopularSymbols, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();

    // exchange 파라미터가 있으면 쿼리 추가
    let url = match &exchange {
        Some(ex) => format!("{}/api/symbols/popular?exchange={}", VPS_SERVER_URL, ex),
        None => format!("{}/api/symbols/popular", VPS_SERVER_URL),
    };

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            let data: serde_json::Value = r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;

            Ok(PopularSymbols {
                okx: parse_symbol_list(&data, "okx"),
                binance: parse_symbol_list(&data, "binance"),
                bybit: parse_symbol_list(&data, "bybit"),
                upbit: parse_symbol_list(&data, "upbit"),
                kis_kr: parse_symbol_list(&data, "kis_kr"),
                kis_kr_etf: parse_symbol_list(&data, "kis_kr_etf"),
                kis_us: parse_symbol_list(&data, "kis_us"),
                kis_us_etf: parse_symbol_list(&data, "kis_us_etf"),
            })
        }
        Ok(_) | Err(_) => Ok(PopularSymbols::default()),
    }
}

// =====================================================
// Backtest API (PHASE 6)
// =====================================================

#[derive(Serialize, Deserialize)]
pub struct BacktestSummary {
    pub total_return: f64,
    pub cagr: f64,
    pub max_drawdown: f64,
    pub sharpe_ratio: f64,
    pub win_rate: f64,
    pub total_trades: i32,
    pub avg_win: f64,
    pub avg_loss: f64,
}

#[derive(Serialize, Deserialize)]
pub struct EquityCurvePoint {
    pub date: String,
    pub equity: f64,
}

#[derive(Serialize, Deserialize)]
pub struct TradeRecord {
    pub date: String,
    #[serde(rename = "type")]
    pub trade_type: String,
    pub price: f64,
    pub qty: f64,
    pub pnl: Option<f64>,
}

#[derive(Serialize, Deserialize)]
pub struct BacktestResult {
    pub summary: serde_json::Value,
    pub equity_curve: Vec<EquityCurvePoint>,
    pub trades: Vec<TradeRecord>,
}

#[tauri::command]
pub async fn run_backtest(
    access_token: String,
    strategy_type: String,
    exchange: String,
    symbol: String,
    start_date: String,
    end_date: String,
    initial_capital: f64,
    params: serde_json::Value,
    order_settings: serde_json::Value,
) -> Result<BacktestResult, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/backtest", VPS_SERVER_URL);

    let body = serde_json::json!({
        "strategy_type": strategy_type,
        "exchange": exchange,
        "symbol": symbol,
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital,
        "params": params,
        "order_settings": order_settings
    });

    let resp = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .json(&body)
        .timeout(std::time::Duration::from_secs(60))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: BacktestResult = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(data)
    } else {
        let error_text = resp.text().await.unwrap_or_default();
        Err(format!("백테스팅 실패: {}", error_text))
    }
}

#[derive(Serialize, Deserialize)]
pub struct StrategyItem {
    pub id: i64,
    pub name: String,
    pub strategy_type: String,
    pub exchange: String,
    pub symbol: String,
    pub is_active: bool,
    pub params: serde_json::Value,
    pub order_settings: serde_json::Value,
    pub created_at: String,
}

#[tauri::command]
pub async fn save_strategy(
    access_token: String,
    name: String,
    strategy_type: String,
    exchange: String,
    symbol: String,
    params: serde_json::Value,
    order_settings: serde_json::Value,
    is_active: bool,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/strategies", VPS_SERVER_URL);

    let body = serde_json::json!({
        "name": name,
        "strategy_type": strategy_type,
        "exchange": exchange,
        "symbol": symbol,
        "params": params,
        "order_settings": order_settings,
        "is_active": is_active
    });

    let resp = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .json(&body)
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(data)
    } else {
        let error_text = resp.text().await.unwrap_or_default();
        Err(format!("전략 저장 실패: {}", error_text))
    }
}

#[tauri::command]
pub async fn get_strategies(access_token: String) -> Result<Vec<StrategyItem>, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/strategies", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            let data: serde_json::Value = r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
            let strategies = data.get("strategies").and_then(|s| s.as_array());

            if let Some(arr) = strategies {
                let result: Vec<StrategyItem> = arr.iter().filter_map(|s| {
                    Some(StrategyItem {
                        id: s.get("id")?.as_i64()?,
                        name: s.get("name")?.as_str()?.to_string(),
                        strategy_type: s.get("strategy_type")?.as_str()?.to_string(),
                        exchange: s.get("exchange")?.as_str()?.to_string(),
                        symbol: s.get("symbol")?.as_str()?.to_string(),
                        is_active: s.get("is_active").and_then(|a| a.as_bool()).unwrap_or(false),
                        params: s.get("params").cloned().unwrap_or(serde_json::json!({})),
                        order_settings: s.get("order_settings").cloned().unwrap_or(serde_json::json!({})),
                        created_at: s.get("created_at").and_then(|c| c.as_str()).unwrap_or("").to_string(),
                    })
                }).collect();
                Ok(result)
            } else {
                Ok(vec![])
            }
        }
        Ok(_) | Err(_) => Ok(vec![]),
    }
}

#[tauri::command]
pub async fn toggle_strategy(access_token: String, strategy_id: i64) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/strategies/{}/toggle", VPS_SERVER_URL, strategy_id);

    let resp = client
        .put(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(data)
    } else {
        Err("전략 토글 실패".to_string())
    }
}

#[tauri::command]
pub async fn delete_strategy(access_token: String, strategy_id: i64) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/strategies/{}", VPS_SERVER_URL, strategy_id);

    let resp = client
        .delete(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(data)
    } else {
        Err("전략 삭제 실패".to_string())
    }
}

// =====================================================
// Password Verification
// =====================================================

#[tauri::command]
pub async fn verify_password(access_token: String, password: String) -> Result<bool, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/auth/verify-password", VPS_SERVER_URL);

    let body = serde_json::json!({ "password": password });

    let resp = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .json(&body)
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        // 응답에서 verified 필드 파싱
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        let verified = data.get("verified").and_then(|v| v.as_bool()).unwrap_or(false);
        Ok(verified)
    } else {
        Ok(false)
    }
}

// =====================================================
// Admin API (PHASE 7)
// =====================================================

#[derive(Serialize, Deserialize)]
pub struct AdminUser {
    pub id: i64,
    pub email: String,
    pub name: Option<String>,
    pub role: String,
    pub plan: String,
    pub created_at: Option<String>,
    pub last_login_at: Option<String>,
    pub is_active: bool,
}

#[tauri::command]
pub async fn admin_get_users(
    access_token: String,
    search: Option<String>,
    plan_filter: Option<String>,
) -> Result<Vec<AdminUser>, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let mut url = format!("{}/api/admin/users?", VPS_SERVER_URL);
    if let Some(s) = search {
        url = format!("{}search={}&", url, s);
    }
    if let Some(p) = plan_filter {
        url = format!("{}plan_filter={}&", url, p);
    }

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            let data: serde_json::Value = r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
            let users = data.get("users").and_then(|u| u.as_array());

            if let Some(arr) = users {
                let result: Vec<AdminUser> = arr.iter().filter_map(|u| {
                    Some(AdminUser {
                        id: u.get("id")?.as_i64()?,
                        email: u.get("email")?.as_str()?.to_string(),
                        name: u.get("name").and_then(|n| n.as_str()).map(String::from),
                        role: u.get("role")?.as_str()?.to_string(),
                        plan: u.get("plan")?.as_str()?.to_string(),
                        created_at: u.get("created_at").and_then(|c| c.as_str()).map(String::from),
                        last_login_at: u.get("last_login_at").and_then(|l| l.as_str()).map(String::from),
                        is_active: u.get("is_active").and_then(|a| a.as_bool()).unwrap_or(true),
                    })
                }).collect();
                Ok(result)
            } else {
                Ok(vec![])
            }
        }
        Ok(_) => Err("권한이 없습니다".to_string()),
        Err(e) => Err(format!("네트워크 오류: {}", e)),
    }
}

#[tauri::command]
pub async fn admin_update_user_plan(
    access_token: String,
    user_id: i64,
    plan: String,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/admin/users/{}/plan", VPS_SERVER_URL, user_id);

    let body = serde_json::json!({ "plan": plan });

    let resp = client
        .put(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .json(&body)
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        let data: serde_json::Value = resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
        Ok(data)
    } else {
        Err("요금제 변경 실패".to_string())
    }
}

#[derive(Serialize, Deserialize)]
pub struct SystemStatus {
    pub status: String,
    pub memory_percent: f64,
    pub db_connected: bool,
    pub platform: String,
    pub webhook_total: i64,
    pub webhook_success: i64,
    pub webhook_failed: i64,
}

#[tauri::command]
pub async fn admin_get_system_status(access_token: String) -> Result<SystemStatus, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/admin/system", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            let data: serde_json::Value = r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))?;
            let stats = data.get("webhook_stats").cloned().unwrap_or(serde_json::json!({}));

            Ok(SystemStatus {
                status: data.get("status").and_then(|s| s.as_str()).unwrap_or("unknown").to_string(),
                memory_percent: data.get("memory_percent").and_then(|m| m.as_f64()).unwrap_or(0.0),
                db_connected: data.get("db_connected").and_then(|d| d.as_bool()).unwrap_or(false),
                platform: data.get("platform").and_then(|p| p.as_str()).unwrap_or("").to_string(),
                webhook_total: stats.get("total").and_then(|t| t.as_i64()).unwrap_or(0),
                webhook_success: stats.get("success").and_then(|s| s.as_i64()).unwrap_or(0),
                webhook_failed: stats.get("failed").and_then(|f| f.as_i64()).unwrap_or(0),
            })
        }
        Ok(_) => Err("권한이 없습니다".to_string()),
        Err(e) => Err(format!("네트워크 오류: {}", e)),
    }
}

// Admin Stats (관리자 대시보드 통계)
#[tauri::command]
pub async fn admin_get_stats(access_token: String) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/admin/stats", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
        }
        Ok(_) => Err("권한이 없습니다".to_string()),
        Err(e) => Err(format!("네트워크 오류: {}", e)),
    }
}

#[tauri::command]
pub async fn admin_get_recent_users(access_token: String) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/admin/recent-users", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await;

    match resp {
        Ok(r) if r.status().is_success() => {
            r.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
        }
        Ok(_) => Err("권한이 없습니다".to_string()),
        Err(e) => Err(format!("네트워크 오류: {}", e)),
    }
}

// =====================================================
// Market Analysis (STEP 2)
// =====================================================

#[tauri::command]
pub async fn get_market_overview(access_token: String) -> Result<serde_json::Value, String> {
    // [DEBUG] 토큰 상태 로그
    let token_preview = if access_token.len() > 20 {
        format!("{}...", &access_token[..20])
    } else if access_token.is_empty() {
        "EMPTY".to_string()
    } else {
        access_token.clone()
    };
    println!("[Rust DEBUG] get_market_overview: token={}", token_preview);

    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/market/overview", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else if resp.status().as_u16() == 401 {
        Err("로그인이 필요합니다".to_string())
    } else if resp.status().as_u16() == 403 {
        Err("Pro 이상 요금제에서 이용 가능합니다".to_string())
    } else {
        let status = resp.status().as_u16();
        Err(format!("시장 현황을 가져올 수 없습니다 ({})", status))
    }
}

#[tauri::command]
pub async fn get_market_us_overview(access_token: String) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/market/us/overview", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else if resp.status().as_u16() == 401 {
        Err("로그인이 필요합니다".to_string())
    } else if resp.status().as_u16() == 403 {
        Err("Pro 이상 요금제에서 이용 가능합니다".to_string())
    } else {
        Err("해외 시장 데이터를 가져올 수 없습니다".to_string())
    }
}

#[tauri::command]
pub async fn get_market_sectors(access_token: String) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/market/sectors", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else if resp.status().as_u16() == 403 {
        Err("Pro 이상 요금제에서 이용 가능합니다".to_string())
    } else {
        Err("업종 현황을 가져올 수 없습니다".to_string())
    }
}

#[tauri::command]
pub async fn get_stock_ranking(
    access_token: String,
    ranking_type: String,
    market: String,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!(
        "{}/api/market/ranking?ranking_type={}&market={}",
        VPS_SERVER_URL, ranking_type, market
    );

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else if resp.status().as_u16() == 403 {
        Err("Pro 이상 요금제에서 이용 가능합니다".to_string())
    } else {
        Err("종목 순위를 가져올 수 없습니다".to_string())
    }
}

#[tauri::command]
pub async fn get_featured_stocks(access_token: String) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/market/featured", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else if resp.status().as_u16() == 403 {
        Err("Pro 이상 요금제에서 이용 가능합니다".to_string())
    } else {
        Err("특징주를 가져올 수 없습니다".to_string())
    }
}

#[tauri::command]
pub async fn get_market_events(
    access_token: String,
    event_type: String,
    month: Option<String>,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let mut url = format!("{}/api/market/events?event_type={}", VPS_SERVER_URL, event_type);
    if let Some(m) = month {
        url.push_str(&format!("&month={}", m));
    }

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else if resp.status().as_u16() == 403 {
        Err("Pro 이상 요금제에서 이용 가능합니다".to_string())
    } else {
        Err("이벤트 일정을 가져올 수 없습니다".to_string())
    }
}

// =====================================================
// AI Analysis + Watchlist (STEP 3)
// =====================================================

#[tauri::command]
pub async fn get_ai_usage(access_token: String) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/ai/usage", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else {
        Err("AI 사용량 조회 실패".to_string())
    }
}

#[tauri::command]
pub async fn request_ai_analysis(
    access_token: String,
    symbol: String,
    exchange: String,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/ai/analyze", VPS_SERVER_URL);

    let body = serde_json::json!({
        "symbol": symbol,
        "exchange": exchange
    });

    let resp = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .header("Content-Type", "application/json")
        .json(&body)
        .timeout(std::time::Duration::from_secs(60))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else if resp.status().as_u16() == 403 {
        Err("AI 종합분석은 Standard 이상에서 이용 가능합니다".to_string())
    } else {
        Err("AI 분석 요청 실패".to_string())
    }
}

#[tauri::command]
pub async fn get_market_timeline(access_token: String) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/market/timeline", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else {
        Err("시황 타임라인 조회 실패".to_string())
    }
}

#[tauri::command]
pub async fn get_watchlist_groups(access_token: String) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/watchlist/groups", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else {
        Err("관심종목 그룹 조회 실패".to_string())
    }
}

#[tauri::command]
pub async fn create_watchlist_group(
    access_token: String,
    name: String,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/watchlist/groups", VPS_SERVER_URL);

    let body = serde_json::json!({ "name": name });

    let resp = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .header("Content-Type", "application/json")
        .json(&body)
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else {
        Err("그룹 생성 실패".to_string())
    }
}

#[tauri::command]
pub async fn delete_watchlist_group(
    access_token: String,
    group_id: i64,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/watchlist/groups/{}", VPS_SERVER_URL, group_id);

    let resp = client
        .delete(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else {
        Err("그룹 삭제 실패".to_string())
    }
}

#[tauri::command]
pub async fn get_watchlist_items(
    access_token: String,
    group_id: i64,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/watchlist/groups/{}/items", VPS_SERVER_URL, group_id);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else {
        Err("관심종목 조회 실패".to_string())
    }
}

#[tauri::command]
pub async fn add_watchlist_item(
    access_token: String,
    group_id: i64,
    symbol: String,
    exchange: String,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/watchlist/items", VPS_SERVER_URL);

    let body = serde_json::json!({
        "group_id": group_id,
        "symbol": symbol,
        "exchange": exchange
    });

    let resp = client
        .post(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .header("Content-Type", "application/json")
        .json(&body)
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else if resp.status().as_u16() == 400 {
        let err: serde_json::Value = resp.json().await.unwrap_or_default();
        Err(err.get("detail").and_then(|d| d.as_str()).unwrap_or("추가 실패").to_string())
    } else {
        Err("관심종목 추가 실패".to_string())
    }
}

#[tauri::command]
pub async fn remove_watchlist_item(
    access_token: String,
    item_id: i64,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/watchlist/items/{}", VPS_SERVER_URL, item_id);

    let resp = client
        .delete(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else {
        Err("관심종목 삭제 실패".to_string())
    }
}

// =====================================================
// [BUG FIX 3] 시장분석 개선 API
// =====================================================

#[tauri::command]
pub async fn get_market_etf(
    access_token: String,
    sector: Option<String>,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let sector_param = sector.unwrap_or_else(|| "all".to_string());
    let url = format!("{}/api/market/etf?sector={}", VPS_SERVER_URL, sector_param);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else {
        Err("ETF 데이터 조회 실패".to_string())
    }
}

#[tauri::command]
pub async fn get_market_crypto(
    access_token: String,
    exchange: Option<String>,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let exchange_param = exchange.unwrap_or_else(|| "all".to_string());
    let url = format!("{}/api/market/crypto?exchange={}", VPS_SERVER_URL, exchange_param);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else {
        Err("코인 데이터 조회 실패".to_string())
    }
}

#[tauri::command]
pub async fn get_analysis_rs(
    access_token: String,
    market: Option<String>,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let market_param = market.unwrap_or_else(|| "all".to_string());
    let url = format!("{}/api/analysis/rs?market={}", VPS_SERVER_URL, market_param);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else {
        Err("RS 데이터 조회 실패".to_string())
    }
}

#[tauri::command]
pub async fn get_analysis_new_high(access_token: String) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let url = format!("{}/api/analysis/new-high", VPS_SERVER_URL);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else {
        Err("52주 신고가 데이터 조회 실패".to_string())
    }
}

#[tauri::command]
pub async fn get_analysis_valuation(
    access_token: String,
    market: Option<String>,
) -> Result<serde_json::Value, String> {
    let client = reqwest::Client::builder().danger_accept_invalid_certs(true).build().unwrap();
    let market_param = market.unwrap_or_else(|| "all".to_string());
    let url = format!("{}/api/analysis/valuation?market={}", VPS_SERVER_URL, market_param);

    let resp = client
        .get(&url)
        .header("Authorization", format!("Bearer {}", access_token))
        .timeout(std::time::Duration::from_secs(15))
        .send()
        .await
        .map_err(|e| format!("네트워크 오류: {}", e))?;

    if resp.status().is_success() {
        resp.json().await.map_err(|e| format!("응답 파싱 오류: {}", e))
    } else {
        Err("밸류에이션 데이터 조회 실패".to_string())
    }
}

// =====================================================
// Helper Functions
// =====================================================

fn find_python() -> Option<String> {
    // Windows
    #[cfg(target_os = "windows")]
    {
        // 1. PATH에서 찾기
        if let Ok(output) = Command::new("where")
            .arg("python")
            .creation_flags(CREATE_NO_WINDOW)
            .output()
        {
            if output.status.success() {
                if let Ok(path) = String::from_utf8(output.stdout) {
                    return Some(path.lines().next()?.trim().to_string());
                }
            }
        }
        // 2. 기본 경로
        let paths = [
            "python",
            "python3",
            r"C:\Python313\python.exe",
            r"C:\Python312\python.exe",
            r"C:\Python311\python.exe",
        ];
        for path in paths {
            if Command::new(path)
                .arg("--version")
                .creation_flags(CREATE_NO_WINDOW)
                .output()
                .is_ok()
            {
                return Some(path.to_string());
            }
        }
    }

    // Unix
    #[cfg(not(target_os = "windows"))]
    {
        let paths = ["python3", "python"];
        for path in paths {
            if Command::new(path).arg("--version").output().is_ok() {
                return Some(path.to_string());
            }
        }
    }

    None
}

fn get_server_path() -> Result<PathBuf, String> {
    // 개발 시: autobot 폴더
    // 배포 시: 앱과 함께 번들된 서버 경로
    let dev_path = PathBuf::from(r"C:\autobot");
    if dev_path.exists() {
        return Ok(dev_path);
    }

    // 실행 파일 위치 기준
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(parent) = exe_path.parent() {
            let server_path = parent.join("server");
            if server_path.exists() {
                return Ok(server_path);
            }
        }
    }

    Err("Server path not found".to_string())
}

fn get_logs_path() -> Result<PathBuf, String> {
    let data_dir = dirs::data_dir().ok_or("Data directory not found")?;
    Ok(data_dir.join("BBooster").join("logs"))
}
