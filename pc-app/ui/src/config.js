// =====================================================
// BBooster PC App Configuration
// =====================================================

// API 서버 URL 설정
// 로컬 개발: "http://127.0.0.1:8000"
// VPS 서버: "http://76.13.180.30:8000"
// 도메인 사용 시: "https://api.yourdomain.com"
export const API_BASE_URL = "http://76.13.180.30:8000";

// 연결 설정
export const CONNECTION_TIMEOUT = 5000; // 5초
export const RETRY_INTERVAL = 3000; // 3초
export const MAX_RETRIES = 3;

// 앱 정보
export const APP_VERSION = "1.0.0";
export const APP_NAME = "BBooster";
