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
    isHubMode: false,

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
// DOM Elements
// =====================================================
const loginScreen = document.getElementById('login-screen');
const appElement = document.getElementById('app');
const btnGoogleLogin = document.getElementById('btn-google-login');
const btnSkipLogin = document.getElementById('btn-skip-login');

// =====================================================
// Login Screen Functions
// =====================================================
function ensureLoginScreenVisible() {
    if (loginScreen) loginScreen.style.cssText = 'display: flex !important';
    if (appElement) appElement.style.cssText = 'display: none !important';
}

function showLoginScreen() {
    if (loginScreen) loginScreen.style.cssText = 'display: flex !important';
    if (appElement) appElement.style.cssText = 'display: none !important';
}

function hideLoginScreen() {
    if (loginScreen) loginScreen.style.cssText = 'display: none !important';
    if (appElement) appElement.style.cssText = 'display: flex !important';
}

ensureLoginScreenVisible();

// Google Login
async function loginWithGoogle() {
    try {
        await open(`${API_BASE_URL}/api/auth/google/login`);
        showToast('브라우저에서 로그인을 완료해주세요', 'info');
        startLoginPolling();
    } catch (error) {
        showToast('로그인 페이지를 열 수 없습니다', 'error');
    }
}

let loginPollingInterval = null;
function startLoginPolling() {
    if (loginPollingInterval) clearInterval(loginPollingInterval);
    let attempts = 0;
    const maxAttempts = 60;

    loginPollingInterval = setInterval(async () => {
        attempts++;
        auth.loadTokens();
        if (auth.accessToken) {
            clearInterval(loginPollingInterval);
            loginPollingInterval = null;
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

function skipLogin() {
    auth.setHubMode(true);
    hideLoginScreen();
    updateUserUI({ name: '허브 모드', plan: 'hub', role: 'user' });
    showToast('허브 모드로 시작합니다', 'info');
    checkServerConnection();
}

// Email Login/Register
const emailLoginForm = document.getElementById('email-login-form');
const emailRegisterForm = document.getElementById('email-register-form');
const loginTitle = document.getElementById('login-title');
const showRegisterLink = document.getElementById('show-register');
const showLoginLink = document.getElementById('show-login');
const btnEmailLogin = document.getElementById('btn-email-login');
const btnEmailRegister = document.getElementById('btn-email-register');

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
        const data = await invoke('login_with_email', { email, password });
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
        const data = await invoke('register_with_email', { email, password, name: name || null });
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

showRegisterLink?.addEventListener('click', showEmailRegisterForm);
showLoginLink?.addEventListener('click', showEmailLoginForm);
btnEmailLogin?.addEventListener('click', handleEmailLogin);
btnEmailRegister?.addEventListener('click', handleEmailRegister);
document.getElementById('login-password')?.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleEmailLogin(); });
document.getElementById('register-password-confirm')?.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleEmailRegister(); });

async function loadUserInfo() {
    if (!auth.accessToken) return;
    try {
        const user = await invoke('get_user_info', { accessToken: auth.accessToken });
        auth.user = user;
        updateUserUI(auth.user);

        // Show admin menus if admin
        if (user.role === 'admin') {
            document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'block');
        }
    } catch (error) {
        console.error('Failed to load user info:', error);
        if (String(error).includes('401') || String(error).includes('Unauthorized')) {
            await refreshAuthToken();
        }
    }
}

async function refreshAuthToken() {
    const success = await tryRefreshToken();
    if (!success) {
        showLoginScreen();
    }
}

function updateUserUI(user) {
    const badge = document.getElementById('subscription-badge');
    const badgeText = document.getElementById('subscription-text');

    if (user.plan === 'premium') {
        if (badge) badge.className = 'subscription-badge premium';
        if (badgeText) badgeText.textContent = '프리미엄';
    } else if (user.plan === 'hub') {
        if (badge) badge.className = 'subscription-badge hub';
        if (badgeText) badgeText.textContent = '허브형';
    } else {
        if (badge) badge.className = 'subscription-badge free';
        if (badgeText) badgeText.textContent = '무료';
    }
}

function logout() {
    localStorage.removeItem('bbooster_access_token');
    localStorage.removeItem('bbooster_refresh_token');
    localStorage.removeItem('bbooster_hub_mode');
    window.location.reload();
}

document.getElementById('btn-logout')?.addEventListener('click', logout);

async function initAuth() {
    ensureLoginScreenVisible();
    auth.loadTokens();

    if (auth.isHubMode) {
        hideLoginScreen();
        updateUserUI({ name: '허브 모드', plan: 'hub', role: 'user' });
        return true;
    }

    if (!auth.accessToken) {
        return false;
    }

    try {
        const user = await invoke('get_user_info', { accessToken: auth.accessToken });
        auth.user = user;
        updateUserUI(auth.user);
        if (user.role === 'admin') {
            document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'block');
        }
        hideLoginScreen();
        return true;
    } catch (error) {
        const refreshed = await tryRefreshToken();
        if (refreshed) {
            hideLoginScreen();
            return true;
        }
    }

    auth.clearTokens();
    return false;
}

async function tryRefreshToken() {
    if (!auth.refreshToken) return false;
    try {
        const tokens = await invoke('refresh_auth_token', { refreshToken: auth.refreshToken });
        auth.saveTokens(tokens.access_token, tokens.refresh_token);
        await loadUserInfo();
        return true;
    } catch (error) {
        console.error('Token refresh failed:', error);
    }
    auth.clearTokens();
    return false;
}

btnGoogleLogin?.addEventListener('click', loginWithGoogle);
btnSkipLogin?.addEventListener('click', skipLogin);

// =====================================================
// Navigation - New Structure
// =====================================================
const navItems = document.querySelectorAll('.nav-item');
const pageTitle = document.getElementById('page-title');

const pageTitles = {
    home: '홈',
    'tv-connect': 'TV 전략연결',
    symbols: '심볼정보',
    'premium-strategy': '프리미엄 전략',
    accounts: '계정관리',
    notifications: '알림설정',
    'app-info': '앱정보',
    'admin-users': '사용자관리',
    'admin-system': '시스템상태'
};

navItems.forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        const page = item.dataset.page;
        navigateTo(page);
    });
});

window.navigateTo = function(page) {
    navItems.forEach(nav => {
        nav.classList.toggle('active', nav.dataset.page === page);
    });

    if (pageTitle) pageTitle.textContent = pageTitles[page] || page;

    document.querySelectorAll('.page-content').forEach(pageEl => {
        pageEl.style.display = 'none';
    });
    const targetPage = document.getElementById(`page-${page}`);
    if (targetPage) {
        targetPage.style.display = 'block';
    }

    // Page-specific initialization
    if (page === 'home') loadHomePage();
    else if (page === 'tv-connect') loadTVConnectPage();
    else if (page === 'symbols') loadSymbolsPage();
    else if (page === 'premium-strategy') loadPremiumStrategyPage();
    else if (page === 'accounts') loadAccountsPage();
    else if (page === 'app-info') loadAppInfoPage();
    else if (page === 'admin-users') loadAdminUsersPage();
    else if (page === 'admin-system') loadAdminSystemPage();
};

// =====================================================
// Toast Notifications
// =====================================================
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}

// =====================================================
// Connection Check
// =====================================================
let isConnected = false;
let retryCount = 0;

async function checkServerConnection() {
    const loadingOverlay = document.getElementById('loading-overlay');
    const loadingMessage = document.getElementById('loading-message');
    const retryBtn = document.getElementById('btn-retry-connection');

    if (loadingOverlay) loadingOverlay.style.display = 'flex';
    if (loadingMessage) loadingMessage.textContent = '서버 연결 중...';
    if (retryBtn) retryBtn.style.display = 'none';

    try {
        const result = await invoke('check_server_health');
        if (result.ok) {
            isConnected = true;
            retryCount = 0;
            if (loadingOverlay) loadingOverlay.style.display = 'none';
            updateServerStatus(true);
            loadHomePage();
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

        if (retryCount < MAX_RETRIES) {
            if (loadingMessage) {
                loadingMessage.textContent = `연결 재시도 중... (${retryCount}/${MAX_RETRIES})`;
            }
            setTimeout(checkServerConnection, 3000);
        }
        return false;
    }
}

document.getElementById('btn-retry-connection')?.addEventListener('click', () => {
    retryCount = 0;
    checkServerConnection();
});

function updateServerStatus(connected) {
    const serverStatus = document.getElementById('server-status');
    const lightServer = document.getElementById('light-server');

    if (connected) {
        if (serverStatus) serverStatus.textContent = '서버: 연결됨';
        if (lightServer) lightServer.className = 'status-light green';
    } else {
        if (serverStatus) serverStatus.textContent = '서버: 오프라인';
        if (lightServer) lightServer.className = 'status-light red';
    }
}

// =====================================================
// Home Page (PHASE 3)
// =====================================================
let profitChart = null;
let allocationChart = null;

async function loadHomePage() {
    // Initialize charts
    initProfitChart();
    initAllocationChart();

    // Load data (dummy for now)
    try {
        const status = await invoke('get_server_status');
        updateServerStatus(status.running);
    } catch (e) {
        console.error('Failed to get server status:', e);
    }
}

function initProfitChart() {
    const ctx = document.getElementById('profit-chart');
    if (!ctx) return;

    if (profitChart) profitChart.destroy();

    // Dummy data
    const labels = ['1/1', '1/2', '1/3', '1/4', '1/5', '1/6', '1/7'];
    const data = [0, 1.2, 0.8, 2.1, 1.8, 2.5, 3.2];

    profitChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '수익률 (%)',
                data: data,
                borderColor: '#22C55E',
                backgroundColor: 'rgba(34, 197, 94, 0.1)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    grid: { color: 'rgba(255,255,255,0.1)' },
                    ticks: { color: '#9CA3AF' }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#9CA3AF' }
                }
            }
        }
    });
}

function initAllocationChart() {
    const ctx = document.getElementById('allocation-chart');
    if (!ctx) return;

    if (allocationChart) allocationChart.destroy();

    allocationChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['국내주식', '해외주식', '암호화폐', '현금'],
            datasets: [{
                data: [0, 0, 0, 100],
                backgroundColor: ['#3B82F6', '#8B5CF6', '#F59E0B', '#6B7280']
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// Period tabs
document.querySelectorAll('.period-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.period-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        // Reload chart with new period data
    });
});

// Emergency stop button
document.getElementById('btn-emergency-stop')?.addEventListener('click', async () => {
    if (!confirm('긴급 정지를 실행하시겠습니까?\n\n모든 주문 전송이 즉시 차단됩니다.')) return;

    try {
        await invoke('set_estop', { enabled: true });
        showToast('긴급 정지가 활성화되었습니다', 'warning');
    } catch (error) {
        showToast('긴급 정지 실패: ' + error, 'error');
    }
});

// =====================================================
// TV Connect Page (PHASE 4)
// =====================================================
let selectedExchange = null;
let selectedSymbol = null;
let tvWizardStep = 1;

async function loadTVConnectPage() {
    loadExchangeSelection();
    loadWebhookLogs();
    updateTVWizardUI(1);
}

async function loadExchangeSelection() {
    const container = document.getElementById('exchange-selection');
    if (!container) return;

    try {
        let accounts = [];
        if (auth.accessToken) {
            accounts = await invoke('get_accounts_list', { accessToken: auth.accessToken });
        }

        if (accounts.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>등록된 거래소 계정이 없습니다.</p>
                    <button class="btn btn-primary" onclick="navigateTo('accounts')">계정 등록하기</button>
                </div>
            `;
            return;
        }

        container.innerHTML = accounts.map(acc => `
            <div class="exchange-card" data-exchange="${acc.exchange}" data-name="${acc.name}">
                <div class="exchange-icon">${acc.exchange === 'OKX' ? '🪙' : '📈'}</div>
                <div class="exchange-name">${acc.name}</div>
                <div class="exchange-type">${acc.exchange}</div>
            </div>
        `).join('');

        container.querySelectorAll('.exchange-card').forEach(card => {
            card.addEventListener('click', () => {
                container.querySelectorAll('.exchange-card').forEach(c => c.classList.remove('selected'));
                card.classList.add('selected');
                selectedExchange = { exchange: card.dataset.exchange, name: card.dataset.name };
                document.getElementById('btn-tv-next-1').disabled = false;
            });
        });
    } catch (error) {
        container.innerHTML = '<p class="empty">계정 로딩 실패</p>';
    }
}

async function loadWebhookLogs() {
    const tbody = document.getElementById('webhook-logs-tbody');
    if (!tbody) return;

    try {
        // For now, show empty state - will be implemented with backend
        tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">최근 수신 웹훅 없음</td></tr>';
    } catch (error) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">로그 로딩 실패</td></tr>';
    }
}

function updateTVWizardUI(step) {
    tvWizardStep = step;

    document.querySelectorAll('.wizard-step').forEach(stepEl => {
        const stepNum = parseInt(stepEl.dataset.step);
        stepEl.classList.remove('active', 'completed');
        if (stepNum === step) stepEl.classList.add('active');
        else if (stepNum < step) stepEl.classList.add('completed');
    });

    for (let i = 1; i <= 4; i++) {
        const content = document.getElementById(`tv-step-${i}`);
        if (content) content.style.display = i === step ? 'block' : 'none';
    }
}

function generateTemplate() {
    const side = document.getElementById('tv-side')?.value || 'buy';
    const qtyType = document.getElementById('tv-qty-type')?.value || 'percent';
    const qty = document.getElementById('tv-qty')?.value || 100;
    const orderType = document.getElementById('tv-order-type')?.value || 'market';
    const leverage = document.getElementById('tv-leverage')?.value || 1;
    const sl = document.getElementById('tv-sl')?.value;
    const tp = document.getElementById('tv-tp')?.value;

    const template = {
        action: side,
        symbol: selectedSymbol || 'BTC-USDT',
        exchange: selectedExchange?.exchange || 'OKX',
        qty_type: qtyType,
        qty: parseFloat(qty),
        order_type: orderType,
        leverage: parseInt(leverage)
    };

    if (sl) template.sl = parseFloat(sl);
    if (tp) template.tp = parseFloat(tp);

    return JSON.stringify(template, null, 2);
}

// TV Wizard navigation
document.getElementById('btn-tv-next-1')?.addEventListener('click', () => updateTVWizardUI(2));
document.getElementById('btn-tv-prev-2')?.addEventListener('click', () => updateTVWizardUI(1));
document.getElementById('btn-tv-next-2')?.addEventListener('click', () => updateTVWizardUI(3));
document.getElementById('btn-tv-prev-3')?.addEventListener('click', () => updateTVWizardUI(2));
document.getElementById('btn-tv-next-3')?.addEventListener('click', () => {
    const templateCode = document.getElementById('template-code');
    if (templateCode) templateCode.textContent = generateTemplate();

    const webhookUrl = document.getElementById('webhook-url');
    if (webhookUrl && auth.user) {
        webhookUrl.textContent = `https://qube-system.com/api/webhook/${auth.user.id || 'USER_ID'}`;
    }

    updateTVWizardUI(4);
});
document.getElementById('btn-tv-prev-4')?.addEventListener('click', () => updateTVWizardUI(3));
document.getElementById('btn-tv-restart')?.addEventListener('click', () => {
    selectedExchange = null;
    selectedSymbol = null;
    document.querySelectorAll('.exchange-card').forEach(c => c.classList.remove('selected'));
    document.getElementById('btn-tv-next-1').disabled = true;
    updateTVWizardUI(1);
});

document.getElementById('btn-copy-template')?.addEventListener('click', async () => {
    const code = document.getElementById('template-code')?.textContent;
    if (code) {
        await navigator.clipboard.writeText(code);
        showToast('템플릿이 복사되었습니다', 'success');
    }
});

document.getElementById('btn-copy-webhook-url')?.addEventListener('click', async () => {
    const url = document.getElementById('webhook-url')?.textContent;
    if (url) {
        await navigator.clipboard.writeText(url);
        showToast('웹훅 URL이 복사되었습니다', 'success');
    }
});

document.getElementById('btn-refresh-webhook-logs')?.addEventListener('click', loadWebhookLogs);

// Asset tags
document.querySelectorAll('.asset-tag').forEach(tag => {
    tag.addEventListener('click', () => {
        selectedSymbol = tag.dataset.symbol;
        document.getElementById('btn-tv-next-2').disabled = false;
        showToast(`${selectedSymbol} 선택됨`, 'info');
    });
});

// =====================================================
// Symbols Page (PHASE 5)
// =====================================================
async function loadSymbolsPage() {
    // Check user plan
    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';

    if (plan === 'free' && role !== 'admin') {
        document.getElementById('symbols-restriction').style.display = 'flex';
        return;
    }

    document.getElementById('symbols-restriction').style.display = 'none';
    loadPopularSymbols();
}

async function loadPopularSymbols() {
    const tbody = document.getElementById('symbols-tbody');
    if (!tbody) return;

    // Dummy data for popular symbols
    const symbols = [
        { symbol: 'BTC-USDT', name: 'Bitcoin', exchange: 'OKX', price: '$97,234.50', change: '+2.34%', volume: '1.2B' },
        { symbol: 'ETH-USDT', name: 'Ethereum', exchange: 'OKX', price: '$3,456.78', change: '+1.23%', volume: '890M' },
        { symbol: 'SOL-USDT', name: 'Solana', exchange: 'OKX', price: '$198.45', change: '-0.89%', volume: '456M' }
    ];

    tbody.innerHTML = symbols.map(s => `
        <tr data-symbol="${s.symbol}">
            <td><strong>${s.symbol}</strong></td>
            <td>${s.name}</td>
            <td><span class="exchange-badge">${s.exchange}</span></td>
            <td>${s.price}</td>
            <td class="${s.change.startsWith('+') ? 'profit' : 'loss'}">${s.change}</td>
            <td>${s.volume}</td>
        </tr>
    `).join('');

    tbody.querySelectorAll('tr').forEach(row => {
        row.addEventListener('click', () => showSymbolDetail(row.dataset.symbol));
    });
}

function showSymbolDetail(symbol) {
    const panel = document.getElementById('symbol-detail-panel');
    if (!panel) return;

    document.getElementById('detail-symbol-name').textContent = symbol;
    panel.style.display = 'block';
}

document.getElementById('btn-close-detail')?.addEventListener('click', () => {
    document.getElementById('symbol-detail-panel').style.display = 'none';
});

document.getElementById('btn-set-strategy-symbol')?.addEventListener('click', () => {
    const symbol = document.getElementById('detail-symbol-name')?.textContent;
    selectedSymbol = symbol;
    navigateTo('premium-strategy');
    showToast(`${symbol}으로 전략 설정 페이지로 이동`, 'info');
});

document.querySelectorAll('.symbol-tag').forEach(tag => {
    tag.addEventListener('click', () => {
        document.getElementById('symbol-search').value = tag.dataset.symbol;
        loadPopularSymbols(); // Would search in real implementation
    });
});

document.querySelectorAll('.filter-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        // Filter by exchange
    });
});

// =====================================================
// Premium Strategy Page (PHASE 6)
// =====================================================
let backtestChart = null;

async function loadPremiumStrategyPage() {
    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';

    if (plan !== 'premium' && role !== 'admin') {
        document.getElementById('premium-restriction').style.display = 'flex';
        return;
    }

    document.getElementById('premium-restriction').style.display = 'none';
    loadStrategies();
    loadExchangeDropdowns();
}

async function loadStrategies() {
    const list = document.getElementById('strategies-list');
    if (!list) return;

    // Dummy - would load from backend
    list.innerHTML = `
        <div class="empty-state">
            <p>설정된 전략이 없습니다.</p>
            <p>커스텀/역추세/추세 탭에서 전략을 추가하세요.</p>
        </div>
    `;
}

async function loadExchangeDropdowns() {
    const selects = ['custom-exchange', 'reversal-exchange', 'trend-exchange'];

    try {
        let accounts = [];
        if (auth.accessToken) {
            accounts = await invoke('get_accounts_list', { accessToken: auth.accessToken });
        }

        selects.forEach(id => {
            const select = document.getElementById(id);
            if (select) {
                select.innerHTML = '<option value="">선택하세요</option>';
                accounts.forEach(acc => {
                    select.innerHTML += `<option value="${acc.exchange}">${acc.name} (${acc.exchange})</option>`;
                });
            }
        });
    } catch (e) {
        console.error('Failed to load exchanges:', e);
    }
}

// Strategy tabs
document.querySelectorAll('.strategy-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.strategy-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');

        document.querySelectorAll('.strategy-content').forEach(c => c.style.display = 'none');
        document.getElementById(`strategy-tab-${tab.dataset.tab}`).style.display = 'block';
    });
});

// Sliders
['reversal-rsi-period', 'reversal-overbought', 'reversal-oversold', 'trend-short-ma', 'trend-long-ma'].forEach(id => {
    const slider = document.getElementById(id);
    if (slider) {
        slider.addEventListener('input', () => {
            document.getElementById(`${id}-val`).textContent = slider.value;
        });
    }
});

// Backtest buttons
document.getElementById('btn-run-backtest')?.addEventListener('click', runBacktest);
document.getElementById('btn-backtest-reversal')?.addEventListener('click', runBacktest);
document.getElementById('btn-backtest-trend')?.addEventListener('click', runBacktest);

async function runBacktest() {
    showToast('백테스팅 실행 중...', 'info');

    // Simulate backtest
    setTimeout(() => {
        const result = document.getElementById('backtest-result');
        if (result) {
            result.style.display = 'block';

            // Update results
            document.getElementById('bt-total-return').textContent = '+45.23%';
            document.getElementById('bt-cagr').textContent = '+8.12%';
            document.getElementById('bt-mdd').textContent = '-15.67%';
            document.getElementById('bt-sharpe').textContent = '1.45';
            document.getElementById('bt-winrate').textContent = '58.3%';
            document.getElementById('bt-trades').textContent = '42회';

            initBacktestChart();
        }
        showToast('백테스팅 완료', 'success');
    }, 2000);
}

function initBacktestChart() {
    const ctx = document.getElementById('backtest-chart');
    if (!ctx) return;

    if (backtestChart) backtestChart.destroy();

    const labels = [];
    const data = [];
    let equity = 10000000;

    for (let i = 0; i < 100; i++) {
        labels.push(`Day ${i}`);
        equity *= (1 + (Math.random() - 0.45) * 0.02);
        data.push(equity);
    }

    backtestChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '자산',
                data: data,
                borderColor: '#22C55E',
                fill: false,
                tension: 0.1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#9CA3AF' } },
                x: { display: false }
            }
        }
    });
}

document.getElementById('btn-activate-strategy')?.addEventListener('click', () => {
    showToast('전략이 활성화되었습니다', 'success');
    document.querySelectorAll('.strategy-tab')[0].click();
});

// =====================================================
// Accounts Page (PHASE 7)
// =====================================================
let accountVerified = false;
let verifyTimer = null;

async function loadAccountsPage() {
    if (!auth.isHubMode && !accountVerified) {
        // Show password verification modal
        document.getElementById('password-verify-modal').style.display = 'flex';
        return;
    }

    loadAccountsList();
}

document.getElementById('btn-verify-password')?.addEventListener('click', async () => {
    const password = document.getElementById('verify-password')?.value;
    if (!password) {
        document.getElementById('verify-error').textContent = '비밀번호를 입력하세요';
        return;
    }

    try {
        // Verify password via backend
        await invoke('verify_password', { accessToken: auth.accessToken, password });
        accountVerified = true;
        document.getElementById('password-verify-modal').style.display = 'none';
        loadAccountsList();

        // Set 5 minute timer
        const timerEl = document.getElementById('verify-timer');
        let seconds = 300;
        verifyTimer = setInterval(() => {
            seconds--;
            if (timerEl) timerEl.textContent = `접근 만료까지: ${Math.floor(seconds/60)}:${(seconds%60).toString().padStart(2,'0')}`;
            if (seconds <= 0) {
                clearInterval(verifyTimer);
                accountVerified = false;
            }
        }, 1000);

    } catch (error) {
        document.getElementById('verify-error').textContent = '비밀번호가 올바르지 않습니다';
    }
});

async function loadAccountsList() {
    const list = document.getElementById('accounts-list');
    if (!list) return;

    try {
        let accounts = [];
        if (auth.accessToken) {
            accounts = await invoke('get_accounts_list', { accessToken: auth.accessToken });
        }

        if (accounts.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <p>등록된 계정이 없습니다.</p>
                    <p>계정 추가 버튼을 클릭하여 거래소를 연결하세요.</p>
                </div>
            `;
            return;
        }

        list.innerHTML = accounts.map(acc => `
            <div class="account-card">
                <div class="account-card-header">
                    <div class="account-info">
                        <h3>${acc.name}</h3>
                        <span class="exchange-badge ${acc.exchange.toLowerCase()}">${acc.exchange}</span>
                    </div>
                    <span class="account-status ${acc.is_active ? 'active' : 'inactive'}">
                        ${acc.is_active ? '● 연결됨' : '○ 미연결'}
                    </span>
                </div>
                <div class="account-card-body">
                    <div class="account-detail">
                        <span>API Key</span>
                        <span>****${acc.has_keys ? '(저장됨)' : '(미설정)'}</span>
                    </div>
                </div>
                <div class="account-card-actions">
                    <button class="btn btn-secondary btn-test" data-name="${acc.name}" data-exchange="${acc.exchange}">연결 테스트</button>
                    <button class="btn btn-danger btn-delete" data-id="${acc.id}" data-name="${acc.name}">삭제</button>
                </div>
            </div>
        `).join('');

        list.querySelectorAll('.btn-test').forEach(btn => {
            btn.addEventListener('click', async () => {
                btn.disabled = true;
                btn.textContent = '테스트 중...';
                try {
                    await invoke('test_account_connection', { exchange: btn.dataset.exchange, accountName: btn.dataset.name });
                    showToast('연결 성공', 'success');
                } catch (e) {
                    showToast('연결 실패: ' + e, 'error');
                }
                btn.disabled = false;
                btn.textContent = '연결 테스트';
            });
        });

        list.querySelectorAll('.btn-delete').forEach(btn => {
            btn.addEventListener('click', async () => {
                if (!confirm(`${btn.dataset.name} 계정을 삭제하시겠습니까?`)) return;
                try {
                    await invoke('delete_api_key', { accessToken: auth.accessToken, accountId: parseInt(btn.dataset.id), accountName: btn.dataset.name, exchange: btn.dataset.exchange });
                    showToast('계정이 삭제되었습니다', 'success');
                    loadAccountsList();
                } catch (e) {
                    showToast('삭제 실패: ' + e, 'error');
                }
            });
        });

    } catch (error) {
        list.innerHTML = '<p class="empty">계정 로딩 실패</p>';
    }
}

// Account form
document.getElementById('btn-add-account')?.addEventListener('click', () => {
    document.getElementById('account-form-section').style.display = 'block';
});

document.getElementById('btn-cancel-account')?.addEventListener('click', () => {
    document.getElementById('account-form-section').style.display = 'none';
});

document.getElementById('account-exchange')?.addEventListener('change', (e) => {
    const exchange = e.target.value;
    document.getElementById('okx-form').style.display = exchange === 'OKX' ? 'block' : 'none';
    document.getElementById('kis-form').style.display = exchange === 'KIS' ? 'block' : 'none';
});

document.getElementById('btn-save-account')?.addEventListener('click', async () => {
    const exchange = document.getElementById('account-exchange').value;

    if (!exchange) {
        showToast('거래소를 선택하세요', 'error');
        return;
    }

    let name, apiKey, apiSecret, passphrase, accountNumber, accountType;

    if (exchange === 'OKX') {
        name = document.getElementById('okx-alias').value;
        apiKey = document.getElementById('okx-api-key').value;
        apiSecret = document.getElementById('okx-secret').value;
        passphrase = document.getElementById('okx-passphrase').value;

        if (!name || !apiKey || !apiSecret || !passphrase) {
            showToast('모든 필드를 입력하세요', 'error');
            return;
        }
    } else if (exchange === 'KIS') {
        name = document.getElementById('kis-alias').value;
        apiKey = document.getElementById('kis-app-key').value;
        apiSecret = document.getElementById('kis-app-secret').value;
        accountNumber = document.getElementById('kis-account-number').value;
        accountType = document.getElementById('kis-account-type').value;

        if (!name || !apiKey || !apiSecret || !accountNumber) {
            showToast('모든 필드를 입력하세요', 'error');
            return;
        }
    }

    try {
        await invoke('register_api_key', {
            accessToken: auth.accessToken,
            name: name,
            exchange: exchange,
            apiKey: apiKey,
            apiSecret: apiSecret,
            apiPassphrase: passphrase || null,
            accountNumber: accountNumber || null,
            accountType: accountType || null
        });

        showToast('계정이 등록되었습니다', 'success');
        document.getElementById('account-form-section').style.display = 'none';
        loadAccountsList();
    } catch (error) {
        showToast('등록 실패: ' + error, 'error');
    }
});

// =====================================================
// App Info Page (PHASE 7)
// =====================================================
async function loadAppInfoPage() {
    try {
        const result = await invoke('check_server_health');
        document.getElementById('app-server-status').textContent = result.ok ? '정상 연결' : '연결 오류';
        document.getElementById('app-last-connection').textContent = new Date().toLocaleString('ko-KR');
    } catch (e) {
        document.getElementById('app-server-status').textContent = '연결 실패';
    }

    // Update current plan
    const plan = auth.user?.plan || 'free';
    const planInfo = document.getElementById('current-plan-info');
    if (planInfo) {
        const badge = planInfo.querySelector('.plan-badge');
        const desc = planInfo.querySelector('.plan-description');
        if (badge) {
            badge.className = `plan-badge ${plan}`;
            badge.textContent = plan === 'premium' ? '프리미엄' : plan === 'hub' ? '허브' : '무료';
        }
        if (desc) {
            desc.textContent = plan === 'premium' ? '모든 기능을 이용할 수 있습니다.' :
                              plan === 'hub' ? '허브 기능을 이용할 수 있습니다.' :
                              '기본 기능을 무료로 이용하세요.';
        }
    }
}

document.getElementById('btn-open-terms')?.addEventListener('click', () => open('https://qube-system.com/terms'));
document.getElementById('btn-open-privacy')?.addEventListener('click', () => open('https://qube-system.com/privacy'));
document.getElementById('btn-export-logs')?.addEventListener('click', async () => {
    try {
        const path = await invoke('export_diagnostic');
        showToast('로그가 내보내졌습니다', 'success');
    } catch (e) {
        showToast('내보내기 실패', 'error');
    }
});

document.getElementById('btn-upgrade-hub')?.addEventListener('click', () => showToast('결제 시스템 준비 중입니다', 'info'));
document.getElementById('btn-upgrade-premium')?.addEventListener('click', () => showToast('결제 시스템 준비 중입니다', 'info'));

// =====================================================
// Admin Pages (PHASE 7)
// =====================================================
async function loadAdminUsersPage() {
    const tbody = document.getElementById('users-tbody');
    if (!tbody) return;

    try {
        // Would load from backend
        tbody.innerHTML = `
            <tr>
                <td>1</td>
                <td>관리자</td>
                <td>admin@qube-system.com</td>
                <td><span class="plan-badge premium">프리미엄</span></td>
                <td>2025-01-01</td>
                <td>2026-02-06</td>
                <td><span class="status-badge success">활성</span></td>
                <td><button class="btn btn-secondary btn-sm">편집</button></td>
            </tr>
        `;
    } catch (e) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">로딩 실패</td></tr>';
    }
}

async function loadAdminSystemPage() {
    try {
        const status = await invoke('get_server_status');
        document.getElementById('sys-status').textContent = status.running ? '정상' : '오류';
        document.getElementById('sys-status').className = `system-value ${status.running ? '' : 'error'}`;
    } catch (e) {
        document.getElementById('sys-status').textContent = '확인 불가';
    }
}

document.getElementById('btn-export-users')?.addEventListener('click', () => showToast('CSV 내보내기 준비 중', 'info'));

// =====================================================
// Initialize App
// =====================================================
(async () => {
    console.log('BBooster PC App 시작');
    console.log('API 서버:', API_BASE_URL);

    const isAuthenticated = await initAuth();

    if (isAuthenticated) {
        checkServerConnection();
    }
})();

// Periodic status update
setInterval(() => {
    if (isConnected) {
        updateServerStatus(true);
    }
}, 5000);
