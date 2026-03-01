// =====================================================
// BBooster Tauri Commands (Native Functions Only)
// HTTP API calls are handled directly by frontend via fetch
// =====================================================

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tauri::AppHandle;

const VPS_SERVER_URL: &str = "http://76.13.180.30";

// =====================================================
// Server Management (VPS 연결 - 트레이 메뉴용)
// =====================================================

#[tauri::command]
pub async fn start_server() -> Result<String, String> {
    let client = reqwest::Client::builder()
        .danger_accept_invalid_certs(true)
        .build()
        .unwrap();
    match client
        .get(format!("{}/api/diag/home", VPS_SERVER_URL))
        .timeout(std::time::Duration::from_secs(5))
        .send()
        .await
    {
        Ok(resp) if resp.status().is_success() => Ok("VPS 서버 연결됨".to_string()),
        Ok(_) => Err("VPS 서버 응답 오류".to_string()),
        Err(e) => Err(format!("VPS 서버 연결 실패: {}", e)),
    }
}

pub async fn start_server_internal(_app: &AppHandle) -> Result<String, String> {
    start_server().await
}

#[tauri::command]
pub async fn stop_server() -> Result<String, String> {
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
    let client = reqwest::Client::builder()
        .danger_accept_invalid_certs(true)
        .build()
        .unwrap();
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

#[derive(Serialize, Deserialize)]
pub struct ServerStatus {
    pub running: bool,
    pub estop: bool,
    pub dry_run: bool,
}

#[tauri::command]
pub async fn get_server_status() -> Result<ServerStatus, String> {
    let client = reqwest::Client::builder()
        .danger_accept_invalid_certs(true)
        .build()
        .unwrap();
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

// =====================================================
// E-STOP (긴급 정지 - 트레이 메뉴용)
// =====================================================

#[tauri::command]
pub async fn set_estop(enabled: bool) -> Result<bool, String> {
    set_estop_api(enabled).await
}

pub async fn set_estop_api(enabled: bool) -> Result<bool, String> {
    let client = reqwest::Client::builder()
        .danger_accept_invalid_certs(true)
        .build()
        .unwrap();
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
// Dashboard & Logs (브라우저/탐색기 열기)
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

fn get_logs_path() -> Result<PathBuf, String> {
    let data_dir = dirs::data_dir().ok_or("Data directory not found")?;
    Ok(data_dir.join("BBooster").join("logs"))
}

// =====================================================
// Diagnostic Export (ZIP 파일 생성)
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
    let options =
        zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Deflated);

    // 시스템 정보
    let system_info = format!(
        "OS: {}\nArch: {}\nTimestamp: {}\n",
        std::env::consts::OS,
        std::env::consts::ARCH,
        chrono::Local::now().to_rfc3339()
    );
    zip.start_file("system_info.txt", options)
        .map_err(|e| e.to_string())?;
    use std::io::Write;
    zip.write_all(system_info.as_bytes())
        .map_err(|e| e.to_string())?;

    // 서버 상태
    let server_status = get_server_status().await.unwrap_or(ServerStatus {
        running: false,
        estop: false,
        dry_run: false,
    });
    let status_json = serde_json::to_string_pretty(&server_status).unwrap_or_default();
    zip.start_file("server_status.json", options)
        .map_err(|e| e.to_string())?;
    zip.write_all(status_json.as_bytes())
        .map_err(|e| e.to_string())?;

    // 로그 파일 (있는 경우)
    if let Ok(logs_path) = get_logs_path() {
        if let Ok(entries) = fs::read_dir(&logs_path) {
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_file() && path.extension().map_or(false, |e| e == "log") {
                    if let Ok(content) = fs::read_to_string(&path) {
                        let file_name =
                            format!("logs/{}", path.file_name().unwrap().to_string_lossy());
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
// API Key Management (OS Secure Storage - keyring)
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
// Account Keys Management (OS Secure Storage)
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
    key_entry
        .set_password(&keys.api_key)
        .map_err(|e| e.to_string())?;

    // Save API Secret
    let secret_entry = keyring::Entry::new(&service, &format!("{}_secret", account_name))
        .map_err(|e| e.to_string())?;
    secret_entry
        .set_password(&keys.api_secret)
        .map_err(|e| e.to_string())?;

    // Save Passphrase (OKX only)
    if let Some(pass) = keys.passphrase {
        if !pass.is_empty() {
            let pass_entry =
                keyring::Entry::new(&service, &format!("{}_passphrase", account_name))
                    .map_err(|e| e.to_string())?;
            pass_entry.set_password(&pass).map_err(|e| e.to_string())?;
        }
    }

    // Save account to local registry
    save_account_to_registry(&account_name, &exchange)?;

    Ok(())
}

#[tauri::command]
pub async fn get_account_keys(account_name: String, exchange: String) -> Result<AccountKeys, String> {
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

// Account registry helper functions
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
// URL & File Operations (브라우저/파일 저장)
// =====================================================

#[tauri::command]
pub async fn open_url(url: String) -> Result<String, String> {
    open::that(&url).map_err(|e| format!("URL 열기 실패: {}", e))?;
    Ok("success".to_string())
}

#[tauri::command]
pub async fn download_ai_pdf(job_id: String, file_name: String) -> Result<String, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(30))
        .danger_accept_invalid_certs(true)
        .build()
        .map_err(|e| e.to_string())?;

    let url = format!("{}/api/ai/report/pdf/{}", VPS_SERVER_URL, job_id);

    let resp = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("PDF 요청 실패: {}", e))?;

    if !resp.status().is_success() {
        return Err(format!("PDF 생성 실패: {}", resp.status()));
    }

    let bytes = resp.bytes().await.map_err(|e| e.to_string())?;

    let download_dir = dirs::download_dir().unwrap_or_else(|| std::path::PathBuf::from("."));
    let path = download_dir.join(&file_name);

    std::fs::write(&path, &bytes).map_err(|e| format!("파일 저장 실패: {}", e))?;

    Ok(path.to_string_lossy().to_string())
}
