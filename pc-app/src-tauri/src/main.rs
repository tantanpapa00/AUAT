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
            commands::start_server,
            commands::stop_server,
            commands::get_server_status,
            commands::check_server_health,
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
            // Auth commands (CORS bypass)
            commands::login_with_email,
            commands::register_with_email,
            commands::get_user_info,
            commands::refresh_auth_token,
            // API Key registration (VPS)
            commands::register_api_key,
            commands::get_accounts_list,
            // Portfolio & Home Page
            commands::get_portfolio_summary,
            commands::get_portfolio_chart,
            commands::get_portfolio_profit_rate,
            commands::get_holdings,
            commands::get_active_strategies,
            commands::get_exchange_rate,
            commands::get_trade_history,
            commands::get_asset_trades,
            commands::get_portfolio_history,
            commands::emergency_stop,
            commands::verify_password,
            // Webhook (PHASE 4)
            commands::get_webhook_logs,
            commands::get_webhook_url,
            // Symbols (PHASE 5)
            commands::search_symbols,
            commands::get_symbol_detail,
            commands::get_popular_symbols,
            // Backtest & Strategy (PHASE 6)
            commands::run_backtest,
            commands::save_strategy,
            commands::get_strategies,
            commands::toggle_strategy,
            commands::delete_strategy,
            commands::toggle_asset,
            commands::delete_asset,
            // Admin (PHASE 7)
            commands::admin_get_users,
            commands::admin_update_user_plan,
            commands::admin_get_system_status,
            commands::admin_get_stats,
            commands::admin_get_recent_users,
            // Market Analysis (STEP 2)
            commands::get_market_overview,
            commands::get_market_us_overview,
            commands::get_market_us_full,
            commands::get_market_us_trend_maintain,
            commands::get_market_sectors,
            commands::get_stock_ranking,
            commands::get_featured_stocks,
            commands::get_market_events,
            // AI + Watchlist (STEP 3)
            commands::get_ai_usage,
            commands::request_ai_analysis,
            commands::get_market_timeline,
            commands::get_watchlist_groups,
            commands::create_watchlist_group,
            commands::delete_watchlist_group,
            commands::get_watchlist_items,
            commands::add_watchlist_item,
            commands::remove_watchlist_item,
            // [BUG FIX 3] 시장분석 개선 API
            commands::get_market_etf,
            commands::get_market_crypto,
            commands::get_analysis_rs,
            commands::get_analysis_new_high,
            commands::get_analysis_valuation,
            // Phase 4: 시장신호 (IBD Big Picture)
            commands::get_market_signal,
            commands::get_market_big_picture,
            commands::get_market_signal_history,
            commands::get_market_breadth_data,
            commands::get_market_breadth_with_index,
            commands::get_market_investors_data,
            commands::get_market_trading_value_data,
            commands::get_screener,  // Phase 7: 종목검색기
            commands::get_market_trend_maintain,
            commands::get_market_sector_analysis,
            commands::get_market_rs_ranking,
            commands::get_market_sector_stocks,
            // Stock Detail Renewal (Phase 2)
            commands::get_stock_financial_summary,
            commands::get_stock_financial_trend,
            commands::get_stock_company,
            commands::get_stock_financial_statement,
            commands::get_stock_news,
            commands::get_stock_disclosures,
            commands::get_stock_consensus,
            commands::get_stock_chart_kr,
            commands::get_stock_summary_kr,
            commands::get_stock_financials_kr,
            commands::get_stock_news_kr,
            commands::get_eps_revision_history,
            commands::get_stock_company_kr,
            commands::get_stock_statement_kr,
            // Phase 9: 해외 종목 상세
            commands::get_stock_summary_us,
            commands::get_stock_chart_us,
            commands::get_stock_news_us,
            commands::get_stock_company_us,
            commands::get_stock_financials_us,
            // Phase 10: ETF 상세
            commands::get_etf_summary,
            commands::get_etf_chart,
            commands::get_etf_performance,
            // Phase 11: 통합 검색 + AI 추천
            commands::search_stocks,
            commands::get_ai_recommendations,
            // TV Connect - 전략/종목 저장
            commands::create_strategy_with_params,
            commands::save_signal_params,
            commands::create_asset,
            // Premium Strategy Engine (Phase 4)
            commands::get_premium_configs,
            commands::get_premium_config,
            commands::create_premium_config,
            commands::update_premium_config,
            commands::delete_premium_config,
            commands::get_strategy_state,
            commands::reset_strategy_state,
            commands::get_scheduler_status,
            commands::start_scheduler,
            commands::stop_scheduler_premium,
            commands::register_to_scheduler,
            commands::trigger_signal,
            commands::get_signal_events,
            // Candle Preload
            commands::preload_candles,
            // MR Backtest (Phase 5)
            commands::run_mr_backtest,
            // Trend Backtest (추세매매)
            commands::run_trend_backtest,
            // Custom Backtest (커스텀 조건빌더)
            commands::run_custom_backtest,
            // KIS Order Settings (KIS 주문 설정)
            commands::save_kis_order_settings,
            commands::get_kis_order_settings,
        ])
        .setup(|app| {
            // 앱 시작 시 VPS 서버 연결 확인 (로컬 서버 시작 없음)
            let _handle = app.handle();
            tauri::async_runtime::spawn(async move {
                // VPS 서버 연결 상태 확인 (로컬 서버 시작하지 않음)
                tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;
                // VPS: https://qube-system.com 에 연결 시도
                // start_server_internal은 더 이상 사용하지 않음

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
