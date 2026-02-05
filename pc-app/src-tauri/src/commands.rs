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
// Server Management
// =====================================================

#[tauri::command]
pub async fn start_server() -> Result<String, String> {
    // 서버 시작 로직
    let python_path = find_python().ok_or("Python not found")?;
    let server_path = get_server_path()?;

    let mut cmd = Command::new(&python_path);
    cmd.args(["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"])
        .current_dir(&server_path);

    #[cfg(target_os = "windows")]
    cmd.creation_flags(CREATE_NO_WINDOW);

    cmd.spawn()
        .map_err(|e| format!("Failed to start server: {}", e))?;

    Ok("Server started".to_string())
}

pub async fn start_server_internal(_app: &AppHandle) -> Result<String, String> {
    start_server().await
}

#[tauri::command]
pub async fn stop_server() -> Result<String, String> {
    // Windows에서 Python 프로세스 종료
    #[cfg(target_os = "windows")]
    {
        let _ = Command::new("taskkill")
            .args(["/F", "/IM", "python.exe"])
            .creation_flags(CREATE_NO_WINDOW)
            .output();
    }

    #[cfg(not(target_os = "windows"))]
    {
        let _ = Command::new("pkill")
            .args(["-f", "uvicorn"])
            .output();
    }

    Ok("Server stopped".to_string())
}

pub async fn stop_server_internal(_app: &AppHandle) -> Result<String, String> {
    stop_server().await
}

#[tauri::command]
pub async fn get_server_status() -> Result<ServerStatus, String> {
    let client = reqwest::Client::new();
    match client
        .get("http://127.0.0.1:8000/api/diag/home")
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
    open::that("http://127.0.0.1:8000").map_err(|e| e.to_string())
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
    let client = reqwest::Client::new();
    let url = format!(
        "http://127.0.0.1:8000/api/system/estop?value={}",
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
    let client = reqwest::Client::new();
    let resp = client
        .get("http://127.0.0.1:8000/api/diag/home")
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

#[tauri::command]
pub async fn delete_api_key(exchange: String, key_type: String) -> Result<(), String> {
    let service = format!("bbooster_{}", exchange.to_lowercase());
    let entry = keyring::Entry::new(&service, &key_type).map_err(|e| e.to_string())?;
    entry.delete_password().map_err(|e| e.to_string())?;
    Ok(())
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
    let client = reqwest::Client::new();
    let resp = client
        .get("http://127.0.0.1:8000/api/accounts")
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
    let client = reqwest::Client::new();
    let endpoint = match exchange.to_uppercase().as_str() {
        "OKX" => format!("http://127.0.0.1:8000/api/diag/okx-preflight?account={}", account_name),
        "KIS" => format!("http://127.0.0.1:8000/api/diag/kis-preflight?account={}", account_name),
        _ => return Err(format!("Unknown exchange: {}", exchange)),
    };

    let resp = client
        .get(&endpoint)
        .timeout(std::time::Duration::from_secs(10))
        .send()
        .await
        .map_err(|e| e.to_string())?;

    if resp.status().is_success() {
        Ok("Connection successful".to_string())
    } else {
        let error_text = resp.text().await.unwrap_or_default();
        Err(format!("Connection failed: {}", error_text))
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
    let client = reqwest::Client::new();
    let url = format!(
        "http://127.0.0.1:8000/api/timeline?limit={}",
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
    let client = reqwest::Client::new();
    let resp = client
        .get("http://127.0.0.1:8000/api/connectors/status")
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
    let client = reqwest::Client::new();
    let resp = client
        .get("http://127.0.0.1:8000/api/subscription")
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
