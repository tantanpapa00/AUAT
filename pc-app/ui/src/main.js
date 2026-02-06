import { invoke } from '@tauri-apps/api/tauri';
import { open } from '@tauri-apps/api/shell';
import { API_BASE_URL, CONNECTION_TIMEOUT, MAX_RETRIES } from './config.js';

// =====================================================
// Authentication State
// =====================================================
const auth = {
    accessToken: null,
    refreshToken: null,
    user: null,
    isHubMode: false, // 허브 모드 (로그인 없이 사용)

    saveTokens(access, refresh) {
        this.accessToken = access;
        this.refreshToken = refresh;
        localStorage.setItem('bbooster_access_token', access || '');
        localStorage.setItem('bbooster_refresh_token', refresh || '');
    },

    loadTokens() {
        this.accessToken = localStorage.getItem('bbooster_access_token') || null;
        this.refreshToken = localStorage.getItem('bbooster_refresh_token') || null;
        this.isHubMode = localStorage.getItem('bbooster_hub_mode') === 'true';
    },

    clearTokens() {
        this.accessToken = null;
        this.refreshToken = null;
        this.user = null;
        this.isHubMode = false;
        localStorage.removeItem('bbooster_access_token');
        localStorage.removeItem('bbooster_refresh_token');
        localStorage.removeItem('bbooster_hub_mode');
    },

    setHubMode(enabled) {
        this.isHubMode = enabled;
        localStorage.setItem('bbooster_hub_mode', enabled ? 'true' : 'false');
    },

    isLoggedIn() {
        return !!this.accessToken || this.isHubMode;
    }
};

// =====================================================
// Login Screen Functions
// =====================================================
const loginScreen = document.getElementById('login-screen');
const appElement = document.getElementById('app');
const btnGoogleLogin = document.getElementById('btn-google-login');
const btnSkipLogin = document.getElementById('btn-skip-login');

// 앱 시작 시 기본 상태 설정 (로그인 화면 표시, 앱 숨김)
function ensureLoginScreenVisible() {
    console.log('[UI] 로그인 화면 강제 표시');
    if (loginScreen) loginScreen.style.cssText = 'display: flex !important';
    if (appElement) appElement.style.cssText = 'display: none !important';
}

function showLoginScreen() {
    console.log('[UI] showLoginScreen 호출');
    if (loginScreen) loginScreen.style.cssText = 'display: flex !important';
    if (appElement) appElement.style.cssText = 'display: none !important';
}

function hideLoginScreen() {
    console.log('[UI] hideLoginScreen 호출 - 대시보드 표시');
    if (loginScreen) loginScreen.style.cssText = 'display: none !important';
    if (appElement) appElement.style.cssText = 'display: flex !important';
}

// 앱 로드 시 즉시 로그인 화면 표시 (가장 먼저 실행)
ensureLoginScreenVisible();

// 디버그용: Ctrl+Shift+L 로 인증 데이터 초기화
document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'L') {
        console.log('[Debug] 인증 데이터 초기화');
        localStorage.removeItem('bbooster_access_token');
        localStorage.removeItem('bbooster_refresh_token');
        localStorage.removeItem('bbooster_hub_mode');
        alert('인증 데이터가 초기화되었습니다. 앱을 다시 시작합니다.');
        window.location.reload();
    }
});

// Google 로그인 (브라우저로 열기)
async function loginWithGoogle() {
    try {
        // 브라우저에서 OAuth 로그인 페이지 열기
        await open(`${API_BASE_URL}/api/auth/google/login`);

        // 사용자에게 안내
        showToast('브라우저에서 로그인을 완료해주세요', 'info');

        // 로그인 확인 폴링 시작
        startLoginPolling();
    } catch (error) {
        console.error('Google login failed:', error);
        showToast('로그인 페이지를 열 수 없습니다', 'error');
    }
}

// 로그인 완료 폴링 (웹에서 로그인 후 토큰 확인)
let loginPollingInterval = null;
function startLoginPolling() {
    // 이미 폴링 중이면 중지
    if (loginPollingInterval) clearInterval(loginPollingInterval);

    let attempts = 0;
    const maxAttempts = 60; // 2분 타임아웃 (2초 간격)

    loginPollingInterval = setInterval(async () => {
        attempts++;

        // 로컬 스토리지에서 토큰 확인 (웹에서 저장됨)
        auth.loadTokens();
        if (auth.accessToken) {
            clearInterval(loginPollingInterval);
            loginPollingInterval = null;

            // 사용자 정보 로드
            await loadUserInfo();
            hideLoginScreen();
            showToast('로그인 성공', 'success');
            checkServerConnection();
            return;
        }

        if (attempts >= maxAttempts) {
            clearInterval(loginPollingInterval);
            loginPollingInterval = null;
            showToast('로그인 시간이 초과되었습니다', 'warning');
        }
    }, 2000);
}

// 허브 모드 (로그인 없이 계속)
function skipLogin() {
    auth.setHubMode(true);
    hideLoginScreen();
    updateUserUI({ name: '허브 모드', plan: 'hub', role: 'user' });
    showToast('허브 모드로 시작합니다', 'info');
    checkServerConnection();
}

// =====================================================
// Email Login/Register Functions
// =====================================================
const emailLoginForm = document.getElementById('email-login-form');
const emailRegisterForm = document.getElementById('email-register-form');
const loginTitle = document.getElementById('login-title');
const showRegisterLink = document.getElementById('show-register');
const showLoginLink = document.getElementById('show-login');
const btnEmailLogin = document.getElementById('btn-email-login');
const btnEmailRegister = document.getElementById('btn-email-register');

// 폼 전환
function showEmailLoginForm() {
    if (emailLoginForm) emailLoginForm.style.display = 'flex';
    if (emailRegisterForm) emailRegisterForm.style.display = 'none';
    if (loginTitle) loginTitle.textContent = '로그인';
    clearAuthErrors();
}

function showEmailRegisterForm() {
    if (emailLoginForm) emailLoginForm.style.display = 'none';
    if (emailRegisterForm) emailRegisterForm.style.display = 'flex';
    if (loginTitle) loginTitle.textContent = '회원가입';
    clearAuthErrors();
}

function clearAuthErrors() {
    const loginError = document.getElementById('login-error');
    const registerError = document.getElementById('register-error');
    if (loginError) loginError.textContent = '';
    if (registerError) registerError.textContent = '';
}

function showLoginError(message) {
    const el = document.getElementById('login-error');
    if (el) el.textContent = message;
}

function showRegisterError(message) {
    const el = document.getElementById('register-error');
    if (el) el.textContent = message;
}

// 이메일 로그인 (Tauri invoke 사용 - CORS 우회)
async function handleEmailLogin() {
    const email = document.getElementById('login-email')?.value?.trim();
    const password = document.getElementById('login-password')?.value;

    if (!email || !password) {
        showLoginError('이메일과 비밀번호를 입력하세요');
        return;
    }

    if (btnEmailLogin) {
        btnEmailLogin.disabled = true;
        btnEmailLogin.textContent = '로그인 중...';
    }
    clearAuthErrors();

    try {
        // Tauri invoke로 Rust에서 HTTP 요청 (CORS 우회)
        const data = await invoke('login_with_email', { email, password });

        // 토큰 저장 및 인증 완료
        auth.saveTokens(data.access_token, data.refresh_token);
        await loadUserInfo();
        hideLoginScreen();
        showToast('로그인 성공', 'success');
        checkServerConnection();
    } catch (error) {
        showLoginError(error || '로그인에 실패했습니다');
    } finally {
        if (btnEmailLogin) {
            btnEmailLogin.disabled = false;
            btnEmailLogin.textContent = '로그인';
        }
    }
}

// 이메일 회원가입 (Tauri invoke 사용 - CORS 우회)
async function handleEmailRegister() {
    const name = document.getElementById('register-name')?.value?.trim();
    const email = document.getElementById('register-email')?.value?.trim();
    const password = document.getElementById('register-password')?.value;
    const passwordConfirm = document.getElementById('register-password-confirm')?.value;

    if (!email || !password) {
        showRegisterError('이메일과 비밀번호를 입력하세요');
        return;
    }

    if (password !== passwordConfirm) {
        showRegisterError('비밀번호가 일치하지 않습니다');
        return;
    }

    if (password.length < 6) {
        showRegisterError('비밀번호는 6자 이상이어야 합니다');
        return;
    }

    if (btnEmailRegister) {
        btnEmailRegister.disabled = true;
        btnEmailRegister.textContent = '회원가입 중...';
    }
    clearAuthErrors();

    try {
        // Tauri invoke로 Rust에서 HTTP 요청 (CORS 우회)
        const data = await invoke('register_with_email', {
            email,
            password,
            name: name || null
        });

        // 회원가입 성공 - 자동 로그인
        auth.saveTokens(data.access_token, data.refresh_token);
        await loadUserInfo();
        hideLoginScreen();
        showToast('회원가입 및 로그인 성공', 'success');
        checkServerConnection();
    } catch (error) {
        showRegisterError(error || '회원가입에 실패했습니다');
    } finally {
        if (btnEmailRegister) {
            btnEmailRegister.disabled = false;
            btnEmailRegister.textContent = '회원가입';
        }
    }
}

// 이메일 로그인/회원가입 이벤트 리스너
showRegisterLink?.addEventListener('click', showEmailRegisterForm);
showLoginLink?.addEventListener('click', showEmailLoginForm);
btnEmailLogin?.addEventListener('click', handleEmailLogin);
btnEmailRegister?.addEventListener('click', handleEmailRegister);

// Enter 키로 로그인/회원가입
document.getElementById('login-password')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleEmailLogin();
});
document.getElementById('register-password-confirm')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') handleEmailRegister();
});

// 사용자 정보 로드 (Tauri invoke 사용 - CORS 우회)
async function loadUserInfo() {
    if (!auth.accessToken) return;

    try {
        // Tauri invoke로 Rust에서 HTTP 요청 (CORS 우회)
        const user = await invoke('get_user_info', { accessToken: auth.accessToken });
        auth.user = user;
        updateUserUI(auth.user);
    } catch (error) {
        console.error('Failed to load user info:', error);
        // 토큰 만료 가능성 - 리프레시 시도
        if (String(error).includes('401') || String(error).includes('Unauthorized')) {
            await refreshAuthToken();
        }
    }
}

// 토큰 갱신 (로그인 후 사용)
async function refreshAuthToken() {
    const success = await tryRefreshToken();
    if (!success) {
        showLoginScreen();
    }
}

// UI 사용자 정보 업데이트
function updateUserUI(user) {
    // 구독 뱃지 업데이트
    const badge = document.getElementById('subscription-badge');
    const badgeText = document.getElementById('subscription-text');

    if (user.plan === 'premium') {
        badge.className = 'subscription-badge premium';
        badgeText.textContent = '프리미엄';
    } else if (user.plan === 'hub') {
        badge.className = 'subscription-badge hub';
        badgeText.textContent = '허브형';
    } else {
        badge.className = 'subscription-badge free';
        badgeText.textContent = '무료';
    }
}

// 로그아웃 (완전 초기화)
function logout() {
    console.log('[Logout] 로그아웃 실행');
    // 모든 인증 관련 데이터 삭제
    localStorage.removeItem('bbooster_access_token');
    localStorage.removeItem('bbooster_refresh_token');
    localStorage.removeItem('bbooster_hub_mode');
    // 페이지 새로고침 (인라인 스크립트가 로그인 화면 표시)
    window.location.reload();
}

// 로그아웃 버튼 이벤트
document.getElementById('btn-logout')?.addEventListener('click', logout);

// 인증 상태 확인 및 초기화
async function initAuth() {
    console.log('[initAuth] ========== 인증 시작 ==========');

    // 먼저 로그인 화면이 보이는지 확인 (방어적 코드)
    ensureLoginScreenVisible();

    // 저장된 토큰 로드
    auth.loadTokens();
    console.log('[initAuth] 저장된 상태:', {
        hasAccessToken: !!auth.accessToken,
        hasRefreshToken: !!auth.refreshToken,
        isHubMode: auth.isHubMode
    });

    // 1. 허브 모드인 경우 - 로그인 없이 진행
    if (auth.isHubMode) {
        console.log('[initAuth] → 허브 모드 감지 - 대시보드로 이동');
        hideLoginScreen();
        updateUserUI({ name: '허브 모드', plan: 'hub', role: 'user' });
        return true;
    }

    // 2. 액세스 토큰이 없는 경우 - 바로 로그인 화면
    if (!auth.accessToken) {
        console.log('[initAuth] → 토큰 없음 - 로그인 화면 유지');
        // 이미 ensureLoginScreenVisible()에서 표시됨
        return false;
    }

    // 3. 액세스 토큰이 있는 경우 - 유효성 검증 (Tauri invoke 사용)
    console.log('[initAuth] → 토큰 검증 시도...');
    try {
        // Tauri invoke로 Rust에서 HTTP 요청 (CORS 우회)
        const user = await invoke('get_user_info', { accessToken: auth.accessToken });
        auth.user = user;
        console.log('[initAuth] → 토큰 유효! 사용자:', auth.user.email);
        updateUserUI(auth.user);
        hideLoginScreen();
        return true;
    } catch (error) {
        console.error('[initAuth] → 토큰 검증 실패:', error);
        // 토큰 만료 가능성 - 리프레시 시도
        console.log('[initAuth] → 토큰 만료, 갱신 시도...');
        const refreshed = await tryRefreshToken();
        if (refreshed) {
            console.log('[initAuth] → 토큰 갱신 성공!');
            hideLoginScreen();
            return true;
        }
        console.log('[initAuth] → 토큰 갱신 실패');
    }

    // 4. 토큰 검증 실패 - 토큰 삭제하고 로그인 화면 유지
    console.log('[initAuth] → 인증 실패 - 토큰 삭제, 로그인 화면 유지');
    auth.clearTokens();
    // ensureLoginScreenVisible()이 이미 호출되었으므로 추가 호출 불필요
    return false;
}

// 토큰 갱신 시도 (Tauri invoke 사용 - CORS 우회)
async function tryRefreshToken() {
    if (!auth.refreshToken) {
        return false;
    }

    try {
        // Tauri invoke로 Rust에서 HTTP 요청 (CORS 우회)
        const tokens = await invoke('refresh_auth_token', { refreshToken: auth.refreshToken });
        auth.saveTokens(tokens.access_token, tokens.refresh_token);
        await loadUserInfo();
        console.log('[tryRefreshToken] 토큰 갱신 성공');
        return true;
    } catch (error) {
        console.error('[tryRefreshToken] 토큰 갱신 실패:', error);
    }

    auth.clearTokens();
    return false;
}

// 이벤트 리스너
btnGoogleLogin?.addEventListener('click', loginWithGoogle);
btnSkipLogin?.addEventListener('click', skipLogin);

// =====================================================
// Connection State
// =====================================================
let isConnected = false;
let retryCount = 0;

// =====================================================
// DOM Elements
// =====================================================
const serverStatus = document.getElementById('server-status');
const estopStatus = document.getElementById('estop-status');
const eventsList = document.getElementById('events-list');

// Status lights
const lightServer = document.getElementById('light-server');
const lightEstop = document.getElementById('light-estop');

// Status overview
const lastSignal = document.getElementById('last-signal');
const lastOrder = document.getElementById('last-order');
const lastFilled = document.getElementById('last-filled');
const systemStatusEl = document.getElementById('system-status');

// Timeline & Connectors
const timelineList = document.getElementById('timeline-list');
const connectorList = document.getElementById('connector-list');

// Error guide
const errorGuide = document.getElementById('error-guide');
const errorMessage = document.getElementById('error-message');
const errorSolution = document.getElementById('error-solution');

// Buttons
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const btnDashboard = document.getElementById('btn-dashboard');
const btnEstopOn = document.getElementById('btn-estop-on');
const btnEstopOff = document.getElementById('btn-estop-off');
const btnLogs = document.getElementById('btn-logs');
const btnDiagnostic = document.getElementById('btn-diagnostic');

// Navigation
const navItems = document.querySelectorAll('.nav-item');
const pageTitle = document.getElementById('page-title');
const subscriptionBadge = document.getElementById('subscription-badge');

// Page titles mapping
const pageTitles = {
    dashboard: '대시보드',
    accounts: '계정 및 API 키',
    templates: 'TradingView 템플릿',
    settings: '시스템 설정',
    logs: '거래 로그'
};

// =====================================================
// Navigation
// =====================================================
navItems.forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        const page = item.dataset.page;
        navigateTo(page);
    });
});

function navigateTo(page) {
    // Update nav active state
    navItems.forEach(nav => {
        nav.classList.toggle('active', nav.dataset.page === page);
    });

    // Update page title
    pageTitle.textContent = pageTitles[page] || 'Dashboard';

    // Show/hide pages
    document.querySelectorAll('.page-content').forEach(pageEl => {
        pageEl.style.display = 'none';
    });
    const targetPage = document.getElementById(`page-${page}`);
    if (targetPage) {
        targetPage.style.display = 'block';
    }

    // Page-specific initialization
    if (page === 'accounts') {
        loadAccounts();
    } else if (page === 'templates') {
        loadTemplateAssets();
    } else if (page === 'settings') {
        loadSettingsData();
    } else if (page === 'logs') {
        loadLogs();
    }
}

// =====================================================
// Status Update
// =====================================================
async function updateStatus() {
    try {
        const status = await invoke('get_server_status');

        // Server status with light
        if (status.running) {
            serverStatus.textContent = 'Server: Running';
            lightServer.className = 'status-light green';
            btnStart.disabled = true;
            btnStop.disabled = false;
            systemStatusEl.textContent = 'Normal';
            systemStatusEl.style.color = '#22C55E';
        } else {
            serverStatus.textContent = 'Server: Stopped';
            lightServer.className = 'status-light red';
            btnStart.disabled = false;
            btnStop.disabled = true;
            systemStatusEl.textContent = 'Offline';
            systemStatusEl.style.color = '#EF4444';
        }

        // E-STOP status with light
        if (status.estop) {
            estopStatus.textContent = 'E-STOP: ON';
            lightEstop.className = 'status-light red';
            systemStatusEl.textContent = 'E-STOP Active';
            systemStatusEl.style.color = '#EF4444';
        } else {
            estopStatus.textContent = 'E-STOP: OFF';
            lightEstop.className = 'status-light green';
        }

        // Load data if server is running
        if (status.running) {
            await Promise.all([
                loadEvents(),
                loadTimeline(),
                loadStatusOverview(),
                loadConnectorStatus(),
                loadSubscription()
            ]);
            hideError();
        }
    } catch (error) {
        console.error('Status update failed:', error);
        serverStatus.textContent = 'Server: Error';
        lightServer.className = 'status-light red';
        showError('CONNECTION_ERROR', 'Cannot connect to server');
    }
}

// =====================================================
// Events
// =====================================================
async function loadEvents() {
    try {
        const data = await invoke('get_home_data');

        if (data.recent_events && data.recent_events.length > 0) {
            eventsList.innerHTML = data.recent_events.map(event => `
                <div class="event-item">
                    <div>
                        <span class="symbol">${event.symbol || '--'}</span>
                        <span class="type">${event.event_type || ''}</span>
                    </div>
                    <span class="time">${formatTime(event.created_at)}</span>
                </div>
            `).join('');
        } else {
            eventsList.innerHTML = '<p class="empty">No recent events</p>';
        }
    } catch (error) {
        console.error('Failed to load events:', error);
        eventsList.innerHTML = '<p class="empty">Failed to load events</p>';
    }
}

function formatTime(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    return date.toLocaleTimeString('ko-KR', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function formatDateTime(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();

    if (isToday) {
        return date.toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit'
        });
    }
    return date.toLocaleDateString('ko-KR', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// =====================================================
// Status Overview
// =====================================================
async function loadStatusOverview() {
    try {
        const data = await invoke('get_home_data');

        if (data.items && data.items.length > 0) {
            let recentSignal = null;
            let recentOrder = null;
            let recentFilled = null;

            for (const item of data.items) {
                if (item.last_signal_at) {
                    if (!recentSignal || new Date(item.last_signal_at) > new Date(recentSignal)) {
                        recentSignal = item.last_signal_at;
                    }
                }
                if (item.last_order_at) {
                    if (!recentOrder || new Date(item.last_order_at) > new Date(recentOrder)) {
                        recentOrder = item.last_order_at;
                    }
                }
                if (item.last_filled_qty) {
                    if (!recentFilled || new Date(item.last_checked_at) > new Date(recentFilled)) {
                        recentFilled = item.last_checked_at;
                    }
                }
            }

            lastSignal.textContent = formatDateTime(recentSignal);
            lastOrder.textContent = formatDateTime(recentOrder);
            lastFilled.textContent = recentFilled ? formatDateTime(recentFilled) : '--';
        }
    } catch (error) {
        console.error('Failed to load status overview:', error);
    }
}

// =====================================================
// Order Timeline (using new Tauri command)
// =====================================================
async function loadTimeline() {
    try {
        // Try new fetch_timeline command first
        let timelineData = [];
        try {
            timelineData = await invoke('fetch_timeline', { limit: 10 });
        } catch (e) {
            // Fallback to get_home_data
            const data = await invoke('get_home_data');
            if (data.items) {
                timelineData = data.items
                    .filter(item => item.last_order_at)
                    .map(item => ({
                        timestamp: item.last_order_at,
                        event_type: item.last_order_status || 'unknown',
                        message: item.symbol,
                        symbol: item.symbol
                    }));
            }
        }

        if (timelineData && timelineData.length > 0) {
            timelineList.innerHTML = timelineData.slice(0, 5).map(event => {
                const status = event.event_type || 'received';
                const statusClass = getStatusClass(status);

                return `
                    <div class="timeline-item ${statusClass}">
                        <div class="timeline-content">
                            <div class="timeline-header">
                                <span class="timeline-symbol">${event.symbol || event.message || '--'}</span>
                                <span class="timeline-status ${statusClass}">${status}</span>
                            </div>
                            <div class="timeline-details">${event.message || ''}</div>
                            <div class="timeline-time">${formatDateTime(event.timestamp)}</div>
                        </div>
                    </div>
                `;
            }).join('');
        } else {
            timelineList.innerHTML = '<p class="empty">No recent orders</p>';
        }
    } catch (error) {
        console.error('Failed to load timeline:', error);
        timelineList.innerHTML = '<p class="empty">Failed to load timeline</p>';
    }
}

function getStatusClass(status) {
    const statusMap = {
        'sent': 'sent',
        'filled': 'filled',
        'partial': 'partial',
        'failed': 'failed',
        'received': 'received',
        'signal': 'received',
        'order': 'sent'
    };
    return statusMap[status.toLowerCase()] || 'received';
}

// =====================================================
// Connector Status (using new Tauri command)
// =====================================================
async function loadConnectorStatus() {
    try {
        let connectors = [];
        try {
            connectors = await invoke('fetch_connector_status');
        } catch (e) {
            // If API not available, show default connectors
            connectors = [
                { exchange: 'OKX', connected: false, last_ping: null },
                { exchange: 'KIS', connected: false, last_ping: null }
            ];
        }

        if (connectors && connectors.length > 0) {
            connectorList.innerHTML = connectors.map(conn => {
                const statusClass = conn.connected ? 'connected' : 'disconnected';
                const statusText = conn.connected ? 'Connected' : 'Disconnected';
                const statusIcon = conn.connected ? '●' : '○';

                return `
                    <div class="connector-item">
                        <span class="connector-name">${conn.exchange}</span>
                        <span class="connector-status ${statusClass}">
                            ${statusIcon} ${statusText}
                        </span>
                    </div>
                `;
            }).join('');
        } else {
            connectorList.innerHTML = '<p class="empty">No connectors configured</p>';
        }
    } catch (error) {
        console.error('Failed to load connector status:', error);
        connectorList.innerHTML = '<p class="empty">Failed to load connectors</p>';
    }
}

// =====================================================
// Subscription (using new Tauri command)
// =====================================================
async function loadSubscription() {
    try {
        const subscription = await invoke('fetch_subscription');

        if (subscription) {
            subscriptionBadge.textContent = subscription.plan || 'Free';

            // Update badge style based on plan
            subscriptionBadge.className = 'subscription-badge';
            if (subscription.plan === 'Pro') {
                subscriptionBadge.classList.add('pro');
            } else if (subscription.plan === 'Hub') {
                subscriptionBadge.classList.add('hub');
            }
        }
    } catch (error) {
        console.error('Failed to load subscription:', error);
        subscriptionBadge.textContent = 'Free';
    }
}

// =====================================================
// Error Guide with Human-readable Messages
// =====================================================
const ERROR_GUIDES = {
    'CONNECTION_ERROR': {
        message: 'Server connection failed',
        solution: `
            <h4>Resolution Steps:</h4>
            <ul>
                <li>Check if the server is running</li>
                <li>Click <strong>Start Server</strong> button</li>
                <li>Verify port 8000 is not in use</li>
            </ul>
        `
    },
    'INSUFFICIENT_BAL': {
        message: 'Insufficient balance for order',
        solution: `
            <h4>Resolution Steps:</h4>
            <ul>
                <li>Check your exchange account balance</li>
                <li>Reduce order quantity</li>
                <li>Deposit more funds to your trading account</li>
            </ul>
        `
    },
    'ESTOP_ACTIVE': {
        message: 'E-STOP is active - all orders blocked',
        solution: `
            <h4>Resolution Steps:</h4>
            <ul>
                <li>Click <strong>E-STOP OFF</strong> to resume trading</li>
                <li>Verify system is ready before resuming</li>
            </ul>
        `
    },
    'API_KEY_INVALID': {
        message: 'API key authentication failed',
        solution: `
            <h4>Resolution Steps:</h4>
            <ul>
                <li>Verify API key is correct</li>
                <li>Check API key permissions (trading enabled)</li>
                <li>Regenerate API key if necessary</li>
            </ul>
        `
    },
    'RATE_LIMITED': {
        message: 'Too many requests - rate limited by exchange',
        solution: `
            <h4>Resolution Steps:</h4>
            <ul>
                <li>Wait 1-2 minutes before retrying</li>
                <li>Reduce signal frequency</li>
            </ul>
        `
    }
};

function showError(errorCode, rawMessage) {
    const guide = ERROR_GUIDES[errorCode] || {
        message: rawMessage || 'An error occurred',
        solution: `
            <h4>General Steps:</h4>
            <ul>
                <li>Check server logs for details</li>
                <li>Export diagnostic report</li>
                <li>Contact support if issue persists</li>
            </ul>
        `
    };

    errorMessage.textContent = guide.message;
    errorSolution.innerHTML = guide.solution;
    errorGuide.style.display = 'block';
}

function hideError() {
    errorGuide.style.display = 'none';
}

// =====================================================
// Toast Notifications
// =====================================================
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 3000);
}

// =====================================================
// Event Handlers
// =====================================================
btnStart.addEventListener('click', async () => {
    btnStart.disabled = true;
    try {
        await invoke('start_server');
        showToast('Server starting...');
        setTimeout(updateStatus, 2000);
    } catch (error) {
        showToast('Failed to start server', 'error');
        btnStart.disabled = false;
    }
});

btnStop.addEventListener('click', async () => {
    btnStop.disabled = true;
    try {
        await invoke('stop_server');
        showToast('Server stopped');
        setTimeout(updateStatus, 1000);
    } catch (error) {
        showToast('Failed to stop server', 'error');
        btnStop.disabled = false;
    }
});

btnDashboard.addEventListener('click', async () => {
    try {
        await invoke('open_dashboard');
    } catch (error) {
        showToast('Failed to open dashboard', 'error');
    }
});

btnEstopOn.addEventListener('click', async () => {
    // Confirmation dialog
    if (!confirm('E-STOP을 켜시겠습니까?\n\n모든 주문 전송이 차단됩니다.')) {
        return;
    }

    try {
        await invoke('set_estop', { enabled: true });
        showToast('E-STOP activated', 'warning');
        updateStatus();
    } catch (error) {
        showToast('Failed to set E-STOP', 'error');
    }
});

btnEstopOff.addEventListener('click', async () => {
    try {
        await invoke('set_estop', { enabled: false });
        showToast('E-STOP deactivated');
        updateStatus();
    } catch (error) {
        showToast('Failed to set E-STOP', 'error');
    }
});

btnLogs.addEventListener('click', async () => {
    try {
        await invoke('open_logs_folder');
    } catch (error) {
        showToast('Failed to open logs folder', 'error');
    }
});

btnDiagnostic.addEventListener('click', async () => {
    btnDiagnostic.disabled = true;
    btnDiagnostic.textContent = 'Exporting...';
    try {
        const path = await invoke('export_diagnostic');
        showToast(`Diagnostic exported`);
    } catch (error) {
        showToast('Failed to export diagnostic', 'error');
    } finally {
        btnDiagnostic.disabled = false;
        btnDiagnostic.textContent = 'Export Diagnostic';
    }
});

// =====================================================
// Accounts Page
// =====================================================

// DOM Elements for Accounts
const accountsList = document.getElementById('accounts-list');
const btnAddAccount = document.getElementById('btn-add-account');
const accountModal = document.getElementById('account-modal');
const modalTitle = document.getElementById('modal-title');
const modalClose = document.getElementById('modal-close');
const accountForm = document.getElementById('account-form');
const accountName = document.getElementById('account-name');
const accountExchange = document.getElementById('account-exchange');
const apiKey = document.getElementById('api-key');
const apiSecret = document.getElementById('api-secret');
const apiPassphrase = document.getElementById('api-passphrase');
const passphraseGroup = document.getElementById('passphrase-group');
const btnTestConnection = document.getElementById('btn-test-connection');
const formMessage = document.getElementById('form-message');

// Delete Modal
const deleteModal = document.getElementById('delete-modal');
const deleteModalClose = document.getElementById('delete-modal-close');
const deleteAccountName = document.getElementById('delete-account-name');
const btnCancelDelete = document.getElementById('btn-cancel-delete');
const btnConfirmDelete = document.getElementById('btn-confirm-delete');

let editingAccount = null;
let deletingAccount = null;

// Load accounts when navigating to Accounts page
async function loadAccounts() {
    try {
        let accounts = [];

        // If logged in, get accounts from VPS server
        if (auth.accessToken) {
            try {
                accounts = await invoke('get_accounts_list', {
                    accessToken: auth.accessToken
                });
                console.log('[Accounts] VPS 서버에서 계정 로드:', accounts.length);
            } catch (e) {
                console.log('VPS accounts not available:', e);
            }
        }

        // Also get local accounts (for hub mode or backup)
        let localAccounts = [];
        try {
            localAccounts = await invoke('list_local_accounts');
        } catch (e) {
            console.log('Local accounts not available');
        }

        // Combine and deduplicate (VPS accounts take priority)
        const accountMap = new Map();
        for (const acc of [...accounts, ...localAccounts]) {
            const key = `${acc.name}-${acc.exchange}`;
            if (!accountMap.has(key)) {
                accountMap.set(key, acc);
            }
        }

        const allAccounts = Array.from(accountMap.values());

        if (allAccounts.length === 0) {
            accountsList.innerHTML = `
                <div class="empty-state">
                    <p class="empty">No accounts registered yet.</p>
                    <p class="empty">Click "Add Account" to register your first exchange account.</p>
                </div>
            `;
            return;
        }

        accountsList.innerHTML = allAccounts.map(account => `
            <div class="account-card" data-id="${account.id || 0}" data-name="${account.name}" data-exchange="${account.exchange}">
                <div class="account-card-header">
                    <div class="account-info">
                        <h3>${account.name}</h3>
                        <div class="account-exchange">
                            <span class="exchange-badge ${account.exchange.toLowerCase()}">${account.exchange}</span>
                        </div>
                    </div>
                    <div class="account-status ${account.is_active ? 'active' : 'inactive'}">
                        ${account.is_active ? '● Active' : '○ Inactive'}
                    </div>
                </div>
                <div class="account-card-body">
                    <div class="account-detail">
                        <span class="account-detail-label">API Key</span>
                        <span class="account-detail-value">****${account.has_keys ? '(saved)' : '(not set)'}</span>
                    </div>
                    <div class="account-detail">
                        <span class="account-detail-label">Last Health Check</span>
                        <span class="account-detail-value">${account.last_health_check ? formatDateTime(account.last_health_check) : '--'}</span>
                    </div>
                    <div class="account-detail">
                        <span class="account-detail-label">Status</span>
                        <span class="account-detail-value">${account.health_status || '--'}</span>
                    </div>
                </div>
                <div class="account-card-actions">
                    <button class="btn btn-secondary btn-edit" data-id="${account.id || 0}" data-name="${account.name}" data-exchange="${account.exchange}">Edit</button>
                    <button class="btn btn-secondary btn-test" data-name="${account.name}" data-exchange="${account.exchange}">Test</button>
                    <button class="btn btn-danger btn-delete" data-id="${account.id || 0}" data-name="${account.name}" data-exchange="${account.exchange}">Delete</button>
                </div>
            </div>
        `).join('');

        // Add event listeners to buttons
        document.querySelectorAll('.btn-edit').forEach(btn => {
            btn.addEventListener('click', () => openEditModal(btn.dataset.name, btn.dataset.exchange));
        });

        document.querySelectorAll('.btn-test').forEach(btn => {
            btn.addEventListener('click', () => testAccountConnection(btn.dataset.name, btn.dataset.exchange, btn));
        });

        document.querySelectorAll('.btn-delete').forEach(btn => {
            btn.addEventListener('click', () => openDeleteModal(btn.dataset.id, btn.dataset.name, btn.dataset.exchange));
        });

    } catch (error) {
        console.error('Failed to load accounts:', error);
        accountsList.innerHTML = '<p class="empty">Failed to load accounts</p>';
    }
}

// Open Add Account Modal
function openAddModal() {
    editingAccount = null;
    modalTitle.textContent = 'Add Account';
    accountForm.reset();
    passphraseGroup.style.display = 'none';
    formMessage.style.display = 'none';
    accountName.disabled = false;
    accountExchange.disabled = false;
    accountModal.style.display = 'flex';
}

// Open Edit Account Modal
async function openEditModal(name, exchange) {
    editingAccount = { name, exchange };
    modalTitle.textContent = 'Edit Account';
    accountName.value = name;
    accountName.disabled = true;
    accountExchange.value = exchange;
    accountExchange.disabled = true;

    // Show passphrase field for OKX
    passphraseGroup.style.display = exchange === 'OKX' ? 'block' : 'none';

    // Clear sensitive fields
    apiKey.value = '';
    apiSecret.value = '';
    apiPassphrase.value = '';

    formMessage.style.display = 'none';
    accountModal.style.display = 'flex';
}

// Close Modal
function closeModal() {
    accountModal.style.display = 'none';
    editingAccount = null;
}

// Show/hide passphrase based on exchange
accountExchange.addEventListener('change', () => {
    passphraseGroup.style.display = accountExchange.value === 'OKX' ? 'block' : 'none';
});

// Add Account Button
btnAddAccount.addEventListener('click', openAddModal);

// Close Modal
modalClose.addEventListener('click', closeModal);
accountModal.addEventListener('click', (e) => {
    if (e.target === accountModal) closeModal();
});

// Test Connection
btnTestConnection.addEventListener('click', async () => {
    const exchange = accountExchange.value;
    const name = accountName.value;

    if (!exchange || !name) {
        showFormMessage('Please fill in account name and exchange', 'error');
        return;
    }

    showFormMessage('Testing connection...', 'loading');
    btnTestConnection.disabled = true;

    try {
        const result = await invoke('test_account_connection', {
            exchange: exchange,
            accountName: name
        });
        showFormMessage(result, 'success');
    } catch (error) {
        showFormMessage(`Connection failed: ${error}`, 'error');
    } finally {
        btnTestConnection.disabled = false;
    }
});

// Save Account
accountForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const name = accountName.value.trim();
    const exchange = accountExchange.value;
    const key = apiKey.value.trim();
    const secret = apiSecret.value.trim();
    const passphrase = apiPassphrase.value.trim();

    if (!name || !exchange || !key || !secret) {
        showFormMessage('Please fill in all required fields', 'error');
        return;
    }

    showFormMessage('Saving account...', 'loading');

    try {
        // If logged in, register API key on VPS server
        if (auth.accessToken) {
            console.log('[Accounts] VPS 서버에 API 키 등록 중...');
            const result = await invoke('register_api_key', {
                accessToken: auth.accessToken,
                name: name,
                exchange: exchange,
                apiKey: key,
                apiSecret: secret,
                apiPassphrase: passphrase || null
            });
            console.log('[Accounts] VPS 등록 성공:', result);
            showFormMessage('API 키가 서버에 등록되었습니다!', 'success');
        } else {
            // Hub mode: save locally only
            console.log('[Accounts] 로컬에 API 키 저장 중...');
            await invoke('save_account_keys', {
                accountName: name,
                exchange: exchange,
                keys: {
                    api_key: key,
                    api_secret: secret,
                    passphrase: passphrase || null
                }
            });
            showFormMessage('Account saved locally!', 'success');
        }

        setTimeout(() => {
            closeModal();
            loadAccounts();
        }, 1000);
    } catch (error) {
        showFormMessage(`Failed to save: ${error}`, 'error');
    }
});

// Test connection from card
async function testAccountConnection(name, exchange, btn) {
    const originalText = btn.textContent;
    btn.textContent = 'Testing...';
    btn.disabled = true;

    try {
        await invoke('test_account_connection', {
            exchange: exchange,
            accountName: name
        });
        showToast(`${name}: Connection successful`, 'success');
    } catch (error) {
        showToast(`${name}: ${error}`, 'error');
    } finally {
        btn.textContent = originalText;
        btn.disabled = false;
    }
}

// Delete Modal
function openDeleteModal(id, name, exchange) {
    deletingAccount = { id: parseInt(id) || 0, name, exchange };
    deleteAccountName.textContent = `${name} (${exchange})`;
    deleteModal.style.display = 'flex';
}

function closeDeleteModal() {
    deleteModal.style.display = 'none';
    deletingAccount = null;
}

deleteModalClose.addEventListener('click', closeDeleteModal);
btnCancelDelete.addEventListener('click', closeDeleteModal);
deleteModal.addEventListener('click', (e) => {
    if (e.target === deleteModal) closeDeleteModal();
});

btnConfirmDelete.addEventListener('click', async () => {
    if (!deletingAccount) return;

    btnConfirmDelete.disabled = true;
    btnConfirmDelete.textContent = 'Deleting...';

    try {
        // If logged in, delete from VPS server
        if (auth.accessToken) {
            console.log('[Accounts] VPS 서버에서 계정 삭제 중...');
            await invoke('delete_api_key', {
                accessToken: auth.accessToken,
                accountId: deletingAccount.id || 0,
                accountName: deletingAccount.name,
                exchange: deletingAccount.exchange
            });
            showToast(`${deletingAccount.name} 서버에서 삭제됨`);
        } else {
            // Hub mode: delete locally
            await invoke('delete_account_keys', {
                accountName: deletingAccount.name,
                exchange: deletingAccount.exchange
            });
            showToast(`${deletingAccount.name} deleted successfully`);
        }
        closeDeleteModal();
        loadAccounts();
    } catch (error) {
        showToast(`Failed to delete: ${error}`, 'error');
    } finally {
        btnConfirmDelete.disabled = false;
        btnConfirmDelete.textContent = 'Delete';
    }
});

// Form message helper
function showFormMessage(message, type) {
    formMessage.textContent = message;
    formMessage.className = `form-message ${type}`;
    formMessage.style.display = 'block';
}

// =====================================================
// Templates Page
// =====================================================
const templateSide = document.getElementById('template-side');
const templateQty = document.getElementById('template-qty');
const templateType = document.getElementById('template-type');
const assetsList = document.getElementById('assets-list');
const btnRefreshAssets = document.getElementById('btn-refresh-assets');
const btnGenerateTemplates = document.getElementById('btn-generate-templates');
const templatesResult = document.getElementById('templates-result');

let selectedAssets = new Set();

// Load assets for template generation
async function loadTemplateAssets() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/templates/tradingview/options`);
        const data = await response.json();

        if (data.ok && data.options && data.options.length > 0) {
            assetsList.innerHTML = data.options.map(asset => `
                <label class="asset-item" data-asset-id="${asset.asset_id}">
                    <input type="checkbox" value="${asset.asset_id}">
                    <div class="asset-info">
                        <div class="asset-symbol">${asset.symbol}</div>
                        <div class="asset-meta">${asset.account_name} / ${asset.strategy_name} / ${asset.exchange}</div>
                    </div>
                </label>
            `).join('');

            // Add event listeners
            assetsList.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
                checkbox.addEventListener('change', (e) => {
                    const assetItem = e.target.closest('.asset-item');
                    const assetId = parseInt(e.target.value);

                    if (e.target.checked) {
                        selectedAssets.add(assetId);
                        assetItem.classList.add('selected');
                    } else {
                        selectedAssets.delete(assetId);
                        assetItem.classList.remove('selected');
                    }

                    btnGenerateTemplates.disabled = selectedAssets.size === 0;
                });
            });
        } else {
            assetsList.innerHTML = `
                <p class="empty">No assets available.</p>
                <p class="empty">Register accounts and create strategies first.</p>
            `;
        }
    } catch (error) {
        console.error('Failed to load assets:', error);
        assetsList.innerHTML = '<p class="empty">Failed to load assets. Check server connection.</p>';
    }
}

// Generate templates
async function generateTemplates() {
    if (selectedAssets.size === 0) return;

    btnGenerateTemplates.disabled = true;
    btnGenerateTemplates.textContent = 'Generating...';

    try {
        const response = await fetch(`${API_BASE_URL}/api/templates/tradingview/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                asset_ids: Array.from(selectedAssets),
                side: templateSide.value,
                qty: parseFloat(templateQty.value),
                type: templateType.value
            })
        });

        const data = await response.json();

        if (data.ok && data.results) {
            templatesResult.innerHTML = data.results.map(result => {
                if (!result.ok) {
                    return `
                        <div class="template-item error">
                            <div class="template-item-header">
                                <span class="template-item-title">${result.symbol} - Error</span>
                            </div>
                            <div class="template-item-body">
                                <p class="error-text">${result.error || 'Unknown error'}</p>
                            </div>
                        </div>
                    `;
                }

                const templateJson = JSON.stringify(result.template, null, 2);
                return `
                    <div class="template-item">
                        <div class="template-item-header">
                            <span class="template-item-title">${result.symbol} (${result.account_name})</span>
                            <button class="btn btn-secondary btn-sm btn-copy" data-template='${templateJson.replace(/'/g, "\\'")}'>
                                Copy
                            </button>
                        </div>
                        <div class="template-item-body">
                            <pre class="template-json">${templateJson}</pre>
                        </div>
                    </div>
                `;
            }).join('');

            // Add copy event listeners
            templatesResult.querySelectorAll('.btn-copy').forEach(btn => {
                btn.addEventListener('click', () => copyTemplateToClipboard(btn));
            });
        } else {
            templatesResult.innerHTML = '<p class="empty">Failed to generate templates</p>';
        }
    } catch (error) {
        console.error('Failed to generate templates:', error);
        templatesResult.innerHTML = '<p class="empty">Failed to generate templates. Check server connection.</p>';
    } finally {
        btnGenerateTemplates.disabled = selectedAssets.size === 0;
        btnGenerateTemplates.textContent = 'Generate Templates';
    }
}

// Copy template to clipboard
async function copyTemplateToClipboard(btn) {
    const template = btn.dataset.template;
    try {
        await navigator.clipboard.writeText(template);
        const originalText = btn.textContent;
        btn.textContent = 'Copied!';
        btn.classList.add('btn-success');
        setTimeout(() => {
            btn.textContent = originalText;
            btn.classList.remove('btn-success');
        }, 2000);
    } catch (error) {
        showToast('Failed to copy to clipboard', 'error');
    }
}

// Event listeners for Templates page
btnRefreshAssets?.addEventListener('click', loadTemplateAssets);
btnGenerateTemplates?.addEventListener('click', generateTemplates);

// =====================================================
// Settings Page
// =====================================================
const settingsEstopBox = document.getElementById('settings-estop-box');
const settingsEstopIndicator = document.getElementById('settings-estop-indicator');
const settingsEstopText = document.getElementById('settings-estop-text');
const estopLastChanged = document.getElementById('estop-last-changed');
const estopReason = document.getElementById('estop-reason');
const estopReasonInput = document.getElementById('estop-reason-input');
const settingsBtnEstopOn = document.getElementById('settings-btn-estop-on');
const settingsBtnEstopOff = document.getElementById('settings-btn-estop-off');

const sysDryRun = document.getElementById('sys-dry-run');
const sysOrderSubmit = document.getElementById('sys-order-submit');
const sysOrderPoll = document.getElementById('sys-order-poll');
const sysServerStatus = document.getElementById('sys-server-status');

const serverUrl = document.getElementById('server-url');
const connectionDot = document.getElementById('connection-dot');
const connectionText = document.getElementById('connection-text');
const connectionPing = document.getElementById('connection-ping');
const btnTestServer = document.getElementById('btn-test-server');
const btnSaveSettings = document.getElementById('btn-save-settings');
const btnOpenLogsSettings = document.getElementById('btn-open-logs-settings');
const btnExportDiagSettings = document.getElementById('btn-export-diag-settings');

// Load settings page data
async function loadSettingsData() {
    // Load E-STOP and system status via Tauri invoke (CORS 우회)
    try {
        const status = await invoke('get_server_status');

        // E-STOP status
        if (status.estop) {
            settingsEstopBox.className = 'estop-status-box active';
            settingsEstopText.textContent = 'E-STOP ACTIVE';
        } else {
            settingsEstopBox.className = 'estop-status-box inactive';
            settingsEstopText.textContent = 'Normal Operation';
        }

        estopLastChanged.textContent = '--';  // invoke에서는 timestamp 미제공
        estopReason.textContent = '--';

        // System status
        sysDryRun.textContent = status.dry_run ? 'ON' : 'OFF';
        sysDryRun.className = `status-value ${status.dry_run ? 'on' : 'off'}`;

        sysServerStatus.textContent = status.running ? 'Connected' : 'Disconnected';
        sysServerStatus.className = `status-value ${status.running ? 'on' : 'error'}`;

        sysOrderSubmit.textContent = status.running ? 'ON' : '--';
        sysOrderSubmit.className = `status-value ${status.running ? 'on' : 'off'}`;

        sysOrderPoll.textContent = status.running ? 'ON' : '--';
        sysOrderPoll.className = `status-value ${status.running ? 'on' : 'off'}`;
    } catch (error) {
        console.error('Failed to load settings status:', error);
        settingsEstopBox.className = 'estop-status-box inactive';
        settingsEstopText.textContent = 'Unknown';
    }
}

// E-STOP controls on Settings page (Tauri invoke 사용)
settingsBtnEstopOn?.addEventListener('click', async () => {
    const reason = estopReasonInput.value.trim() || 'Manual activation from PC App';

    if (!confirm(`E-STOP을 켜시겠습니까?\n\n사유: ${reason}\n\n모든 주문 전송이 차단됩니다.`)) {
        return;
    }

    settingsBtnEstopOn.disabled = true;
    try {
        await invoke('set_estop', { enabled: true });
        showToast('E-STOP activated', 'warning');
        estopReasonInput.value = '';
        loadSettingsData();
        updateStatus();
    } catch (error) {
        showToast('Failed to activate E-STOP', 'error');
    } finally {
        settingsBtnEstopOn.disabled = false;
    }
});

settingsBtnEstopOff?.addEventListener('click', async () => {
    settingsBtnEstopOff.disabled = true;
    try {
        await invoke('set_estop', { enabled: false });
        showToast('E-STOP deactivated', 'success');
        loadSettingsData();
        updateStatus();
    } catch (error) {
        showToast('Failed to deactivate E-STOP', 'error');
    } finally {
        settingsBtnEstopOff.disabled = false;
    }
});

// Test server connection
btnTestServer?.addEventListener('click', async () => {
    btnTestServer.disabled = true;
    btnTestServer.textContent = 'Testing...';
    connectionText.textContent = 'Testing...';
    connectionDot.className = 'status-dot';

    const url = serverUrl.value.trim();
    const startTime = Date.now();

    try {
        const response = await fetch(`${url}/api/diag/home`, {
            method: 'GET',
            signal: AbortSignal.timeout(5000)
        });

        const pingMs = Date.now() - startTime;

        if (response.ok) {
            connectionDot.className = 'status-dot connected';
            connectionText.textContent = 'Connected';
            connectionPing.textContent = `(${pingMs}ms)`;
            showToast('Connection successful', 'success');
        } else {
            throw new Error('Server responded with error');
        }
    } catch (error) {
        connectionDot.className = 'status-dot disconnected';
        connectionText.textContent = 'Connection failed';
        connectionPing.textContent = '';
        showToast('Connection failed', 'error');
    } finally {
        btnTestServer.disabled = false;
        btnTestServer.textContent = 'Test Connection';
    }
});

// Save settings
btnSaveSettings?.addEventListener('click', async () => {
    const url = serverUrl.value.trim();
    // In a real implementation, this would save to local storage or Tauri state
    localStorage.setItem('bbooster_server_url', url);
    showToast('Settings saved', 'success');
});

// Load saved server URL or use default from config
if (serverUrl) {
    const savedUrl = localStorage.getItem('bbooster_server_url');
    serverUrl.value = savedUrl || API_BASE_URL;
}

// Settings page buttons
btnOpenLogsSettings?.addEventListener('click', async () => {
    try {
        await invoke('open_logs_folder');
    } catch (error) {
        showToast('Failed to open logs folder', 'error');
    }
});

btnExportDiagSettings?.addEventListener('click', async () => {
    btnExportDiagSettings.disabled = true;
    btnExportDiagSettings.textContent = 'Exporting...';
    try {
        await invoke('export_diagnostic');
        showToast('Diagnostic exported', 'success');
    } catch (error) {
        showToast('Failed to export diagnostic', 'error');
    } finally {
        btnExportDiagSettings.disabled = false;
        btnExportDiagSettings.textContent = 'Export Diagnostic';
    }
});

// =====================================================
// Logs Page
// =====================================================
const logsCount = document.getElementById('logs-count');
const btnRefreshLogs = document.getElementById('btn-refresh-logs');
const btnExportCsv = document.getElementById('btn-export-csv');
const filterExchange = document.getElementById('filter-exchange');
const filterStatus = document.getElementById('filter-status');
const filterSymbol = document.getElementById('filter-symbol');
const filterLimit = document.getElementById('filter-limit');
const btnApplyFilters = document.getElementById('btn-apply-filters');
const logsTbody = document.getElementById('logs-tbody');

// Log detail modal
const logDetailModal = document.getElementById('log-detail-modal');
const logDetailClose = document.getElementById('log-detail-close');
const logDetailJson = document.getElementById('log-detail-json');
const btnCopyLogJson = document.getElementById('btn-copy-log-json');
const btnCloseLogDetail = document.getElementById('btn-close-log-detail');

let currentLogs = [];

// Load logs (Tauri invoke 사용 - CORS 우회)
async function loadLogs() {
    const limit = parseInt(filterLimit?.value || '100');

    try {
        // Tauri invoke로 타임라인 데이터 조회
        const data = await invoke('fetch_timeline', { limit: limit });

        if (Array.isArray(data) && data.length > 0) {
            currentLogs = data;
            logsCount.textContent = `${data.length} records`;

            logsTbody.innerHTML = data.map((log, index) => {
                const time = formatDateTime(log.timestamp || log.created_at);
                const exchangeVal = log.exchange || '--';
                const symbolVal = log.symbol || '--';
                const side = log.side || '--';
                const qty = log.qty || log.filled_qty || '--';
                const statusVal = log.event_type || log.status || 'unknown';
                const orderId = log.order_id || log.okx_order_id || '--';

                return `
                    <tr>
                        <td class="col-time">${time}</td>
                        <td>${exchangeVal}</td>
                        <td class="col-symbol">${symbolVal}</td>
                        <td class="col-side ${side.toLowerCase()}">${side.toUpperCase()}</td>
                        <td>${qty}</td>
                        <td><span class="col-status ${statusVal.toLowerCase()}">${statusVal}</span></td>
                        <td class="col-orderid">${orderId !== '--' ? orderId.slice(-8) : '--'}</td>
                        <td>
                            <button class="btn btn-secondary btn-view-detail" data-index="${index}">View</button>
                        </td>
                    </tr>
                `;
            }).join('');

            // Add event listeners for view buttons
            logsTbody.querySelectorAll('.btn-view-detail').forEach(btn => {
                btn.addEventListener('click', () => showLogDetail(parseInt(btn.dataset.index)));
            });
        } else {
            currentLogs = [];
            logsCount.textContent = '0 records';
            logsTbody.innerHTML = '<tr><td colspan="8" class="empty-cell">No logs found</td></tr>';
        }
    } catch (error) {
        console.error('Failed to load logs:', error);
        logsTbody.innerHTML = '<tr><td colspan="8" class="empty-cell">Failed to load logs. Check server connection.</td></tr>';
    }
}

// Show log detail modal
function showLogDetail(index) {
    const log = currentLogs[index];
    if (!log) return;

    logDetailJson.textContent = JSON.stringify(log, null, 2);
    logDetailModal.style.display = 'flex';
}

// Close log detail modal
function closeLogDetailModal() {
    logDetailModal.style.display = 'none';
}

logDetailClose?.addEventListener('click', closeLogDetailModal);
btnCloseLogDetail?.addEventListener('click', closeLogDetailModal);
logDetailModal?.addEventListener('click', (e) => {
    if (e.target === logDetailModal) closeLogDetailModal();
});

// Copy log JSON
btnCopyLogJson?.addEventListener('click', async () => {
    try {
        await navigator.clipboard.writeText(logDetailJson.textContent);
        showToast('Copied to clipboard', 'success');
    } catch (error) {
        showToast('Failed to copy', 'error');
    }
});

// Refresh logs
btnRefreshLogs?.addEventListener('click', loadLogs);

// Apply filters
btnApplyFilters?.addEventListener('click', loadLogs);

// Export CSV
btnExportCsv?.addEventListener('click', async () => {
    if (currentLogs.length === 0) {
        showToast('No logs to export', 'warning');
        return;
    }

    btnExportCsv.disabled = true;
    btnExportCsv.textContent = 'Exporting...';

    try {
        // Create CSV content
        const headers = ['Time', 'Exchange', 'Symbol', 'Side', 'Qty', 'Status', 'Order ID', 'Message'];
        const rows = currentLogs.map(log => [
            log.timestamp || log.created_at || '',
            log.exchange || '',
            log.symbol || '',
            log.side || '',
            log.qty || log.filled_qty || '',
            log.event_type || log.status || '',
            log.order_id || log.okx_order_id || '',
            log.message || ''
        ]);

        const csvContent = [
            headers.join(','),
            ...rows.map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
        ].join('\n');

        // Create blob and download
        const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `bbooster_logs_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        showToast('CSV exported successfully', 'success');
    } catch (error) {
        console.error('Failed to export CSV:', error);
        showToast('Failed to export CSV', 'error');
    } finally {
        btnExportCsv.disabled = false;
        btnExportCsv.textContent = 'Export CSV';
    }
});

// =====================================================
// Connection Check with Loading Screen (Tauri invoke 사용)
// =====================================================
async function checkServerConnection() {
    const loadingOverlay = document.getElementById('loading-overlay');
    const loadingMessage = document.getElementById('loading-message');
    const retryBtn = document.getElementById('btn-retry-connection');

    if (loadingOverlay) loadingOverlay.style.display = 'flex';
    if (loadingMessage) loadingMessage.textContent = '서버 연결 중...';
    if (retryBtn) retryBtn.style.display = 'none';

    try {
        // Tauri invoke를 통해 Rust에서 HTTP 요청 (CORS 우회)
        const result = await invoke('check_server_health');

        if (result.ok) {
            isConnected = true;
            retryCount = 0;
            if (loadingOverlay) loadingOverlay.style.display = 'none';
            console.log(`서버 연결 성공 (${result.latency_ms}ms)`);
            updateStatus();
            return true;
        }
        throw new Error(result.message || 'Server not responding');
    } catch (error) {
        console.error('Connection failed:', error);
        isConnected = false;
        retryCount++;

        if (loadingMessage) {
            loadingMessage.textContent = '서버에 연결할 수 없습니다.\n네트워크를 확인해주세요.';
        }
        if (retryBtn) retryBtn.style.display = 'block';

        // Auto retry
        if (retryCount < MAX_RETRIES) {
            if (loadingMessage) {
                loadingMessage.textContent = `연결 재시도 중... (${retryCount}/${MAX_RETRIES})`;
            }
            setTimeout(checkServerConnection, 3000);
        }
        return false;
    }
}

// Retry button handler
document.getElementById('btn-retry-connection')?.addEventListener('click', () => {
    retryCount = 0;
    checkServerConnection();
});

// =====================================================
// Subscription Type Management
// =====================================================
const SUBSCRIPTION_TYPES = {
    free: {
        name: '무료',
        icon: '⭐',
        class: 'free',
        features: ['basic', 'webhook'],
        description: '기본 기능을 무료로 사용하세요. 허브형(개인 서버)으로 운영됩니다.'
    },
    hub: {
        name: '허브형',
        icon: '🏠',
        class: 'hub',
        features: ['basic', 'webhook', 'multi-account'],
        description: '개인 서버에서 운영하는 허브형 사용자입니다. 무제한 계정을 등록할 수 있습니다.'
    },
    premium: {
        name: '프리미엄',
        icon: '👑',
        class: 'premium',
        features: ['basic', 'webhook', 'multi-account', 'premium-signals', 'cloud-sync', 'priority-support'],
        description: '클라우드 기반 프리미엄 서비스입니다. 모든 기능과 우선 지원을 받으세요.'
    }
};

let currentSubscription = 'free';

async function loadSubscriptionStatus() {
    try {
        // Tauri invoke 사용 (CORS 우회)
        const data = await invoke('fetch_subscription');
        if (data && data.plan) {
            currentSubscription = data.plan.toLowerCase() === 'premium' ? 'premium' :
                                  data.plan.toLowerCase() === 'hub' ? 'hub' : 'free';
        }
    } catch (error) {
        console.log('Subscription status not available, defaulting to free');
        currentSubscription = 'free';
    }
    updateSubscriptionUI();
}

function updateSubscriptionUI() {
    const subType = SUBSCRIPTION_TYPES[currentSubscription] || SUBSCRIPTION_TYPES.free;

    // Update sidebar badge
    const badge = document.getElementById('subscription-badge');
    const badgeText = document.getElementById('subscription-text');
    if (badge) {
        badge.className = `subscription-badge ${subType.class}`;
        badge.querySelector('.badge-icon').textContent = subType.icon;
    }
    if (badgeText) {
        badgeText.textContent = subType.name;
    }

    // Update subscription card in settings
    const subCard = document.getElementById('subscription-card');
    const subTypeBadge = document.getElementById('sub-type-badge');
    const subDescription = document.getElementById('sub-description-text');
    const upgradeBtn = document.getElementById('btn-upgrade');

    if (subCard) {
        subCard.className = `subscription-card ${subType.class}`;
    }
    if (subTypeBadge) {
        subTypeBadge.textContent = subType.name;
        subTypeBadge.className = `sub-type-badge ${subType.class}`;
    }
    if (subDescription) {
        subDescription.textContent = subType.description;
    }
    if (upgradeBtn) {
        upgradeBtn.style.display = currentSubscription === 'premium' ? 'none' : 'block';
    }

    // Update feature checks
    const featureMap = {
        'feat-multi-account': 'multi-account',
        'feat-premium-signals': 'premium-signals',
        'feat-cloud-sync': 'cloud-sync',
        'feat-priority-support': 'priority-support'
    };

    for (const [elemId, featureKey] of Object.entries(featureMap)) {
        const elem = document.getElementById(elemId);
        if (elem) {
            const hasFeature = subType.features.includes(featureKey);
            const icon = elem.querySelector('span:first-child');
            if (icon) {
                icon.textContent = hasFeature ? '✓' : '✕';
                icon.className = hasFeature ? 'check' : 'cross';
            }
        }
    }
}

// Sidebar badge click to go to settings
document.getElementById('subscription-badge')?.addEventListener('click', () => {
    navigateTo('settings');
});

// =====================================================
// Payment System UI
// =====================================================
const PLANS = {
    hub: { name: '허브형', price: '₩29,000' },
    premium: { name: '프리미엄', price: '₩99,000' }
};

let selectedPlan = null;

function openPaymentModal(planType) {
    selectedPlan = planType;
    const plan = PLANS[planType];
    if (!plan) return;

    document.getElementById('selected-plan-name').textContent = plan.name;
    document.getElementById('selected-plan-price').textContent = plan.price;
    document.getElementById('payment-modal').style.display = 'flex';
}

function closePaymentModal() {
    document.getElementById('payment-modal').style.display = 'none';
    selectedPlan = null;
}

async function processPayment() {
    const email = document.getElementById('payment-email').value;
    const agreeTerms = document.getElementById('agree-terms').checked;
    const paymentMethod = document.querySelector('input[name="payment-method"]:checked')?.value;

    if (!email) {
        showToast('이메일을 입력해주세요.', 'error');
        return;
    }

    if (!agreeTerms) {
        showToast('약관에 동의해주세요.', 'error');
        return;
    }

    // In a real implementation, this would integrate with a payment gateway
    // For now, just show a message that payment processing would happen here
    showToast(`${PLANS[selectedPlan].name} 플랜 결제 처리 중... (데모)`, 'success');

    // Simulate payment processing
    setTimeout(() => {
        showToast('결제 시스템은 추후 연동 예정입니다.', 'warning');
        closePaymentModal();
    }, 2000);
}

// Payment modal event listeners
document.getElementById('btn-subscribe-hub')?.addEventListener('click', () => openPaymentModal('hub'));
document.getElementById('btn-subscribe-premium')?.addEventListener('click', () => openPaymentModal('premium'));
document.getElementById('payment-modal-close')?.addEventListener('click', closePaymentModal);
document.getElementById('btn-cancel-payment')?.addEventListener('click', closePaymentModal);
document.getElementById('btn-confirm-payment')?.addEventListener('click', processPayment);

// Close modal on backdrop click
document.getElementById('payment-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'payment-modal') {
        closePaymentModal();
    }
});

// =====================================================
// Initialize
// =====================================================
(async () => {
    console.log('='.repeat(50));
    console.log('[Init] BBooster PC App 시작');
    console.log('[Init] API 서버:', API_BASE_URL);
    console.log('[Init] 현재 localStorage 상태:');
    console.log('  - access_token:', localStorage.getItem('bbooster_access_token') ? '있음' : '없음');
    console.log('  - refresh_token:', localStorage.getItem('bbooster_refresh_token') ? '있음' : '없음');
    console.log('  - hub_mode:', localStorage.getItem('bbooster_hub_mode'));
    console.log('='.repeat(50));

    // 1. 인증 상태 확인 (로그인 화면 또는 대시보드 결정)
    const isAuthenticated = await initAuth();
    console.log('[Init] 최종 인증 결과:', isAuthenticated ? '✓ 인증됨' : '✗ 로그인 필요');

    // 2. 인증된 경우에만 서버 연결 체크 및 데이터 로드
    if (isAuthenticated) {
        console.log('[Init] 서버 연결 체크 시작...');
        checkServerConnection();

        // 구독 상태 로드 (연결 후)
        setTimeout(() => {
            if (isConnected) {
                loadSubscriptionStatus();
            }
        }, 2000);
    } else {
        console.log('[Init] 로그인 화면에서 사용자 입력 대기 중...');
        // 로그인 화면이 이미 ensureLoginScreenVisible()에서 표시됨
    }
})();

// Periodic status update (every 5 seconds)
setInterval(() => {
    if (isConnected) {
        updateStatus();
    }
}, 5000);

// Load accounts when page loads if on accounts page
if (document.querySelector('.nav-item[data-page="accounts"].active')) {
    loadAccounts();
}
