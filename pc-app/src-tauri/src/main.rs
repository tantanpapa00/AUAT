#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]
#![recursion_limit = "512"]

use std::process::Child;
use std::sync::Mutex;
use tauri::{
    CustomMenuItem, Manager, SystemTray, SystemTrayEvent, SystemTrayMenu,
    SystemTrayMenuItem, WindowEvent,
};

mod commands;
mod crypto;

// 서버 프로세스 상태 관리
struct ServerState {
    process: Mutex<Option<Child>>,
}

fn main() {
    // 시스템 트레이 메뉴 구성 (VPS 서버 연결 방식)
    let tray_menu = SystemTrayMenu::new()
        .add_item(CustomMenuItem::new("status", "Status: Checking...").disabled())
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(CustomMenuItem::new("start", "VPS 연결 확인"))
        .add_item(CustomMenuItem::new("stop", "연결 해제").disabled())
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(CustomMenuItem::new("dashboard", "Open Dashboard"))
        .add_item(CustomMenuItem::new("logs", "Open Logs Folder"))
        .add_item(CustomMenuItem::new("diagnostic", "Export Diagnostic"))
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(CustomMenuItem::new("estop_on", "E-STOP ON"))
        .add_item(CustomMenuItem::new("estop_off", "E-STOP OFF"))
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(CustomMenuItem::new("quit", "Quit"));

    let system_tray = SystemTray::new().with_menu(tray_menu);

    tauri::Builder::default()
        .manage(ServerState {
            process: Mutex::new(None),
        })
        .system_tray(system_tray)
        .on_system_tray_event(|app, event| match event {
            SystemTrayEvent::LeftClick { .. } => {
                // 왼쪽 클릭: 대시보드 열기
                if let Some(window) = app.get_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            SystemTrayEvent::MenuItemClick { id, .. } => {
                handle_tray_menu(app, &id);
            }
            _ => {}
        })
        .on_window_event(|event| {
            // 창 닫기 시 트레이로 최소화
            if let WindowEvent::CloseRequested { api, .. } = event.event() {
                event.window().hide().unwrap();
                api.prevent_close();
            }
        })
        .invoke_handler(tauri::generate_handler![
            // Server Management (트레이 메뉴용)
            commands::start_server,
            commands::stop_server,
            commands::get_server_status,
            commands::check_server_health,
            commands::set_estop,
            // Dashboard & Logs (브라우저/탐색기)
            commands::open_dashboard,
            commands::open_logs_folder,
            // Diagnostic (파일 생성)
            commands::export_diagnostic,
            // API Key Management (OS keyring)
            commands::save_api_key,
            commands::get_api_key,
            commands::save_account_keys,
            commands::get_account_keys,
            commands::delete_account_keys,
            commands::list_local_accounts,
            // URL & File Operations
            commands::open_url,
            commands::download_ai_pdf,
        ])
        .setup(|app| {
            // 앱 시작 시 VPS 서버 연결 확인 (로컬 서버 시작하지 않음)
            let _handle = app.handle();
            tauri::async_runtime::spawn(async move {
                tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
                // 대시보드 자동 열기
                tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
                let _ = open::that("https://qube-system.com");
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn handle_tray_menu(app: &tauri::AppHandle, id: &str) {
    match id {
        "start" => {
            tauri::async_runtime::spawn({
                let handle = app.clone();
                async move {
                    let _ = commands::start_server_internal(&handle).await;
                }
            });
        }
        "stop" => {
            tauri::async_runtime::spawn({
                let handle = app.clone();
                async move {
                    let _ = commands::stop_server_internal(&handle).await;
                }
            });
        }
        "dashboard" => {
            let _ = open::that("https://qube-system.com");
        }
        "logs" => {
            if let Some(data_dir) = dirs::data_dir() {
                let logs_path = data_dir.join("BBooster").join("logs");
                let _ = std::fs::create_dir_all(&logs_path);
                let _ = open::that(logs_path);
            }
        }
        "diagnostic" => {
            tauri::async_runtime::spawn({
                let handle = app.clone();
                async move {
                    let _ = commands::export_diagnostic_internal(&handle).await;
                }
            });
        }
        "estop_on" => {
            tauri::async_runtime::spawn(async {
                let _ = commands::set_estop_api(true).await;
            });
        }
        "estop_off" => {
            tauri::async_runtime::spawn(async {
                let _ = commands::set_estop_api(false).await;
            });
        }
        "quit" => {
            // 서버 정지 후 종료
            tauri::async_runtime::spawn({
                let handle = app.clone();
                async move {
                    let _ = commands::stop_server_internal(&handle).await;
                    std::process::exit(0);
                }
            });
        }
        _ => {}
    }
}
