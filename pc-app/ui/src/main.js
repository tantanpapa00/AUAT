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
    const userName = document.getElementById('user-name');
    const userAvatar = document.getElementById('user-avatar');

    // Update user name
    if (userName) {
        userName.textContent = user.name || user.email?.split('@')[0] || '사용자';
    }

    // Update avatar (first letter or emoji)
    if (userAvatar) {
        const name = user.name || user.email || '사용자';
        userAvatar.textContent = name.charAt(0).toUpperCase();
    }

    // Update subscription badge
    if (user.plan === 'premium') {
        if (badge) badge.className = 'subscription-badge premium';
        if (badgeText) badgeText.textContent = '프리미엄';
    } else if (user.plan === 'hub') {
        if (badge) badge.className = 'subscription-badge hub';
        if (badgeText) badgeText.textContent = '허브';
    } else {
        if (badge) badge.className = 'subscription-badge free';
        if (badgeText) badgeText.textContent = '무료';
    }

    // Show admin menu if admin
    if (user.role === 'admin') {
        document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'block');
        document.getElementById('admin-menu-group')?.style.setProperty('display', 'block');
    }
}

function logout() {
    localStorage.removeItem('bbooster_access_token');
    localStorage.removeItem('bbooster_refresh_token');
    localStorage.removeItem('bbooster_hub_mode');
    window.location.reload();
}

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
// Navigation - New Collapsible Sidebar Structure
// =====================================================
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebar-toggle');
const mainWrapper = document.querySelector('.main-wrapper');
const pageTitle = document.getElementById('page-title');

const pageTitles = {
    home: '홈',
    'tv-connect': '트레이딩뷰 연결',
    symbols: '심볼정보',
    'premium-strategy': '프리미엄 전략',
    accounts: '계정관리',
    notifications: '알림설정',
    'app-info': '앱정보',
    'admin-users': '사용자관리',
    'admin-system': '시스템상태'
};

// Sidebar Toggle (Collapse/Expand)
sidebarToggle?.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
    if (mainWrapper) {
        mainWrapper.style.marginLeft = sidebar.classList.contains('collapsed') ? '60px' : '240px';
    }
    localStorage.setItem('sidebar_collapsed', sidebar.classList.contains('collapsed'));
});

// Restore sidebar state
if (localStorage.getItem('sidebar_collapsed') === 'true') {
    sidebar?.classList.add('collapsed');
    if (mainWrapper) mainWrapper.style.marginLeft = '60px';
}

// Accordion Submenu Toggle
document.querySelectorAll('.nav-parent').forEach(parent => {
    parent.addEventListener('click', (e) => {
        e.preventDefault();
        const group = parent.closest('.nav-group');
        if (group) {
            // Close other groups
            document.querySelectorAll('.nav-group').forEach(g => {
                if (g !== group) g.classList.remove('open');
            });
            group.classList.toggle('open');
        }
    });
});

// Nav Item Click (Page Navigation)
document.querySelectorAll('.nav-item[data-page]').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        const page = item.dataset.page;
        if (page) navigateTo(page);
    });
});

window.navigateTo = function(page) {
    // Update active state
    document.querySelectorAll('.nav-item').forEach(nav => {
        nav.classList.toggle('active', nav.dataset.page === page);
    });

    // Open parent group if navigating to submenu item
    const activeItem = document.querySelector(`.nav-item[data-page="${page}"]`);
    if (activeItem) {
        const parentGroup = activeItem.closest('.nav-group');
        if (parentGroup) parentGroup.classList.add('open');
    }

    // Update page title
    if (pageTitle) pageTitle.textContent = pageTitles[page] || page;

    // Show target page
    document.querySelectorAll('.page-content').forEach(pageEl => {
        pageEl.style.display = 'none';
    });
    const targetPage = document.getElementById(`page-${page}`);
    if (targetPage) {
        targetPage.style.display = 'block';
    }

    // Update URL hash
    window.location.hash = page;

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

// Handle URL hash navigation
window.addEventListener('hashchange', () => {
    const hash = window.location.hash.slice(1);
    if (hash && pageTitles[hash]) {
        navigateTo(hash);
    }
});

// Sidebar Logout Button
document.getElementById('sidebar-logout-btn')?.addEventListener('click', logout);

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
// Home Page (PHASE 3) - Portfolio Dashboard
// =====================================================
let profitChart = null;
let allocationChart = null;
let currentPeriod = '1w';

async function loadHomePage() {
    // Load server status
    try {
        const status = await invoke('get_server_status');
        updateServerStatus(status.running);
    } catch (e) {
        console.error('Failed to get server status:', e);
    }

    // Load portfolio data
    await loadPortfolioSummary();
    await loadPortfolioChart(currentPeriod);
    await loadHoldings();
    await loadActiveStrategies();

    // Initialize charts
    initAllocationChart();
}

async function loadPortfolioSummary() {
    try {
        if (!auth.accessToken) {
            updateSummaryCards({ total_assets_formatted: '₩0', total_profit_rate: 0, daily_change_formatted: '₩0', daily_change_rate: 0, active_strategies: 0 });
            return;
        }

        const summary = await invoke('get_portfolio_summary', { accessToken: auth.accessToken });
        updateSummaryCards(summary);
    } catch (e) {
        console.error('Failed to load portfolio summary:', e);
        updateSummaryCards({ total_assets_formatted: '₩0', total_profit_rate: 0, daily_change_formatted: '₩0', daily_change_rate: 0, active_strategies: 0 });
    }
}

function updateSummaryCards(summary) {
    const totalAssets = document.getElementById('total-assets');
    const totalProfit = document.getElementById('total-profit');
    const dailyChange = document.getElementById('daily-change');
    const activeStrategies = document.getElementById('active-strategies-count');

    if (totalAssets) totalAssets.textContent = summary.total_assets_formatted || '₩0';

    if (totalProfit) {
        const rate = summary.total_profit_rate || 0;
        totalProfit.textContent = (rate >= 0 ? '+' : '') + rate.toFixed(2) + '%';
        totalProfit.className = 'summary-value ' + (rate >= 0 ? 'profit' : 'loss');
    }

    if (dailyChange) {
        const change = summary.daily_change_formatted || '₩0';
        const rate = summary.daily_change_rate || 0;
        dailyChange.textContent = `${change} (${rate >= 0 ? '+' : ''}${rate.toFixed(2)}%)`;
        dailyChange.className = 'summary-value ' + (rate >= 0 ? 'profit' : 'loss');
    }

    if (activeStrategies) activeStrategies.textContent = (summary.active_strategies || 0) + '개';
}

async function loadPortfolioChart(period) {
    currentPeriod = period;

    try {
        let chartData;
        if (auth.accessToken) {
            chartData = await invoke('get_portfolio_chart', { accessToken: auth.accessToken, period });
        } else {
            // Dummy data for non-logged in users
            chartData = generateDummyChartData(period);
        }

        updateProfitChart(chartData);
    } catch (e) {
        console.error('Failed to load chart data:', e);
        updateProfitChart(generateDummyChartData(period));
    }
}

function generateDummyChartData(period) {
    const counts = { '1d': 24, '1w': 7, '1m': 30, '3m': 90, '1y': 12 };
    const count = counts[period] || 7;
    const data = [];
    let value = 0;

    for (let i = 0; i < count; i++) {
        value += (Math.random() - 0.45) * 0.5;
        const date = new Date();
        date.setDate(date.getDate() - (count - i - 1));
        data.push({
            date: (date.getMonth() + 1) + '/' + date.getDate(),
            value: Math.round(value * 100) / 100
        });
    }

    return { period, data, period_profit_rate: value };
}

function updateProfitChart(chartData) {
    const ctx = document.getElementById('profit-chart');
    if (!ctx) return;

    if (profitChart) profitChart.destroy();

    const labels = chartData.data.map(d => d.date);
    const values = chartData.data.map(d => d.value);
    const isPositive = chartData.period_profit_rate >= 0;

    profitChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '수익률 (%)',
                data: values,
                borderColor: isPositive ? '#00C853' : '#FF1744',
                backgroundColor: isPositive ? 'rgba(0, 200, 83, 0.1)' : 'rgba(255, 23, 68, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: values.length > 30 ? 0 : 3,
                pointHoverRadius: 5
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            plugins: { legend: { display: false } },
            scales: {
                y: {
                    grid: { color: 'rgba(255,255,255,0.1)' },
                    ticks: { color: '#9CA3AF', callback: (v) => v + '%' }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#9CA3AF', maxRotation: 0 }
                }
            }
        }
    });

    // Update period profit display
    const periodProfit = document.getElementById('period-profit');
    if (periodProfit) {
        const rate = chartData.period_profit_rate || 0;
        periodProfit.textContent = (rate >= 0 ? '+' : '') + rate.toFixed(2) + '%';
        periodProfit.className = rate >= 0 ? 'profit' : 'loss';
    }
}

function initAllocationChart(allocData) {
    const ctx = document.getElementById('allocation-chart');
    if (!ctx) return;

    if (allocationChart) allocationChart.destroy();

    // Default allocation (all cash)
    const data = allocData || [0, 0, 0, 100];

    allocationChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['국내주식', '해외주식', '암호화폐', '현금'],
            datasets: [{
                data: data,
                backgroundColor: ['#3B82F6', '#8B5CF6', '#F59E0B', '#6B7280'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: { legend: { display: false } }
        }
    });
}

async function loadHoldings() {
    const tbody = document.getElementById('holdings-tbody');
    if (!tbody) return;

    try {
        let holdings = [];
        if (auth.accessToken) {
            holdings = await invoke('get_holdings', { accessToken: auth.accessToken });
        }

        if (holdings.length === 0) {
            tbody.innerHTML = `
                <tr class="empty-row">
                    <td colspan="7">
                        <div class="empty-state">
                            <p>연결된 계정이 없습니다.</p>
                            <p>설정 → 계정관리에서 거래소를 연결하세요.</p>
                            <button class="btn btn-primary" onclick="navigateTo('accounts')">계정 연결하기</button>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        // Sort by profit rate (highest first)
        holdings.sort((a, b) => b.profit_rate - a.profit_rate);

        tbody.innerHTML = holdings.map(h => `
            <tr>
                <td><strong>${h.symbol}</strong><br><small>${h.name}</small></td>
                <td><span class="exchange-badge">${h.exchange}</span></td>
                <td>${formatNumber(h.quantity)}</td>
                <td>${formatCurrency(h.avg_price, h.exchange)}</td>
                <td>${formatCurrency(h.current_price, h.exchange)}</td>
                <td class="${h.profit_loss >= 0 ? 'profit' : 'loss'}">${formatCurrency(h.profit_loss, h.exchange)}</td>
                <td class="${h.profit_rate >= 0 ? 'profit' : 'loss'}">${h.profit_rate >= 0 ? '+' : ''}${h.profit_rate.toFixed(2)}%</td>
            </tr>
        `).join('');

    } catch (e) {
        console.error('Failed to load holdings:', e);
    }
}

async function loadActiveStrategies() {
    const container = document.getElementById('active-strategies-list');
    if (!container) return;

    try {
        let strategies = [];
        if (auth.accessToken) {
            strategies = await invoke('get_active_strategies', { accessToken: auth.accessToken });
        }

        if (strategies.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <p>활성 전략이 없습니다.</p>
                    <p>전략설정에서 전략을 추가하세요.</p>
                    <button class="btn btn-primary" onclick="navigateTo('tv-connect')">전략 추가하기</button>
                </div>
            `;
            return;
        }

        container.innerHTML = strategies.map(s => `
            <div class="strategy-card">
                <div class="strategy-card-header">
                    <h4>${s.name}</h4>
                    <span class="strategy-status ${s.status === 'running' ? 'running' : 'stopped'}">
                        ${s.status === 'running' ? '실행중' : '정지'}
                    </span>
                </div>
                <div class="strategy-card-body">
                    <div class="strategy-info">
                        <span class="strategy-info-label">대상 자산</span>
                        <span class="strategy-info-value">${s.symbol}</span>
                    </div>
                    <div class="strategy-info">
                        <span class="strategy-info-label">거래소</span>
                        <span class="strategy-info-value">${s.exchange}</span>
                    </div>
                    <div class="strategy-trades-today">
                        오늘 거래: <strong>${s.trades_today}회</strong>
                    </div>
                </div>
            </div>
        `).join('');

    } catch (e) {
        console.error('Failed to load active strategies:', e);
    }
}

// Utility functions for formatting
function formatNumber(num) {
    if (num === null || num === undefined) return '0';
    return num.toLocaleString('ko-KR', { maximumFractionDigits: 8 });
}

function formatCurrency(value, exchange) {
    if (value === null || value === undefined) return '-';
    const isCrypto = ['OKX', 'BINANCE', 'BYBIT'].includes(exchange?.toUpperCase());
    const isKRW = ['KIS', 'KIWOOM'].includes(exchange?.toUpperCase());

    if (isCrypto) {
        return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    } else if (isKRW) {
        return '₩' + Math.round(value).toLocaleString('ko-KR');
    }
    return value.toLocaleString('ko-KR', { minimumFractionDigits: 2 });
}

// Period tabs
document.querySelectorAll('.period-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.period-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        loadPortfolioChart(tab.dataset.period);
    });
});

// Refresh buttons
document.getElementById('btn-refresh-holdings')?.addEventListener('click', loadHoldings);
document.getElementById('btn-refresh-strategies')?.addEventListener('click', loadActiveStrategies);

// Emergency stop button
document.getElementById('btn-emergency-stop')?.addEventListener('click', async () => {
    if (!confirm('모든 자동매매를 즉시 정지하시겠습니까?\n\n모든 활성 전략이 중단됩니다.')) return;

    try {
        if (auth.accessToken) {
            await invoke('emergency_stop', { accessToken: auth.accessToken });
        } else {
            await invoke('set_estop', { enabled: true });
        }
        showToast('긴급 정지가 활성화되었습니다', 'warning');
        loadActiveStrategies(); // Refresh strategies
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
    loadUserWebhookUrl();
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
        let logs = [];
        if (auth.accessToken) {
            logs = await invoke('get_webhook_logs', { accessToken: auth.accessToken, limit: 20 });
        }

        if (!logs || logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">최근 수신 웹훅 없음</td></tr>';
            return;
        }

        tbody.innerHTML = logs.map(log => {
            const statusClass = log.status === 'success' ? 'success' : log.status === 'rejected' ? 'warning' : 'error';
            const statusText = log.status === 'success' ? '성공' : log.status === 'rejected' ? '거부' : '실패';
            const timeStr = log.received_at ? new Date(log.received_at).toLocaleString('ko-KR') : '-';
            const content = log.error_message || `${log.action} ${log.symbol}`;

            return `
                <tr>
                    <td>${timeStr}</td>
                    <td><span class="status-badge ${statusClass}">${statusText}</span></td>
                    <td>${log.exchange || '-'}</td>
                    <td>${log.symbol || '-'}</td>
                    <td title="${log.error_message || ''}">${content}</td>
                </tr>
            `;
        }).join('');

    } catch (error) {
        console.error('Failed to load webhook logs:', error);
        tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">로그 로딩 실패</td></tr>';
    }
}

async function loadUserWebhookUrl() {
    const webhookUrlEl = document.getElementById('webhook-url');
    if (!webhookUrlEl) return;

    try {
        if (auth.accessToken) {
            const urlInfo = await invoke('get_webhook_url', { accessToken: auth.accessToken });
            webhookUrlEl.textContent = urlInfo.webhook_url;
        } else if (auth.user && auth.user.id) {
            webhookUrlEl.textContent = `https://qube-system.com/api/webhook/${auth.user.id}`;
        }
    } catch (error) {
        console.error('Failed to load webhook URL:', error);
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
let currentSymbolExchange = 'all';
let symbolsData = [];

async function loadSymbolsPage() {
    // Check user plan
    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';

    if (plan === 'free' && role !== 'admin') {
        document.getElementById('symbols-restriction').style.display = 'flex';
        return;
    }

    document.getElementById('symbols-restriction').style.display = 'none';
    await loadPopularSymbols();
}

async function loadPopularSymbols() {
    const tbody = document.getElementById('symbols-tbody');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">로딩 중...</td></tr>';

    try {
        let symbols = [];
        if (auth.accessToken) {
            const data = await invoke('get_popular_symbols', { accessToken: auth.accessToken });
            symbols = [...(data.crypto || []), ...(data.stocks || [])];
        }

        if (symbols.length === 0) {
            // 더미 데이터
            symbols = [
                { symbol: 'BTC-USDT', name: 'Bitcoin', exchange: 'OKX', price_formatted: '$97,234.50', change_formatted: '+2.34%', change: 2.34, volume_formatted: '1.2B' },
                { symbol: 'ETH-USDT', name: 'Ethereum', exchange: 'OKX', price_formatted: '$3,456.78', change_formatted: '+1.23%', change: 1.23, volume_formatted: '890M' },
                { symbol: 'SOL-USDT', name: 'Solana', exchange: 'OKX', price_formatted: '$198.45', change_formatted: '-0.89%', change: -0.89, volume_formatted: '456M' }
            ];
        }

        symbolsData = symbols;
        renderSymbolsTable(symbols);
    } catch (error) {
        console.error('Failed to load symbols:', error);
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">심볼 로딩 실패</td></tr>';
    }
}

async function searchSymbols(query) {
    const tbody = document.getElementById('symbols-tbody');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">검색 중...</td></tr>';

    try {
        const exchange = currentSymbolExchange === 'all' ? null : currentSymbolExchange;
        const symbols = await invoke('search_symbols', {
            accessToken: auth.accessToken || '',
            query: query,
            exchange: exchange
        });

        symbolsData = symbols || [];
        renderSymbolsTable(symbolsData);
    } catch (error) {
        console.error('Failed to search symbols:', error);
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">검색 실패</td></tr>';
    }
}

function renderSymbolsTable(symbols) {
    const tbody = document.getElementById('symbols-tbody');
    if (!tbody) return;

    if (!symbols || symbols.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">검색 결과 없음</td></tr>';
        return;
    }

    tbody.innerHTML = symbols.map(s => `
        <tr data-symbol="${s.symbol}" data-exchange="${s.exchange}" style="cursor: pointer;">
            <td><strong>${s.symbol}</strong></td>
            <td>${s.name}</td>
            <td><span class="exchange-badge ${s.exchange.toLowerCase()}">${s.exchange}</span></td>
            <td>${s.price_formatted}</td>
            <td class="${s.change >= 0 ? 'profit' : 'loss'}">${s.change_formatted}</td>
            <td>${s.volume_formatted}</td>
        </tr>
    `).join('');

    tbody.querySelectorAll('tr[data-symbol]').forEach(row => {
        row.addEventListener('click', () => showSymbolDetail(row.dataset.symbol, row.dataset.exchange));
    });
}

async function showSymbolDetail(symbol, exchange) {
    const panel = document.getElementById('symbol-detail-panel');
    if (!panel) return;

    document.getElementById('detail-symbol-name').textContent = symbol;
    document.getElementById('detail-exchange').textContent = exchange;
    document.getElementById('detail-exchange').className = `exchange-badge ${exchange.toLowerCase()}`;
    panel.style.display = 'block';

    try {
        const detail = await invoke('get_symbol_detail', {
            accessToken: auth.accessToken || '',
            symbol: symbol,
            exchange: exchange
        });

        document.getElementById('detail-price').textContent = detail.price_formatted || '-';
        const changeEl = document.getElementById('detail-change');
        changeEl.textContent = detail.change_formatted || '-';
        changeEl.className = `price-change ${detail.change >= 0 ? 'profit' : 'loss'}`;
        document.getElementById('detail-high').textContent = detail.high_24h_formatted || '-';
        document.getElementById('detail-low').textContent = detail.low_24h_formatted || '-';
        document.getElementById('detail-volume').textContent = detail.volume_formatted || '-';

        // 미니 차트 (더미)
        drawMiniChart(detail.price, detail.change);
    } catch (error) {
        console.error('Failed to load symbol detail:', error);
    }
}

function drawMiniChart(price, change) {
    const canvas = document.getElementById('mini-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;

    ctx.clearRect(0, 0, width, height);

    // 더미 차트 데이터
    const data = [];
    let value = price * 0.97;
    for (let i = 0; i < 24; i++) {
        value += (Math.random() - 0.45) * price * 0.01;
        data.push(value);
    }
    data.push(price);

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;

    // 라인 그리기
    ctx.strokeStyle = change >= 0 ? '#22C55E' : '#EF4444';
    ctx.lineWidth = 2;
    ctx.beginPath();

    data.forEach((v, i) => {
        const x = (i / (data.length - 1)) * width;
        const y = height - ((v - min) / range) * height * 0.8 - height * 0.1;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });

    ctx.stroke();
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

// Symbol search input
document.getElementById('symbol-search')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        const query = e.target.value.trim();
        if (query) searchSymbols(query);
        else loadPopularSymbols();
    }
});

document.getElementById('btn-symbol-search')?.addEventListener('click', () => {
    const query = document.getElementById('symbol-search')?.value?.trim() || '';
    if (query) searchSymbols(query);
    else loadPopularSymbols();
});

document.querySelectorAll('.symbol-tag').forEach(tag => {
    tag.addEventListener('click', () => {
        const symbol = tag.dataset.symbol;
        document.getElementById('symbol-search').value = symbol;
        searchSymbols(symbol);
    });
});

document.querySelectorAll('.filter-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        currentSymbolExchange = tab.dataset.exchange;

        // 현재 검색어로 재검색
        const query = document.getElementById('symbol-search')?.value?.trim() || '';
        if (query) searchSymbols(query);
        else loadPopularSymbols();
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

    list.innerHTML = '<p class="loading">전략 로딩 중...</p>';

    try {
        let strategies = [];
        if (auth.accessToken) {
            strategies = await invoke('get_strategies', { accessToken: auth.accessToken });
        }

        if (!strategies || strategies.length === 0) {
            list.innerHTML = `
                <div class="empty-state">
                    <p>설정된 전략이 없습니다.</p>
                    <p>커스텀/역추세/추세 탭에서 전략을 추가하세요.</p>
                </div>
            `;
            return;
        }

        list.innerHTML = strategies.map(s => `
            <div class="strategy-card" data-id="${s.id}">
                <div class="strategy-card-header">
                    <h4>${s.name}</h4>
                    <span class="strategy-type-badge ${s.strategy_type}">${s.strategy_type}</span>
                </div>
                <div class="strategy-card-body">
                    <div class="strategy-info">
                        <span>심볼:</span>
                        <strong>${s.symbol}</strong>
                    </div>
                    <div class="strategy-info">
                        <span>거래소:</span>
                        <strong>${s.exchange}</strong>
                    </div>
                </div>
                <div class="strategy-card-actions">
                    <button class="btn btn-sm ${s.is_active ? 'btn-success' : 'btn-secondary'} btn-toggle-strategy" data-id="${s.id}">
                        ${s.is_active ? '실행중' : '비활성'}
                    </button>
                    <button class="btn btn-sm btn-danger btn-delete-strategy" data-id="${s.id}">삭제</button>
                </div>
            </div>
        `).join('');

        // 이벤트 바인딩
        list.querySelectorAll('.btn-toggle-strategy').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = parseInt(btn.dataset.id);
                try {
                    const result = await invoke('toggle_strategy', { accessToken: auth.accessToken, strategyId: id });
                    showToast(result.is_active ? '전략 활성화됨' : '전략 비활성화됨', 'success');
                    loadStrategies();
                } catch (e) {
                    showToast('전략 토글 실패', 'error');
                }
            });
        });

        list.querySelectorAll('.btn-delete-strategy').forEach(btn => {
            btn.addEventListener('click', async () => {
                if (!confirm('이 전략을 삭제하시겠습니까?')) return;
                const id = parseInt(btn.dataset.id);
                try {
                    await invoke('delete_strategy', { accessToken: auth.accessToken, strategyId: id });
                    showToast('전략이 삭제되었습니다', 'success');
                    loadStrategies();
                } catch (e) {
                    showToast('전략 삭제 실패', 'error');
                }
            });
        });

    } catch (error) {
        console.error('Failed to load strategies:', error);
        list.innerHTML = '<p class="empty">전략 로딩 실패</p>';
    }
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

    // 현재 활성 탭에서 설정 수집
    const activeTab = document.querySelector('.strategy-tab.active')?.dataset.tab || 'custom';
    let strategyType = activeTab;
    let exchange = '';
    let symbol = '';
    let params = {};
    let orderSettings = {};

    if (activeTab === 'reversal') {
        exchange = document.getElementById('reversal-exchange')?.value || 'OKX';
        symbol = document.getElementById('reversal-symbol')?.value || 'BTC-USDT';
        params = {
            rsi_period: parseInt(document.getElementById('reversal-rsi-period')?.value || 14),
            overbought: parseInt(document.getElementById('reversal-overbought')?.value || 70),
            oversold: parseInt(document.getElementById('reversal-oversold')?.value || 30)
        };
        orderSettings = {
            qty_percent: parseFloat(document.getElementById('reversal-qty')?.value || 100),
            stop_loss: parseFloat(document.getElementById('reversal-sl')?.value) || null,
            take_profit: parseFloat(document.getElementById('reversal-tp')?.value) || null
        };
    } else if (activeTab === 'trend') {
        exchange = document.getElementById('trend-exchange')?.value || 'OKX';
        symbol = document.getElementById('trend-symbol')?.value || 'BTC-USDT';
        params = {
            short_ma: parseInt(document.getElementById('trend-short-ma')?.value || 20),
            long_ma: parseInt(document.getElementById('trend-long-ma')?.value || 60)
        };
        orderSettings = {
            qty_percent: parseFloat(document.getElementById('trend-qty')?.value || 100),
            stop_loss: parseFloat(document.getElementById('trend-sl')?.value) || null,
            take_profit: parseFloat(document.getElementById('trend-tp')?.value) || null
        };
    } else {
        exchange = document.getElementById('custom-exchange')?.value || 'OKX';
        symbol = document.getElementById('custom-symbol')?.value || 'BTC-USDT';
        orderSettings = {
            qty_percent: parseFloat(document.getElementById('custom-qty')?.value || 100),
            leverage: parseInt(document.getElementById('custom-leverage')?.value || 1),
            stop_loss: parseFloat(document.getElementById('custom-sl')?.value) || null,
            take_profit: parseFloat(document.getElementById('custom-tp')?.value) || null
        };
    }

    const startDate = document.getElementById('backtest-start')?.value || '2024-01-01';
    const endDate = document.getElementById('backtest-end')?.value || '2025-12-31';
    const initialCapital = parseFloat(document.getElementById('backtest-capital')?.value || 10000000);

    try {
        const result = await invoke('run_backtest', {
            accessToken: auth.accessToken || '',
            strategyType: strategyType,
            exchange: exchange,
            symbol: symbol,
            startDate: startDate,
            endDate: endDate,
            initialCapital: initialCapital,
            params: params,
            orderSettings: orderSettings
        });

        displayBacktestResult(result);
        showToast('백테스팅 완료', 'success');
    } catch (error) {
        console.error('Backtest failed:', error);
        showToast('백테스팅 실패: ' + error, 'error');
    }
}

function displayBacktestResult(result) {
    const resultDiv = document.getElementById('backtest-result');
    if (!resultDiv) return;

    resultDiv.style.display = 'block';

    const summary = result.summary || {};
    document.getElementById('bt-total-return').textContent = `${summary.total_return >= 0 ? '+' : ''}${summary.total_return || 0}%`;
    document.getElementById('bt-cagr').textContent = `${summary.cagr >= 0 ? '+' : ''}${summary.cagr || 0}%`;
    document.getElementById('bt-mdd').textContent = `${summary.max_drawdown || 0}%`;
    document.getElementById('bt-sharpe').textContent = (summary.sharpe_ratio || 0).toFixed(2);
    document.getElementById('bt-winrate').textContent = `${summary.win_rate || 0}%`;
    document.getElementById('bt-trades').textContent = `${summary.total_trades || 0}회`;

    // 차트 업데이트
    if (result.equity_curve && result.equity_curve.length > 0) {
        initBacktestChartWithData(result.equity_curve);
    }
}

function initBacktestChartWithData(equityCurve) {
    const ctx = document.getElementById('backtest-chart');
    if (!ctx) return;

    if (backtestChart) backtestChart.destroy();

    const labels = equityCurve.map(p => p.date);
    const data = equityCurve.map(p => p.equity);

    backtestChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '자산',
                data: data,
                borderColor: data[data.length - 1] >= data[0] ? '#22C55E' : '#EF4444',
                fill: false,
                tension: 0.1,
                pointRadius: data.length > 100 ? 0 : 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: {
                    grid: { color: 'rgba(255,255,255,0.1)' },
                    ticks: { color: '#9CA3AF', callback: (v) => `₩${(v/1000000).toFixed(0)}M` }
                },
                x: { display: false }
            }
        }
    });
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

document.getElementById('btn-activate-strategy')?.addEventListener('click', async () => {
    const activeTab = document.querySelector('.strategy-tab.active')?.dataset.tab || 'custom';
    let exchange = '';
    let symbol = '';
    let params = {};
    let orderSettings = {};

    if (activeTab === 'reversal') {
        exchange = document.getElementById('reversal-exchange')?.value || 'OKX';
        symbol = document.getElementById('reversal-symbol')?.value || 'BTC-USDT';
        params = {
            rsi_period: parseInt(document.getElementById('reversal-rsi-period')?.value || 14),
            overbought: parseInt(document.getElementById('reversal-overbought')?.value || 70),
            oversold: parseInt(document.getElementById('reversal-oversold')?.value || 30)
        };
        orderSettings = {
            qty_percent: parseFloat(document.getElementById('reversal-qty')?.value || 100),
            stop_loss: parseFloat(document.getElementById('reversal-sl')?.value) || null,
            take_profit: parseFloat(document.getElementById('reversal-tp')?.value) || null
        };
    } else if (activeTab === 'trend') {
        exchange = document.getElementById('trend-exchange')?.value || 'OKX';
        symbol = document.getElementById('trend-symbol')?.value || 'BTC-USDT';
        params = {
            short_ma: parseInt(document.getElementById('trend-short-ma')?.value || 20),
            long_ma: parseInt(document.getElementById('trend-long-ma')?.value || 60)
        };
        orderSettings = {
            qty_percent: parseFloat(document.getElementById('trend-qty')?.value || 100),
            stop_loss: parseFloat(document.getElementById('trend-sl')?.value) || null,
            take_profit: parseFloat(document.getElementById('trend-tp')?.value) || null
        };
    } else {
        exchange = document.getElementById('custom-exchange')?.value || 'OKX';
        symbol = document.getElementById('custom-symbol')?.value || 'BTC-USDT';
        orderSettings = {
            qty_percent: parseFloat(document.getElementById('custom-qty')?.value || 100),
            leverage: parseInt(document.getElementById('custom-leverage')?.value || 1),
            stop_loss: parseFloat(document.getElementById('custom-sl')?.value) || null,
            take_profit: parseFloat(document.getElementById('custom-tp')?.value) || null
        };
    }

    const strategyName = `${activeTab} - ${symbol}`;

    try {
        await invoke('save_strategy', {
            accessToken: auth.accessToken || '',
            name: strategyName,
            strategyType: activeTab,
            exchange: exchange,
            symbol: symbol,
            params: params,
            orderSettings: orderSettings,
            isActive: true
        });
        showToast('전략이 저장되고 활성화되었습니다', 'success');
        document.querySelectorAll('.strategy-tab')[0].click();
        loadStrategies();
    } catch (error) {
        showToast('전략 저장 실패: ' + error, 'error');
    }
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
