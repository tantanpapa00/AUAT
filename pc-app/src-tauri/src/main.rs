#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use std::process::{Child, Command};
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
    // 시스템 트레이 메뉴 구성
    let tray_menu = SystemTrayMenu::new()
        .add_item(CustomMenuItem::new("status", "Status: Checking...").disabled())
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(CustomMenuItem::new("start", "Start Server"))
        .add_item(CustomMenuItem::new("stop", "Stop Server"))
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
            commands::start_server,
            commands::stop_server,
            commands::get_server_status,
            commands::open_dashboard,
            commands::open_logs_folder,
            commands::export_diagnostic,
            commands::set_estop,
            commands::get_home_data,
            commands::save_api_key,
            commands::get_api_key,
            commands::delete_api_key,
            commands::fetch_timeline,
            commands::fetch_connector_status,
            commands::fetch_subscription,
            // Account management
            commands::save_account_keys,
            commands::get_account_keys,
            commands::delete_account_keys,
            commands::list_local_accounts,
            commands::fetch_server_accounts,
            commands::test_account_connection,
        ])
        .setup(|app| {
            // 앱 시작 시 서버 자동 시작 (옵션)
            let handle = app.handle();
            tauri::async_runtime::spawn(async move {
                // 1초 대기 후 서버 시작
                tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
                let _ = commands::start_server_internal(&handle).await;

                // 대시보드 자동 열기
                tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;
                let _ = open::that("http://127.0.0.1:8000");
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
            let _ = open::that("http://127.0.0.1:8000");
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
