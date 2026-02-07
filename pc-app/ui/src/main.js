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
// [BUG FIX 8] 공통 유틸리티 - 타임아웃 + 에러 처리
// =====================================================

/**
 * Tauri invoke 래퍼 - 타임아웃 + 에러 처리
 * @param {string} command - Tauri 명령어
 * @param {object} args - 인자
 * @param {number} timeout - 타임아웃 (ms)
 * @returns {Promise<any>}
 */
async function invokeWithTimeout(command, args = {}, timeout = 10000) {
    try {
        const result = await Promise.race([
            invoke(command, args),
            new Promise((_, reject) =>
                setTimeout(() => reject(new Error('TIMEOUT')), timeout)
            )
        ]);
        return result;
    } catch (e) {
        console.error(`[${command}] Error:`, e);
        if (e.message === 'TIMEOUT') {
            throw new Error('요청 시간이 초과되었습니다');
        }
        throw e;
    }
}

/**
 * 로딩 상태 표시 + 타임아웃 자동 에러 전환
 * @param {HTMLElement} element - 로딩 표시할 요소
 * @param {number} maxTime - 최대 대기 시간 (ms)
 */
function showLoadingWithTimeout(element, maxTime = 15000) {
    if (!element) return null;
    element.innerHTML = '<div class="loading-state">데이터 로딩 중...</div>';

    const timeoutId = setTimeout(() => {
        if (element.innerHTML.includes('로딩 중')) {
            element.innerHTML = `
                <div class="error-state">
                    <p>데이터를 불러올 수 없습니다</p>
                    <button class="btn btn-sm btn-primary retry-btn">다시 시도</button>
                </div>
            `;
        }
    }, maxTime);

    return timeoutId;
}

/**
 * 에러 상태 표시
 * @param {HTMLElement} element
 * @param {string} message
 * @param {Function} retryFn - 다시 시도 콜백
 */
function showErrorState(element, message = '데이터를 불러올 수 없습니다', retryFn = null) {
    if (!element) return;
    element.innerHTML = `
        <div class="error-state">
            <p>${message}</p>
            ${retryFn ? '<button class="btn btn-sm btn-primary retry-btn">다시 시도</button>' : ''}
        </div>
    `;
    if (retryFn) {
        element.querySelector('.retry-btn')?.addEventListener('click', retryFn);
    }
}

// =====================================================
// [BUG FIX 1] 종목 검색 자동완성 공통 컴포넌트
// =====================================================

/**
 * 종목 자동완성 컴포넌트 생성
 * @param {HTMLInputElement} inputElement - 검색 입력 필드
 * @param {Function} onSelect - 종목 선택 시 콜백 ({code, name, exchange, market})
 * @param {object} options - 옵션 {exchange, category, showBadge}
 * @returns {object} - 컴포넌트 인스턴스
 */
function createSymbolAutocomplete(inputElement, onSelect, options = {}) {
    if (!inputElement) return null;

    const {
        exchange = 'all',
        category = 'all',
        showBadge = true,
        maxResults = 10
    } = options;

    // 상태
    let selectedSymbol = null;
    let dropdownVisible = false;
    let highlightedIndex = -1;
    let debounceTimer = null;

    // 드롭다운 생성
    const wrapper = document.createElement('div');
    wrapper.className = 'autocomplete-wrapper';
    inputElement.parentNode.insertBefore(wrapper, inputElement);
    wrapper.appendChild(inputElement);

    const dropdown = document.createElement('div');
    dropdown.className = 'autocomplete-dropdown';
    dropdown.style.display = 'none';
    wrapper.appendChild(dropdown);

    // 선택 배지 (입력 필드 옆)
    const badge = document.createElement('span');
    badge.className = 'selected-symbol-badge';
    badge.style.display = 'none';
    wrapper.appendChild(badge);

    // 검색 함수
    async function search(query) {
        if (!query || query.length < 1) {
            hideDropdown();
            return;
        }

        try {
            const result = await invokeWithTimeout('search_symbols', {
                accessToken: auth.accessToken || '',
                query: query,
                exchange: exchange !== 'all' ? exchange : null
            }, 5000);

            const symbols = result?.symbols || result || [];

            if (symbols.length === 0) {
                showNoResults();
                return;
            }

            renderDropdown(symbols.slice(0, maxResults));
        } catch (error) {
            console.error('Symbol search error:', error);
            showNoResults();
        }
    }

    // 드롭다운 렌더링
    function renderDropdown(symbols) {
        dropdown.innerHTML = symbols.map((s, idx) => `
            <div class="autocomplete-item ${idx === highlightedIndex ? 'highlighted' : ''}"
                 data-code="${s.symbol || s.code}"
                 data-name="${s.name}"
                 data-exchange="${s.exchange}"
                 data-market="${s.market || ''}">
                <span class="symbol-name">${s.name}</span>
                <span class="symbol-code">(${s.symbol || s.code})</span>
                <span class="symbol-market">${s.market || s.exchange}</span>
            </div>
        `).join('');

        dropdown.querySelectorAll('.autocomplete-item').forEach((item, idx) => {
            item.addEventListener('click', () => selectItem(idx));
            item.addEventListener('mouseenter', () => {
                highlightedIndex = idx;
                updateHighlight();
            });
        });

        showDropdown();
    }

    function showNoResults() {
        dropdown.innerHTML = '<div class="autocomplete-no-result">검색 결과가 없습니다</div>';
        showDropdown();
    }

    function showDropdown() {
        dropdown.style.display = 'block';
        dropdownVisible = true;
    }

    function hideDropdown() {
        dropdown.style.display = 'none';
        dropdownVisible = false;
        highlightedIndex = -1;
    }

    function updateHighlight() {
        dropdown.querySelectorAll('.autocomplete-item').forEach((item, idx) => {
            item.classList.toggle('highlighted', idx === highlightedIndex);
        });
    }

    function selectItem(idx) {
        const items = dropdown.querySelectorAll('.autocomplete-item');
        if (idx >= 0 && idx < items.length) {
            const item = items[idx];
            selectedSymbol = {
                code: item.dataset.code,
                name: item.dataset.name,
                exchange: item.dataset.exchange,
                market: item.dataset.market
            };

            inputElement.value = selectedSymbol.name;
            hideDropdown();

            // 배지 표시
            if (showBadge) {
                badge.innerHTML = `${selectedSymbol.name} ${selectedSymbol.code} <span class="badge-close">✕</span>`;
                badge.style.display = 'inline-flex';
                badge.querySelector('.badge-close').addEventListener('click', clearSelection);
            }

            // 콜백 호출
            if (onSelect) {
                onSelect(selectedSymbol);
            }
        }
    }

    function clearSelection() {
        selectedSymbol = null;
        inputElement.value = '';
        badge.style.display = 'none';
        if (onSelect) {
            onSelect(null);
        }
    }

    // 이벤트 바인딩
    inputElement.addEventListener('input', (e) => {
        const query = e.target.value.trim();

        // 선택 해제
        if (selectedSymbol && query !== selectedSymbol.name) {
            selectedSymbol = null;
            badge.style.display = 'none';
        }

        // 디바운스 (200ms)
        if (debounceTimer) clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => search(query), 200);
    });

    inputElement.addEventListener('keydown', (e) => {
        if (!dropdownVisible) return;

        const items = dropdown.querySelectorAll('.autocomplete-item');

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            highlightedIndex = Math.min(highlightedIndex + 1, items.length - 1);
            updateHighlight();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            highlightedIndex = Math.max(highlightedIndex - 1, 0);
            updateHighlight();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (highlightedIndex >= 0) {
                selectItem(highlightedIndex);
            } else if (items.length > 0) {
                selectItem(0);
            }
        } else if (e.key === 'Escape') {
            hideDropdown();
        }
    });

    // 외부 클릭 시 닫기
    document.addEventListener('click', (e) => {
        if (!wrapper.contains(e.target)) {
            hideDropdown();
        }
    });

    // 반환 인터페이스
    return {
        getSelected: () => selectedSymbol,
        isValid: () => !!selectedSymbol,
        clear: clearSelection,
        destroy: () => {
            wrapper.parentNode.insertBefore(inputElement, wrapper);
            wrapper.remove();
        }
    };
}

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

    const isAdmin = user.role === 'admin';

    // Update user name (admin 표시 포함)
    if (userName) {
        const displayName = user.name || user.email?.split('@')[0] || '사용자';
        userName.textContent = isAdmin ? `${displayName} (Admin)` : displayName;
    }

    // Update avatar (first letter or emoji, admin은 특별 표시)
    if (userAvatar) {
        if (isAdmin) {
            userAvatar.textContent = '👑';
        } else {
            const name = user.name || user.email || '사용자';
            userAvatar.textContent = name.charAt(0).toUpperCase();
        }
    }

    // Update subscription badge
    // [BUG FIX 5] admin이면 Admin 배지, 아니면 요금제 배지
    if (isAdmin) {
        if (badge) badge.className = 'subscription-badge admin';
        if (badgeText) badgeText.textContent = 'Admin';
    } else {
        const planDisplayMap = {
            'premium': { class: 'premium', text: 'Premium' },
            'pro': { class: 'pro', text: 'Pro' },
            'standard': { class: 'standard', text: 'Standard' },
            'hub': { class: 'standard', text: 'Standard' },
            'starter': { class: 'starter', text: 'Starter' },
            'free': { class: 'starter', text: 'Starter' },
        };
        const planInfo = planDisplayMap[user.plan] || planDisplayMap['starter'];
        if (badge) badge.className = `subscription-badge ${planInfo.class}`;
        if (badgeText) badgeText.textContent = planInfo.text;
    }

    // Show admin menu if admin
    if (isAdmin) {
        document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'block');
        document.getElementById('admin-menu-group')?.style.setProperty('display', 'block');
    } else {
        document.querySelectorAll('.admin-only').forEach(el => el.style.display = 'none');
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
    'premium-strategy': '프리미엄 전략',
    // 시장분석
    'market-kr': '국내시장',
    'market-us': '해외시장',
    'market-etf': 'ETF',
    'market-crypto': '코인시장',
    // 종목분석
    'stock-kr': '국내주식',
    'stock-us': '해외주식',
    'stock-etf': 'ETF 분석',
    'stock-crypto': '코인분석',
    // 기타
    watchlist: '관심종목',
    symbols: '종목분석', // legacy
    'market-overview': '시장현황', // legacy
    'sector-analysis': '업종분석', // legacy
    'stock-ranking': '종목순위', // legacy
    'featured-stocks': '특징주', // legacy
    'market-events': '이벤트일정', // legacy
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
    // 시장분석 (신규)
    else if (page === 'market-kr') loadMarketKr();
    else if (page === 'market-us') loadMarketUs();
    else if (page === 'market-etf') loadMarketEtf();
    else if (page === 'market-crypto') loadMarketCrypto();
    // 종목분석 (신규)
    else if (page === 'stock-kr') loadStockKr();
    else if (page === 'stock-us') loadStockUs();
    else if (page === 'stock-etf') loadStockEtf();
    else if (page === 'stock-crypto') loadStockCrypto();
    // 관심종목 (신규)
    else if (page === 'watchlist') loadWatchlist();
    // 기존 (legacy)
    else if (page === 'market-overview') loadMarketOverview();
    else if (page === 'sector-analysis') loadSectorAnalysis();
    else if (page === 'stock-ranking') loadStockRanking();
    else if (page === 'featured-stocks') loadFeaturedStocks();
    else if (page === 'market-events') loadMarketEvents();
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
    // [BUG FIX 3] 자동완성 초기화
    initTVAssetAutocomplete();
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
// [BUG FIX 3] 자동완성 초기화 - 4곳에 적용
// =====================================================

// 자동완성 인스턴스 저장
let tvAssetAutocomplete = null;
let customSymbolAutocomplete = null;
let reversalSymbolAutocomplete = null;
let trendSymbolAutocomplete = null;
let stockKrAutocomplete = null;
let watchlistAddAutocomplete = null;

// 1. TV Connect Step 2: 자산 선택 자동완성
function initTVAssetAutocomplete() {
    const input = document.getElementById('asset-search-input');
    if (!input || tvAssetAutocomplete) return;

    tvAssetAutocomplete = createSymbolAutocomplete(input, (symbol) => {
        if (symbol) {
            selectedSymbol = symbol.code;
            document.getElementById('btn-tv-next-2').disabled = false;
            // 자산 리스트에 선택된 종목 표시
            const listEl = document.getElementById('tv-asset-list');
            if (listEl) {
                listEl.innerHTML = `
                    <div class="selected-asset-card">
                        <span class="asset-name">${symbol.name}</span>
                        <span class="asset-code">(${symbol.code})</span>
                        <span class="asset-market">${symbol.market || symbol.exchange}</span>
                    </div>
                `;
            }
            showToast(`${symbol.name} (${symbol.code}) 선택됨`, 'success');
        } else {
            selectedSymbol = null;
            document.getElementById('btn-tv-next-2').disabled = true;
            const listEl = document.getElementById('tv-asset-list');
            if (listEl) listEl.innerHTML = '<p class="empty">자산을 검색하세요</p>';
        }
    }, { exchange: 'all', showBadge: false });
}

// 2. Premium Strategy: 커스텀 전략 종목 선택
function initCustomSymbolAutocomplete() {
    const input = document.getElementById('custom-symbol');
    if (!input || customSymbolAutocomplete) return;

    customSymbolAutocomplete = createSymbolAutocomplete(input, (symbol) => {
        if (symbol) {
            input.dataset.selectedCode = symbol.code;
            input.dataset.selectedExchange = symbol.exchange;
        } else {
            delete input.dataset.selectedCode;
            delete input.dataset.selectedExchange;
        }
    }, { exchange: 'all', showBadge: true });
}

// 3. Premium Strategy: 역추세 전략 종목 선택
function initReversalSymbolAutocomplete() {
    const input = document.getElementById('reversal-symbol');
    if (!input || reversalSymbolAutocomplete) return;

    reversalSymbolAutocomplete = createSymbolAutocomplete(input, (symbol) => {
        if (symbol) {
            input.dataset.selectedCode = symbol.code;
            input.dataset.selectedExchange = symbol.exchange;
        } else {
            delete input.dataset.selectedCode;
            delete input.dataset.selectedExchange;
        }
    }, { exchange: 'all', showBadge: true });
}

// 4. Premium Strategy: 추세 전략 종목 선택
function initTrendSymbolAutocomplete() {
    const input = document.getElementById('trend-symbol');
    if (!input || trendSymbolAutocomplete) return;

    trendSymbolAutocomplete = createSymbolAutocomplete(input, (symbol) => {
        if (symbol) {
            input.dataset.selectedCode = symbol.code;
            input.dataset.selectedExchange = symbol.exchange;
        } else {
            delete input.dataset.selectedCode;
            delete input.dataset.selectedExchange;
        }
    }, { exchange: 'all', showBadge: true });
}

// 5. Stock KR: 종목 검색 자동완성
function initStockKrAutocomplete() {
    const input = document.getElementById('stock-kr-search');
    if (!input || stockKrAutocomplete) return;

    stockKrAutocomplete = createSymbolAutocomplete(input, (symbol) => {
        if (symbol) {
            // 미니 차트 프리뷰 표시
            showStockKrPreview(symbol);
        } else {
            hideStockKrPreview();
        }
    }, { exchange: 'kis_kr', showBadge: false });
}

// Stock KR 프리뷰 표시
async function showStockKrPreview(symbol) {
    const preview = document.getElementById('stock-kr-preview');
    if (!preview) return;

    document.getElementById('preview-stock-name').textContent = symbol.name;
    document.getElementById('preview-stock-code').textContent = symbol.code;
    preview.style.display = 'block';

    try {
        const detail = await invokeWithTimeout('get_symbol_detail', {
            accessToken: auth.accessToken || '',
            symbol: symbol.code,
            exchange: 'KIS_KR'
        }, 5000);

        if (detail) {
            const priceEl = document.getElementById('preview-price');
            const changeEl = document.getElementById('preview-change');
            const rsEl = document.getElementById('preview-rs');

            if (priceEl) priceEl.textContent = detail.price_formatted || detail.price || '-';
            if (changeEl) {
                const change = detail.change || 0;
                changeEl.textContent = (change >= 0 ? '+' : '') + change.toFixed(2) + '%';
                changeEl.className = change >= 0 ? 'positive' : 'negative';
            }
            if (rsEl) rsEl.textContent = detail.rs_total || '-';
        }
    } catch (e) {
        console.error('Failed to load stock preview:', e);
    }
}

function hideStockKrPreview() {
    const preview = document.getElementById('stock-kr-preview');
    if (preview) preview.style.display = 'none';
}

// 6. Watchlist: 종목 추가 모달 자동완성
let watchlistAddModal = null;
let watchlistAddSelectedSymbol = null;

function showWatchlistAddModal() {
    // 기존 모달이 없으면 생성
    if (!watchlistAddModal) {
        watchlistAddModal = document.createElement('div');
        watchlistAddModal.className = 'modal';
        watchlistAddModal.id = 'watchlist-add-modal';
        watchlistAddModal.innerHTML = `
            <div class="modal-content" style="max-width: 400px;">
                <div class="modal-header">
                    <h3>종목 추가</h3>
                    <button class="close-btn" id="close-watchlist-add-modal">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>종목 검색</label>
                        <input type="text" id="watchlist-add-search" class="form-input" placeholder="종목명 또는 종목코드 검색..." autocomplete="off">
                    </div>
                    <div class="form-group">
                        <label>메모 (선택)</label>
                        <input type="text" id="watchlist-add-memo" class="form-input" placeholder="메모 입력">
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" id="btn-cancel-watchlist-add">취소</button>
                    <button class="btn btn-primary" id="btn-confirm-watchlist-add" disabled>추가</button>
                </div>
            </div>
        `;
        document.body.appendChild(watchlistAddModal);

        // 이벤트 바인딩
        document.getElementById('close-watchlist-add-modal').addEventListener('click', hideWatchlistAddModal);
        document.getElementById('btn-cancel-watchlist-add').addEventListener('click', hideWatchlistAddModal);
        document.getElementById('btn-confirm-watchlist-add').addEventListener('click', confirmWatchlistAdd);

        // 자동완성 초기화
        const searchInput = document.getElementById('watchlist-add-search');
        watchlistAddAutocomplete = createSymbolAutocomplete(searchInput, (symbol) => {
            watchlistAddSelectedSymbol = symbol;
            document.getElementById('btn-confirm-watchlist-add').disabled = !symbol;
        }, { exchange: 'all', showBadge: true });
    }

    watchlistAddSelectedSymbol = null;
    document.getElementById('watchlist-add-search').value = '';
    document.getElementById('watchlist-add-memo').value = '';
    document.getElementById('btn-confirm-watchlist-add').disabled = true;
    watchlistAddModal.style.display = 'flex';
}

function hideWatchlistAddModal() {
    if (watchlistAddModal) {
        watchlistAddModal.style.display = 'none';
    }
}

async function confirmWatchlistAdd() {
    if (!watchlistAddSelectedSymbol) {
        showToast('종목을 선택해주세요', 'warning');
        return;
    }

    const memo = document.getElementById('watchlist-add-memo')?.value || '';
    const group = document.querySelector('.group-tab.active')?.dataset.group || 'default';

    try {
        await invokeWithTimeout('add_watchlist_item', {
            accessToken: auth.accessToken || '',
            groupName: group,
            symbol: watchlistAddSelectedSymbol.code,
            exchange: watchlistAddSelectedSymbol.exchange,
            memo: memo
        }, 5000);

        showToast(`${watchlistAddSelectedSymbol.name} 관심종목에 추가됨`, 'success');
        hideWatchlistAddModal();
        loadWatchlistItems(group); // 리스트 새로고침
    } catch (e) {
        showToast('종목 추가 실패: ' + e, 'error');
    }
}

// Watchlist 종목 추가 버튼 이벤트
document.getElementById('btn-add-watchlist-item')?.addEventListener('click', showWatchlistAddModal);

// 페이지 로드 시 자동완성 초기화
function initAllAutocompletes() {
    initTVAssetAutocomplete();
    initStockKrAutocomplete();
}

// TV Connect 페이지 로드 시 자동완성 초기화
const originalLoadTVConnectPage = typeof loadTVConnectPage === 'function' ? loadTVConnectPage : null;

// Premium Strategy 페이지 로드 시 자동완성 초기화
function initPremiumStrategyAutocomplete() {
    initCustomSymbolAutocomplete();
    initReversalSymbolAutocomplete();
    initTrendSymbolAutocomplete();
}

// =====================================================
// Symbols Page (PHASE 5) — Real Exchange API Integration
// =====================================================
let currentSymbolExchange = 'all';
let symbolsData = [];
let symbolSearchTimeout = null;
let isSymbolsLoading = false;

// 디바운스 함수
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

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

function showSymbolsLoading() {
    const tbody = document.getElementById('symbols-tbody');
    if (!tbody) return;
    isSymbolsLoading = true;
    tbody.innerHTML = `
        <tr>
            <td colspan="6" class="empty-cell">
                <div class="loading-spinner"></div>
                <span style="margin-left: 8px;">거래소에서 데이터 로딩 중...</span>
            </td>
        </tr>
    `;
}

async function loadPopularSymbols() {
    const tbody = document.getElementById('symbols-tbody');
    if (!tbody) return;

    showSymbolsLoading();

    try {
        let allSymbols = [];

        if (auth.accessToken) {
            // 거래소 필터에 따라 인기 종목 조회
            const exchangeParam = currentSymbolExchange === 'all' ? null : currentSymbolExchange;
            const data = await invoke('get_popular_symbols', {
                accessToken: auth.accessToken,
                exchange: exchangeParam
            });

            // 각 거래소별 결과 합치기
            if (data.okx) allSymbols = allSymbols.concat(data.okx);
            if (data.binance) allSymbols = allSymbols.concat(data.binance);
            if (data.bybit) allSymbols = allSymbols.concat(data.bybit);
            if (data.upbit) allSymbols = allSymbols.concat(data.upbit);
            if (data.kis_kr) allSymbols = allSymbols.concat(data.kis_kr);
            if (data.kis_kr_etf) allSymbols = allSymbols.concat(data.kis_kr_etf);
            if (data.kis_us) allSymbols = allSymbols.concat(data.kis_us);
            if (data.kis_us_etf) allSymbols = allSymbols.concat(data.kis_us_etf);

            // 현재 선택된 거래소만 필터
            if (currentSymbolExchange !== 'all') {
                allSymbols = allSymbols.filter(s => {
                    const exLower = s.exchange.toLowerCase().replace(/_/g, '-');
                    const filterLower = currentSymbolExchange.toLowerCase().replace(/_/g, '-');
                    return exLower === filterLower;
                });
            }
        }

        symbolsData = allSymbols;
        renderSymbolsTable(allSymbols);
    } catch (error) {
        console.error('Failed to load popular symbols:', error);
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">인기 종목 로딩 실패</td></tr>';
    } finally {
        isSymbolsLoading = false;
    }
}

async function searchSymbols(query) {
    const tbody = document.getElementById('symbols-tbody');
    if (!tbody) return;

    showSymbolsLoading();

    try {
        const exchange = currentSymbolExchange === 'all' ? null : currentSymbolExchange;
        const result = await invoke('search_symbols', {
            accessToken: auth.accessToken || '',
            query: query,
            exchange: exchange
        });

        // result.symbols 또는 result 자체가 배열인 경우 처리
        const symbols = result.symbols || result || [];
        symbolsData = symbols;
        renderSymbolsTable(symbols);
    } catch (error) {
        console.error('Failed to search symbols:', error);
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">검색 실패</td></tr>';
    } finally {
        isSymbolsLoading = false;
    }
}

// 디바운스된 검색 함수 (300ms)
const debouncedSearch = debounce((query) => {
    if (query) {
        searchSymbols(query);
    } else {
        loadPopularSymbols();
    }
}, 300);

function renderSymbolsTable(symbols) {
    const tbody = document.getElementById('symbols-tbody');
    if (!tbody) return;

    if (!symbols || symbols.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">검색 결과 없음</td></tr>';
        return;
    }

    tbody.innerHTML = symbols.map(s => {
        // exchange badge 클래스 결정 (kis_kr, kis_us 처리)
        const exchangeLower = (s.exchange || '').toLowerCase().replace('_', '-');
        const exchangeDisplay = s.exchange.replace('_', ' ').toUpperCase();

        return `
            <tr data-symbol="${s.symbol}" data-exchange="${s.exchange}" style="cursor: pointer;">
                <td><strong>${s.symbol}</strong></td>
                <td>${s.name || s.symbol}</td>
                <td><span class="exchange-badge ${exchangeLower}">${exchangeDisplay}</span></td>
                <td>${s.price_formatted || 'N/A'}</td>
                <td class="${(s.change || 0) >= 0 ? 'profit' : 'loss'}">${s.change_formatted || '0.00%'}</td>
                <td>${s.volume_formatted || '0'}</td>
            </tr>
        `;
    }).join('');

    tbody.querySelectorAll('tr[data-symbol]').forEach(row => {
        row.addEventListener('click', () => showSymbolDetail(row.dataset.symbol, row.dataset.exchange));
    });
}

let currentSymbolData = null;

async function showSymbolDetail(symbol, exchange) {
    const panel = document.getElementById('symbol-detail-panel');
    if (!panel) return;

    // 현재 심볼 정보 저장 (AI/관심종목 버튼용)
    currentDetailSymbol = symbol;
    currentDetailExchange = exchange;

    const isKIS = exchange.toLowerCase().startsWith('kis');

    // 기본 정보 초기화
    document.getElementById('detail-symbol-name').textContent = symbol;
    const exchangeDisplay = exchange.replace('_', ' ').toUpperCase();
    document.getElementById('detail-exchange').textContent = exchangeDisplay;
    document.getElementById('detail-exchange').className = `exchange-badge ${exchange.toLowerCase().replace('_', '-')}`;
    document.getElementById('detail-market').style.display = 'none';
    document.getElementById('detail-etf-badge').style.display = 'none';

    // 탭 초기화 (시세 탭 활성화)
    document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
    document.querySelector('.detail-tab[data-tab="price"]')?.classList.add('active');
    document.querySelectorAll('.detail-tab-content').forEach(c => c.style.display = 'none');
    document.getElementById('detail-tab-price').style.display = 'block';

    // KIS 탭 표시/숨김
    const finTab = document.querySelector('.detail-tab[data-tab="financial"]');
    const opTab = document.querySelector('.detail-tab[data-tab="opinion"]');
    if (finTab) finTab.style.display = isKIS ? 'inline-block' : 'none';
    if (opTab) opTab.style.display = isKIS ? 'inline-block' : 'none';

    panel.style.display = 'block';

    // 로딩 상태 표시
    document.getElementById('detail-price').textContent = '로딩...';
    document.getElementById('detail-change').textContent = '-';
    document.getElementById('detail-high').textContent = '-';
    document.getElementById('detail-low').textContent = '-';
    document.getElementById('detail-volume').textContent = '-';
    document.getElementById('detail-market-cap').textContent = '-';
    const sourceEl = document.getElementById('detail-source');
    if (sourceEl) sourceEl.style.display = 'none';

    try {
        const detail = await invoke('get_symbol_detail', {
            accessToken: auth.accessToken || '',
            symbol: symbol,
            exchange: exchange
        });

        currentSymbolData = detail;

        // 기본 정보
        if (detail.basic) {
            document.getElementById('detail-symbol-name').textContent = detail.basic.name || symbol;
            if (detail.basic.market) {
                document.getElementById('detail-market').textContent = detail.basic.market;
                document.getElementById('detail-market').style.display = 'inline-block';
            }
            if (detail.basic.is_etf) {
                document.getElementById('detail-etf-badge').style.display = 'inline-block';
            }
        }

        // 가격 정보
        if (detail.price) {
            document.getElementById('detail-price').textContent = detail.price.current_formatted || 'N/A';
            const changeEl = document.getElementById('detail-change');
            changeEl.textContent = detail.price.change_formatted || 'N/A';
            changeEl.className = `price-change ${(detail.price.change || 0) >= 0 ? 'profit' : 'loss'}`;
            document.getElementById('detail-high').textContent = detail.price.high_formatted || '-';
            document.getElementById('detail-low').textContent = detail.price.low_formatted || '-';
            document.getElementById('detail-volume').textContent = detail.price.volume_formatted || '-';
            document.getElementById('detail-market-cap').textContent = detail.price.market_cap_formatted || '-';

            // 데이터 출처 표시
            const sourceEl = document.getElementById('detail-source');
            if (sourceEl) {
                const source = detail.price.source || (detail.has_kis_account ? 'kis' : '');
                if (source === 'naver') {
                    sourceEl.textContent = '네이버 금융';
                    sourceEl.className = 'data-source naver';
                    sourceEl.style.display = 'inline-block';
                } else if (source === 'yahoo') {
                    sourceEl.textContent = 'Yahoo Finance';
                    sourceEl.className = 'data-source yahoo';
                    sourceEl.style.display = 'inline-block';
                } else if (source === 'kis' || detail.has_kis_account) {
                    sourceEl.textContent = 'KIS API';
                    sourceEl.className = 'data-source kis';
                    sourceEl.style.display = 'inline-block';
                } else if (source === 'krx') {
                    sourceEl.textContent = 'KRX';
                    sourceEl.className = 'data-source naver';
                    sourceEl.style.display = 'inline-block';
                } else {
                    sourceEl.style.display = 'none';
                }
            }
        }

        // 일봉 차트 그리기
        if (detail.daily_prices && detail.daily_prices.length > 0) {
            drawDailyChart(detail.daily_prices, detail.price?.change || 0);
        } else if (detail.price?.current) {
            drawSimulatedChart(detail.price.current, detail.price?.change || 0);
        }

        // 투자자 동향 (국내주식만)
        if (detail.investor && detail.investor.length > 0) {
            document.getElementById('investor-trend-section').style.display = 'block';
            drawInvestorChart(detail.investor);
        } else {
            document.getElementById('investor-trend-section').style.display = 'none';
        }

        // 재무 탭 (국내주식만)
        if (isKIS) {
            if (detail.has_kis_account && detail.financial) {
                document.getElementById('financial-notice').style.display = 'none';
                document.getElementById('financial-content').style.display = 'block';
                document.getElementById('fin-per').textContent = detail.financial.per?.toFixed(2) || '-';
                document.getElementById('fin-pbr').textContent = detail.financial.pbr?.toFixed(2) || '-';
                document.getElementById('fin-roe').textContent = (detail.financial.roe?.toFixed(2) || '-') + '%';
                document.getElementById('fin-debt').textContent = (detail.financial.debt_ratio?.toFixed(1) || '-') + '%';

                if (detail.financial.income_statement) {
                    drawIncomeChart(detail.financial.income_statement);
                }
            } else {
                document.getElementById('financial-notice').style.display = 'block';
                document.getElementById('financial-content').style.display = 'none';
            }

            // 투자의견 탭
            if (detail.has_kis_account && detail.opinion) {
                document.getElementById('opinion-notice').style.display = 'none';
                document.getElementById('opinion-content').style.display = 'block';
                document.getElementById('consensus-badge').textContent = detail.opinion.consensus || '-';
                document.getElementById('consensus-badge').className = `consensus-badge ${detail.opinion.consensus === '매수' ? 'buy' : (detail.opinion.consensus === '매도' ? 'sell' : 'hold')}`;
                document.getElementById('target-price').textContent = detail.opinion.target_price_formatted || '-';
                document.getElementById('analyst-count').textContent = detail.opinion.analyst_count || 0;
                document.getElementById('buy-count').textContent = detail.opinion.buy_count || 0;
                document.getElementById('hold-count').textContent = detail.opinion.hold_count || 0;
                document.getElementById('sell-count').textContent = detail.opinion.sell_count || 0;

                drawOpinionChart(detail.opinion);
            } else {
                document.getElementById('opinion-notice').style.display = 'block';
                document.getElementById('opinion-content').style.display = 'none';
            }
        }

    } catch (error) {
        console.error('Failed to load symbol detail:', error);
        document.getElementById('detail-price').textContent = '조회 실패';
    }
}

// 상세 탭 전환
document.querySelectorAll('.detail-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const tabName = tab.dataset.tab;
        document.querySelectorAll('.detail-tab-content').forEach(c => c.style.display = 'none');
        document.getElementById(`detail-tab-${tabName}`).style.display = 'block';
    });
});

function drawDailyChart(dailyPrices, change) {
    const canvas = document.getElementById('mini-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const prices = dailyPrices.map(d => d.close).reverse();
    if (prices.length === 0) return;

    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;

    // 배경 그라데이션
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, change >= 0 ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)');
    gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');

    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.moveTo(0, height);

    prices.forEach((p, i) => {
        const x = (i / (prices.length - 1)) * width;
        const y = height - ((p - min) / range) * height * 0.8 - height * 0.1;
        ctx.lineTo(x, y);
    });
    ctx.lineTo(width, height);
    ctx.closePath();
    ctx.fill();

    // 라인 그리기
    ctx.strokeStyle = change >= 0 ? '#22C55E' : '#EF4444';
    ctx.lineWidth = 2;
    ctx.beginPath();
    prices.forEach((p, i) => {
        const x = (i / (prices.length - 1)) * width;
        const y = height - ((p - min) / range) * height * 0.8 - height * 0.1;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.stroke();
}

function drawSimulatedChart(price, change) {
    const canvas = document.getElementById('mini-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    // 시뮬레이션 데이터
    const data = [];
    let value = price * 0.97;
    for (let i = 0; i < 60; i++) {
        value += (Math.random() - 0.45) * price * 0.005;
        data.push(value);
    }
    data.push(price);

    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;

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

function drawInvestorChart(investorData) {
    const canvas = document.getElementById('investor-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const barWidth = width / (investorData.length * 4);
    const maxVal = Math.max(...investorData.flatMap(d => [Math.abs(d.foreign_net), Math.abs(d.institution_net), Math.abs(d.individual_net)])) || 1;

    investorData.reverse().forEach((d, i) => {
        const baseX = i * (barWidth * 4) + barWidth / 2;

        // 외국인
        const fH = (d.foreign_net / maxVal) * (height / 2 - 10);
        ctx.fillStyle = '#3B82F6';
        ctx.fillRect(baseX, height / 2 - (fH > 0 ? fH : 0), barWidth * 0.8, Math.abs(fH) || 2);

        // 기관
        const iH = (d.institution_net / maxVal) * (height / 2 - 10);
        ctx.fillStyle = '#F59E0B';
        ctx.fillRect(baseX + barWidth, height / 2 - (iH > 0 ? iH : 0), barWidth * 0.8, Math.abs(iH) || 2);

        // 개인
        const pH = (d.individual_net / maxVal) * (height / 2 - 10);
        ctx.fillStyle = '#EF4444';
        ctx.fillRect(baseX + barWidth * 2, height / 2 - (pH > 0 ? pH : 0), barWidth * 0.8, Math.abs(pH) || 2);
    });

    // 중앙선
    ctx.strokeStyle = '#4B5563';
    ctx.beginPath();
    ctx.moveTo(0, height / 2);
    ctx.lineTo(width, height / 2);
    ctx.stroke();
}

function drawIncomeChart(incomeData) {
    const canvas = document.getElementById('income-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const data = incomeData.reverse();
    const barWidth = width / (data.length * 4);
    const maxVal = Math.max(...data.flatMap(d => [d.revenue, d.operating_profit, d.net_income])) || 1;

    data.forEach((d, i) => {
        const baseX = i * (barWidth * 4) + barWidth / 2;
        const bH = (d.revenue / maxVal) * (height - 30);
        const oH = (d.operating_profit / maxVal) * (height - 30);
        const nH = (d.net_income / maxVal) * (height - 30);

        ctx.fillStyle = '#3B82F6';
        ctx.fillRect(baseX, height - 20 - bH, barWidth * 0.8, bH);

        ctx.fillStyle = '#22C55E';
        ctx.fillRect(baseX + barWidth, height - 20 - oH, barWidth * 0.8, oH);

        ctx.fillStyle = '#F59E0B';
        ctx.fillRect(baseX + barWidth * 2, height - 20 - nH, barWidth * 0.8, nH);

        // 기간 라벨
        ctx.fillStyle = '#9CA3AF';
        ctx.font = '10px sans-serif';
        ctx.fillText(d.period, baseX, height - 5);
    });
}

function drawOpinionChart(opinion) {
    const canvas = document.getElementById('opinion-chart');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) / 2 - 10;

    ctx.clearRect(0, 0, width, height);

    const total = (opinion.buy_count || 0) + (opinion.hold_count || 0) + (opinion.sell_count || 0);
    if (total === 0) return;

    const slices = [
        { value: opinion.buy_count || 0, color: '#22C55E' },
        { value: opinion.hold_count || 0, color: '#F59E0B' },
        { value: opinion.sell_count || 0, color: '#EF4444' },
    ];

    let startAngle = -Math.PI / 2;
    slices.forEach(slice => {
        const sliceAngle = (slice.value / total) * 2 * Math.PI;
        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.arc(centerX, centerY, radius, startAngle, startAngle + sliceAngle);
        ctx.closePath();
        ctx.fillStyle = slice.color;
        ctx.fill();
        startAngle += sliceAngle;
    });

    // 중앙 원 (도넛 효과)
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius * 0.5, 0, 2 * Math.PI);
    ctx.fillStyle = '#1F2937';
    ctx.fill();
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

// Symbol search input with debounce
document.getElementById('symbol-search')?.addEventListener('input', (e) => {
    const query = e.target.value.trim();
    debouncedSearch(query);
});

document.getElementById('symbol-search')?.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        // Enter 시 즉시 검색
        clearTimeout(symbolSearchTimeout);
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

        // 탭 전환 시 해당 거래소 심볼 로드
        const query = document.getElementById('symbol-search')?.value?.trim() || '';
        if (query) {
            searchSymbols(query);
        } else {
            loadPopularSymbols();
        }
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
    // [BUG FIX 3] 자동완성 초기화
    initPremiumStrategyAutocomplete();
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
                        <span>종목:</span>
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
    // 모든 거래소 폼 숨김
    document.querySelectorAll('.exchange-form').forEach(form => form.style.display = 'none');
    // 선택된 거래소 폼만 표시
    const formMap = {
        'OKX': 'okx-form',
        'BINANCE': 'binance-form',
        'BYBIT': 'bybit-form',
        'UPBIT': 'upbit-form',
        'KIS_KR': 'kis-kr-form',
        'KIS_US': 'kis-us-form'
    };
    const formId = formMap[exchange];
    if (formId) {
        document.getElementById(formId).style.display = 'block';
    }
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
    } else if (exchange === 'BINANCE') {
        name = document.getElementById('binance-alias').value;
        apiKey = document.getElementById('binance-api-key').value;
        apiSecret = document.getElementById('binance-secret').value;
        if (!name || !apiKey || !apiSecret) {
            showToast('모든 필드를 입력하세요', 'error');
            return;
        }
    } else if (exchange === 'BYBIT') {
        name = document.getElementById('bybit-alias').value;
        apiKey = document.getElementById('bybit-api-key').value;
        apiSecret = document.getElementById('bybit-secret').value;
        if (!name || !apiKey || !apiSecret) {
            showToast('모든 필드를 입력하세요', 'error');
            return;
        }
    } else if (exchange === 'UPBIT') {
        name = document.getElementById('upbit-alias').value;
        apiKey = document.getElementById('upbit-access-key').value;
        apiSecret = document.getElementById('upbit-secret').value;
        if (!name || !apiKey || !apiSecret) {
            showToast('모든 필드를 입력하세요', 'error');
            return;
        }
    } else if (exchange === 'KIS_KR') {
        name = document.getElementById('kis-kr-alias').value;
        apiKey = document.getElementById('kis-kr-app-key').value;
        apiSecret = document.getElementById('kis-kr-app-secret').value;
        accountNumber = document.getElementById('kis-kr-account-number').value;
        if (!name || !apiKey || !apiSecret || !accountNumber) {
            showToast('모든 필드를 입력하세요', 'error');
            return;
        }
    } else if (exchange === 'KIS_US') {
        name = document.getElementById('kis-us-alias').value;
        apiKey = document.getElementById('kis-us-app-key').value;
        apiSecret = document.getElementById('kis-us-app-secret').value;
        accountNumber = document.getElementById('kis-us-account-number').value;
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
            accountNumber: accountNumber || null
        });

        showToast('계정이 등록되었습니다', 'success');
        document.getElementById('account-form-section').style.display = 'none';
        // 폼 초기화
        document.querySelectorAll('.exchange-form input').forEach(input => input.value = '');
        document.getElementById('account-exchange').value = '';
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
let adminPlanChart = null;

async function loadAdminUsersPage() {
    // 대시보드 통계 로드
    await loadAdminStats();
    // 최근 가입자 로드
    await loadRecentUsers();
    // AI 사용량 로드
    await loadAiUsageStats();
    // 사용자 목록 로드
    await loadUsersList();
}

async function loadAdminStats() {
    try {
        const stats = await invoke('admin_get_stats', { accessToken: auth.accessToken || '' });

        // 상단 카드 업데이트
        document.getElementById('admin-total-users').textContent = stats.total_users || 0;
        document.getElementById('admin-active-users').textContent = stats.active_users || 0;
        document.getElementById('admin-today-signups').textContent = stats.today_signups || 0;
        document.getElementById('admin-today-ai').textContent = stats.today_ai || 0;

        // 요금제별 테이블 업데이트
        const planCounts = stats.plan_counts || {};
        const planPrices = stats.plan_prices || {};
        const total = (planCounts.starter || 0) + (planCounts.standard || 0) + (planCounts.pro || 0) + (planCounts.premium || 0);

        // Starter
        const starterCount = planCounts.starter || planCounts.free || 0;
        document.getElementById('plan-starter-count').textContent = starterCount;
        document.getElementById('plan-starter-pct').textContent = total > 0 ? Math.round(starterCount / total * 100) + '%' : '0%';
        document.getElementById('plan-starter-revenue').textContent = '₩' + (starterCount * 19900).toLocaleString();

        // Standard
        const standardCount = planCounts.standard || planCounts.hub || 0;
        document.getElementById('plan-standard-count').textContent = standardCount;
        document.getElementById('plan-standard-pct').textContent = total > 0 ? Math.round(standardCount / total * 100) + '%' : '0%';
        document.getElementById('plan-standard-revenue').textContent = '₩' + (standardCount * 49000).toLocaleString();

        // Pro
        const proCount = planCounts.pro || 0;
        document.getElementById('plan-pro-count').textContent = proCount;
        document.getElementById('plan-pro-pct').textContent = total > 0 ? Math.round(proCount / total * 100) + '%' : '0%';
        document.getElementById('plan-pro-revenue').textContent = '₩' + (proCount * 99000).toLocaleString();

        // Premium
        const premiumCount = planCounts.premium || 0;
        document.getElementById('plan-premium-count').textContent = premiumCount;
        document.getElementById('plan-premium-pct').textContent = total > 0 ? Math.round(premiumCount / total * 100) + '%' : '0%';
        document.getElementById('plan-premium-revenue').textContent = '₩' + (premiumCount * 249000).toLocaleString();

        // 합계
        const totalRevenue = (starterCount * 19900) + (standardCount * 49000) + (proCount * 99000) + (premiumCount * 249000);
        document.getElementById('plan-total-count').innerHTML = '<strong>' + total + '</strong>';
        document.getElementById('plan-total-revenue').innerHTML = '<strong>₩' + totalRevenue.toLocaleString() + '</strong>';

        // 원형 차트 그리기
        drawAdminPlanChart([starterCount, standardCount, proCount, premiumCount]);

    } catch (e) {
        console.error('Failed to load admin stats:', e);
    }
}

function drawAdminPlanChart(data) {
    const canvas = document.getElementById('admin-plan-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    if (adminPlanChart) adminPlanChart.destroy();

    adminPlanChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Starter', 'Standard', 'Pro', 'Premium'],
            datasets: [{
                data: data,
                backgroundColor: ['#3B82F6', '#22C55E', '#F59E0B', '#EF4444'],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '60%',
            plugins: { legend: { display: false } }
        }
    });
}

async function loadRecentUsers() {
    const tbody = document.getElementById('recent-users-tbody');
    if (!tbody) return;

    try {
        const result = await invoke('admin_get_recent_users', { accessToken: auth.accessToken || '' });
        const users = result.users || [];

        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">최근 가입자 없음</td></tr>';
            return;
        }

        tbody.innerHTML = users.map(user => {
            const planText = getPlanDisplayName(user.plan);
            const createdAt = user.created_at ? user.created_at.split('T')[0] : '-';
            return `
                <tr>
                    <td><strong>${user.name || '-'}</strong><br><small>${user.email}</small></td>
                    <td>${createdAt}</td>
                    <td><span class="plan-badge ${user.plan}">${planText}</span></td>
                    <td><span class="status-badge ${user.is_active ? 'success' : 'error'}">${user.is_active ? '활성' : '비활성'}</span></td>
                </tr>
            `;
        }).join('');

    } catch (e) {
        console.error('Failed to load recent users:', e);
        tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">로딩 실패</td></tr>';
    }
}

function getPlanDisplayName(plan) {
    const names = {
        'starter': 'Starter',
        'standard': 'Standard',
        'pro': 'Pro',
        'premium': 'Premium',
        'free': 'Starter',
        'hub': 'Standard'
    };
    return names[plan] || plan;
}

async function loadAiUsageStats() {
    const tbody = document.getElementById('ai-usage-tbody');
    if (!tbody) return;

    try {
        const stats = await invoke('admin_get_stats', { accessToken: auth.accessToken || '' });
        const aiData = stats.ai_usage_7days || [];

        if (aiData.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="empty-cell">데이터 없음</td></tr>';
            return;
        }

        tbody.innerHTML = aiData.map(d => `
            <tr>
                <td>${d.date}</td>
                <td>${d.count}회</td>
                <td>~${d.tokens.toLocaleString()} 토큰</td>
            </tr>
        `).join('');

    } catch (e) {
        console.error('Failed to load AI usage stats:', e);
        tbody.innerHTML = '<tr><td colspan="3" class="empty-cell">로딩 실패</td></tr>';
    }
}

async function loadUsersList() {
    const tbody = document.getElementById('users-tbody');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">로딩 중...</td></tr>';

    try {
        const users = await invoke('admin_get_users', {
            accessToken: auth.accessToken || '',
            search: null,
            planFilter: null
        });

        if (!users || users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">사용자 없음</td></tr>';
            return;
        }

        tbody.innerHTML = users.map(user => {
            const planText = getPlanDisplayName(user.plan);
            const createdAt = user.created_at ? user.created_at.split('T')[0] : '-';
            const lastLogin = user.last_login_at ? user.last_login_at.split('T')[0] : '-';

            return `
                <tr data-user-id="${user.id}">
                    <td>${user.id}</td>
                    <td>${user.name || '-'}</td>
                    <td>${user.email}</td>
                    <td>
                        <select class="plan-select" data-user-id="${user.id}">
                            <option value="starter" ${user.plan === 'starter' || user.plan === 'free' ? 'selected' : ''}>Starter</option>
                            <option value="standard" ${user.plan === 'standard' || user.plan === 'hub' ? 'selected' : ''}>Standard</option>
                            <option value="pro" ${user.plan === 'pro' ? 'selected' : ''}>Pro</option>
                            <option value="premium" ${user.plan === 'premium' ? 'selected' : ''}>Premium</option>
                        </select>
                    </td>
                    <td>${createdAt}</td>
                    <td>${lastLogin}</td>
                    <td><span class="status-badge ${user.is_active ? 'success' : 'error'}">${user.is_active ? '활성' : '비활성'}</span></td>
                    <td>${user.role === 'admin' ? '<span class="role-badge">관리자</span>' : ''}</td>
                </tr>
            `;
        }).join('');

        // 요금제 변경 이벤트
        tbody.querySelectorAll('.plan-select').forEach(select => {
            select.addEventListener('change', async (e) => {
                const userId = parseInt(e.target.dataset.userId);
                const newPlan = e.target.value;
                try {
                    await invoke('admin_update_user_plan', {
                        accessToken: auth.accessToken || '',
                        userId: userId,
                        plan: newPlan
                    });
                    showToast('요금제가 변경되었습니다', 'success');
                } catch (error) {
                    showToast('요금제 변경 실패', 'error');
                    loadUsersList(); // 롤백
                }
            });
        });

    } catch (e) {
        console.error('Failed to load admin users:', e);
        tbody.innerHTML = '<tr><td colspan="8" class="empty-cell">로딩 실패 (권한 확인)</td></tr>';
    }
}

async function loadAdminSystemPage() {
    try {
        const status = await invoke('admin_get_system_status', { accessToken: auth.accessToken || '' });

        document.getElementById('sys-status').textContent = status.status === 'ok' ? '정상' : '오류';
        document.getElementById('sys-status').className = `system-value ${status.status === 'ok' ? '' : 'error'}`;

        document.getElementById('sys-memory').textContent = `${status.memory_percent.toFixed(1)}%`;
        document.getElementById('sys-db').textContent = status.db_connected ? '정상' : '오류';
        document.getElementById('sys-db').className = `system-value ${status.db_connected ? '' : 'error'}`;

        // 웹훅 통계
        document.getElementById('webhook-total').textContent = status.webhook_total;
        document.getElementById('webhook-success').textContent = status.webhook_success;
        document.getElementById('webhook-failed').textContent = status.webhook_failed;

    } catch (e) {
        console.error('Failed to load system status:', e);
        document.getElementById('sys-status').textContent = '확인 불가';
    }
}

document.getElementById('btn-export-users')?.addEventListener('click', () => showToast('CSV 내보내기 준비 중', 'info'));

// =====================================================
// 시장분석 기능 (STEP 2)
// =====================================================

let currentRankingType = 'volume';
let currentEventType = 'all';

async function loadMarketOverview() {
    const restrictionEl = document.getElementById('market-restriction');
    const contentEl = document.getElementById('market-overview-content');
    if (!restrictionEl || !contentEl) return;

    try {
        const data = await invoke('get_market_overview', { accessToken: auth.accessToken || '' });

        restrictionEl.style.display = 'none';
        contentEl.style.display = 'block';

        // 지수 표시
        const indices = data.indices || {};
        updateIndexCard('index-kospi', indices.kospi);
        updateIndexCard('index-kosdaq', indices.kosdaq);
        updateIndexCard('index-nasdaq', indices.nasdaq);
        updateIndexCard('index-sp500', indices.sp500);
        updateIndexCard('index-dow', indices.dow);

        // 시황 요약
        const summary = data.summary || {};
        document.getElementById('market-status-emoji').textContent = summary.emoji || '🟡';
        document.getElementById('market-status-text').textContent = summary.status || '-';

        const kospiChange = summary.kospi_change || 0;
        const kosdaqChange = summary.kosdaq_change || 0;
        document.getElementById('market-summary-text').textContent =
            `코스피 ${kospiChange >= 0 ? '+' : ''}${kospiChange.toFixed(2)}%, ` +
            `코스닥 ${kosdaqChange >= 0 ? '+' : ''}${kosdaqChange.toFixed(2)}%`;

        // 투자자 동향
        if (data.investor) {
            updateInvestorBars(data.investor);
            document.getElementById('investor-kis-hint').style.display = 'none';
        } else {
            document.getElementById('investor-kis-hint').style.display = data.has_kis_account ? 'none' : 'block';
        }

    } catch (error) {
        console.error('Market overview error:', error);
        if (error.toString().includes('Pro')) {
            restrictionEl.style.display = 'flex';
            contentEl.style.display = 'none';
        }
    }
}

function updateIndexCard(cardId, data) {
    const card = document.getElementById(cardId);
    if (!card || !data) return;

    const valueEl = card.querySelector('.index-value');
    const changeEl = card.querySelector('.index-change');

    valueEl.textContent = data.current?.toLocaleString() || '-';
    const change = data.change || 0;
    changeEl.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(2)}%`;
    changeEl.className = `index-change ${change >= 0 ? 'profit' : 'loss'}`;
}

function updateInvestorBars(investor) {
    const maxVal = Math.max(
        Math.abs(investor.foreign_net || 0),
        Math.abs(investor.institution_net || 0),
        Math.abs(investor.individual_net || 0)
    ) || 1;

    updateInvestorBar('foreign', investor.foreign_net || 0, maxVal);
    updateInvestorBar('institution', investor.institution_net || 0, maxVal);
    updateInvestorBar('individual', investor.individual_net || 0, maxVal);
}

function updateInvestorBar(type, value, maxVal) {
    const bar = document.getElementById(`bar-${type}`);
    const valueEl = document.getElementById(`investor-${type}`);
    if (!bar || !valueEl) return;

    const pct = Math.min(Math.abs(value) / maxVal * 100, 100);
    bar.style.width = `${pct}%`;
    bar.classList.toggle('negative', value < 0);

    const formatted = formatKoreanNumber(Math.abs(value));
    valueEl.textContent = `${value >= 0 ? '+' : '-'}${formatted}`;
    valueEl.className = `value ${value >= 0 ? 'profit' : 'loss'}`;
}

function formatKoreanNumber(num) {
    if (num >= 100000000) return (num / 100000000).toFixed(1) + '억';
    if (num >= 10000) return (num / 10000).toFixed(1) + '만';
    return num.toLocaleString();
}

async function loadSectorAnalysis() {
    const restrictionEl = document.getElementById('sector-restriction');
    const leadingEl = document.getElementById('leading-sectors');
    const laggingEl = document.getElementById('lagging-sectors');
    const tbody = document.getElementById('sector-tbody');
    if (!tbody) return;

    try {
        const data = await invoke('get_market_sectors', { accessToken: auth.accessToken || '' });

        if (restrictionEl) restrictionEl.style.display = 'none';

        // 주도/부진 업종
        if (leadingEl && data.leading) {
            leadingEl.innerHTML = data.leading.map(s =>
                `<span class="sector-tag positive">${s.name} +${s.change?.toFixed(2)}%</span>`
            ).join('');
        }
        if (laggingEl && data.lagging) {
            laggingEl.innerHTML = data.lagging.map(s =>
                `<span class="sector-tag negative">${s.name} ${s.change?.toFixed(2)}%</span>`
            ).join('');
        }

        // 테이블
        const sectors = data.sectors || [];
        tbody.innerHTML = sectors.map(s => `
            <tr>
                <td>${s.name || '-'}</td>
                <td>${s.current?.toLocaleString() || '-'}</td>
                <td class="${(s.change || 0) >= 0 ? 'profit' : 'loss'}">${s.change >= 0 ? '+' : ''}${s.change?.toFixed(2) || 0}%</td>
            </tr>
        `).join('') || '<tr><td colspan="3" class="empty-cell">데이터 없음</td></tr>';

    } catch (error) {
        console.error('Sector analysis error:', error);
        if (error.toString().includes('Pro') && restrictionEl) {
            restrictionEl.style.display = 'flex';
        }
    }
}

async function loadStockRanking(rankingType = 'volume', market = 'all') {
    const restrictionEl = document.getElementById('ranking-restriction');
    const tbody = document.getElementById('ranking-tbody');
    const headerEl = document.getElementById('ranking-extra-header');
    if (!tbody) return;

    currentRankingType = rankingType;

    // 헤더 업데이트
    const headers = {
        volume: '거래량', rise: '등락률', fall: '등락률',
        market_cap: '시가총액', foreign_buy: '외인순매수', foreign_sell: '외인순매도',
        institution_buy: '기관순매수', institution_sell: '기관순매도'
    };
    if (headerEl) headerEl.textContent = headers[rankingType] || '거래량';

    tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">로딩 중...</td></tr>';

    try {
        const data = await invoke('get_stock_ranking', {
            accessToken: auth.accessToken || '',
            rankingType: rankingType,
            market: market
        });

        if (restrictionEl) restrictionEl.style.display = 'none';

        const stocks = data.stocks || [];
        tbody.innerHTML = stocks.map(s => {
            let extraValue = '';
            if (rankingType === 'volume') extraValue = formatKoreanNumber(s.volume || 0);
            else if (rankingType === 'market_cap') extraValue = formatKoreanNumber((s.market_cap || 0) * 100000000);
            else if (rankingType.includes('foreign')) extraValue = formatKoreanNumber(Math.abs(s.foreign_net_qty || 0));
            else if (rankingType.includes('institution')) extraValue = formatKoreanNumber(Math.abs(s.institution_net_qty || 0));
            else extraValue = `${s.change >= 0 ? '+' : ''}${s.change?.toFixed(2)}%`;

            return `
                <tr onclick="showSymbolDetail('${s.code}', 'kis_kr')">
                    <td>${s.rank || '-'}</td>
                    <td>${s.name || '-'}</td>
                    <td>₩${(s.current || 0).toLocaleString()}</td>
                    <td class="${(s.change || 0) >= 0 ? 'profit' : 'loss'}">${s.change >= 0 ? '+' : ''}${s.change?.toFixed(2) || 0}%</td>
                    <td>${extraValue}</td>
                </tr>
            `;
        }).join('') || '<tr><td colspan="5" class="empty-cell">데이터 없음</td></tr>';

    } catch (error) {
        console.error('Stock ranking error:', error);
        if (error.toString().includes('Pro') && restrictionEl) {
            restrictionEl.style.display = 'flex';
        }
        tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">데이터를 불러올 수 없습니다</td></tr>';
    }
}

async function loadFeaturedStocks() {
    const restrictionEl = document.getElementById('featured-restriction');

    try {
        const data = await invoke('get_featured_stocks', { accessToken: auth.accessToken || '' });

        if (restrictionEl) restrictionEl.style.display = 'none';

        // 상한가/하한가/급등/급락
        updateFeaturedList('upper-limit-list', data.upper_limit || []);
        updateFeaturedList('lower-limit-list', data.lower_limit || []);
        updateFeaturedList('surge-list', data.surge || []);
        updateFeaturedList('plunge-list', data.plunge || []);

        // 상승/하락 TOP 10
        updateFeaturedTable('rise-top-tbody', data.rise_top || []);
        updateFeaturedTable('fall-top-tbody', data.fall_top || []);

    } catch (error) {
        console.error('Featured stocks error:', error);
        if (error.toString().includes('Pro') && restrictionEl) {
            restrictionEl.style.display = 'flex';
        }
    }
}

function updateFeaturedList(containerId, stocks) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (stocks.length === 0) {
        container.innerHTML = '<div class="featured-item"><span class="name">-</span></div>';
        return;
    }

    container.innerHTML = stocks.slice(0, 5).map(s => `
        <div class="featured-item" onclick="showSymbolDetail('${s.code}', 'kis_kr')">
            <span class="name">${s.name || '-'}</span>
            <span class="change ${(s.change || 0) >= 0 ? 'profit' : 'loss'}">${s.change >= 0 ? '+' : ''}${s.change?.toFixed(2)}%</span>
        </div>
    `).join('');
}

function updateFeaturedTable(tbodyId, stocks) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;

    tbody.innerHTML = stocks.map(s => `
        <tr onclick="showSymbolDetail('${s.code}', 'kis_kr')">
            <td>${s.rank || '-'}</td>
            <td>${s.name || '-'}</td>
            <td>₩${(s.current || 0).toLocaleString()}</td>
            <td class="${(s.change || 0) >= 0 ? 'profit' : 'loss'}">${s.change >= 0 ? '+' : ''}${s.change?.toFixed(2)}%</td>
        </tr>
    `).join('') || '<tr><td colspan="4" class="empty-cell">-</td></tr>';
}

async function loadMarketEvents(eventType = 'all') {
    const restrictionEl = document.getElementById('events-restriction');
    const kisNotice = document.getElementById('events-kis-notice');
    const tbody = document.getElementById('events-tbody');
    if (!tbody) return;

    currentEventType = eventType;
    tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">로딩 중...</td></tr>';

    try {
        const data = await invoke('get_market_events', {
            accessToken: auth.accessToken || '',
            eventType: eventType,
            month: null
        });

        if (restrictionEl) restrictionEl.style.display = 'none';

        if (!data.has_kis_account && kisNotice) {
            kisNotice.style.display = 'block';
            tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">KIS 계정 등록 필요</td></tr>';
            return;
        }

        if (kisNotice) kisNotice.style.display = 'none';

        const events = data.events || [];
        const typeLabels = { dividend: '배당', ipo: '공모주', rights: '유상증자', bonus: '무상증자' };

        tbody.innerHTML = events.map(e => {
            let detail = '';
            if (e.type === 'dividend') detail = `${e.amount?.toLocaleString()}원 (${e.yield}%)`;
            else if (e.type === 'ipo') detail = `공모가 ${e.price?.toLocaleString()}원`;
            else detail = '-';

            return `
                <tr>
                    <td>${typeLabels[e.type] || e.type}</td>
                    <td>${e.stock_name || '-'}</td>
                    <td>${e.date || e.date_start || '-'}</td>
                    <td>${detail}</td>
                </tr>
            `;
        }).join('') || '<tr><td colspan="4" class="empty-cell">예정된 이벤트 없음</td></tr>';

    } catch (error) {
        console.error('Market events error:', error);
        if (error.toString().includes('Pro') && restrictionEl) {
            restrictionEl.style.display = 'flex';
        }
        tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">데이터를 불러올 수 없습니다</td></tr>';
    }
}

// 시장분석 탭 이벤트
document.querySelectorAll('.ranking-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.ranking-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const marketSelect = document.getElementById('ranking-market-filter');
        loadStockRanking(tab.dataset.type, marketSelect?.value || 'all');
    });
});

document.getElementById('ranking-market-filter')?.addEventListener('change', (e) => {
    loadStockRanking(currentRankingType, e.target.value);
});

document.querySelectorAll('.event-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.event-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        loadMarketEvents(tab.dataset.type);
    });
});

// =====================================================
// AI 분석 + 관심종목 (STEP 3)
// =====================================================

let currentDetailSymbol = null;
let currentDetailExchange = null;

// AI 분석 버튼 클릭
document.getElementById('btn-ai-analysis')?.addEventListener('click', async () => {
    if (!currentSymbolData) {
        showToast('종목을 먼저 선택하세요', 'error');
        return;
    }

    const modal = document.getElementById('ai-modal');
    const loadingEl = document.getElementById('ai-loading');
    const reportEl = document.getElementById('ai-report');
    const errorEl = document.getElementById('ai-error');
    const usageEl = document.getElementById('ai-usage');

    modal.style.display = 'flex';
    loadingEl.style.display = 'block';
    reportEl.style.display = 'none';
    errorEl.style.display = 'none';

    try {
        const result = await invoke('request_ai_analysis', {
            accessToken: auth.accessToken || '',
            symbol: currentSymbolData.basic?.symbol || currentDetailSymbol,
            exchange: currentSymbolData.basic?.exchange || currentDetailExchange
        });

        loadingEl.style.display = 'none';

        if (result.success) {
            reportEl.innerHTML = markdownToHtml(result.report || '');
            reportEl.style.display = 'block';
            // 일일/월간 사용량 표시
            const dailyRemain = (result.daily_max || 0) - (result.daily_used || 0);
            const monthlyRemain = (result.monthly_max || 0) - (result.monthly_used || 0);
            usageEl.textContent = `오늘 ${result.daily_used}/${result.daily_max}회 | 이번 달 ${result.monthly_used}/${result.monthly_max}회`;
        } else {
            errorEl.textContent = result.error || 'AI 분석에 실패했습니다';
            errorEl.style.display = 'block';
            // 제한 초과 시에도 사용량 표시
            if (result.daily_max !== undefined) {
                usageEl.textContent = `오늘 ${result.daily_used}/${result.daily_max}회 | 이번 달 ${result.monthly_used}/${result.monthly_max}회`;
            }
        }
    } catch (error) {
        loadingEl.style.display = 'none';
        errorEl.textContent = error.toString();
        errorEl.style.display = 'block';
    }
});

// 간단한 마크다운 변환
function markdownToHtml(md) {
    return md
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/^- (.*$)/gim, '<li>$1</li>')
        .replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>')
        .replace(/^---$/gim, '<hr>')
        .replace(/\n/g, '<br>');
}

// AI 모달 닫기
document.getElementById('ai-modal-close')?.addEventListener('click', () => {
    document.getElementById('ai-modal').style.display = 'none';
});

document.getElementById('ai-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'ai-modal') {
        document.getElementById('ai-modal').style.display = 'none';
    }
});

// 관심종목 추가 버튼 클릭
document.getElementById('btn-add-watchlist')?.addEventListener('click', async () => {
    if (!currentSymbolData) {
        showToast('종목을 먼저 선택하세요', 'error');
        return;
    }

    const modal = document.getElementById('watchlist-modal');
    const groupsList = document.getElementById('watchlist-groups-list');

    modal.style.display = 'flex';
    groupsList.innerHTML = '<div class="loading">로딩 중...</div>';

    try {
        const data = await invoke('get_watchlist_groups', { accessToken: auth.accessToken || '' });
        const groups = data.groups || [];

        groupsList.innerHTML = groups.map(g => `
            <div class="watchlist-group-item" data-group-id="${g.id}">
                <span class="group-name">${g.name}</span>
            </div>
        `).join('') || '<div class="empty">그룹이 없습니다</div>';

        // 그룹 클릭 이벤트
        groupsList.querySelectorAll('.watchlist-group-item').forEach(item => {
            item.addEventListener('click', async () => {
                const groupId = parseInt(item.dataset.groupId);
                await addToWatchlist(groupId);
            });
        });
    } catch (error) {
        groupsList.innerHTML = '<div class="error">그룹 로딩 실패</div>';
    }
});

async function addToWatchlist(groupId) {
    try {
        await invoke('add_watchlist_item', {
            accessToken: auth.accessToken || '',
            groupId: groupId,
            symbol: currentSymbolData.basic?.symbol || currentDetailSymbol,
            exchange: currentSymbolData.basic?.exchange || currentDetailExchange
        });
        showToast('관심종목에 추가되었습니다', 'success');
        document.getElementById('watchlist-modal').style.display = 'none';
    } catch (error) {
        showToast(error.toString(), 'error');
    }
}

// 새 그룹 생성
document.getElementById('btn-create-group')?.addEventListener('click', async () => {
    const nameInput = document.getElementById('new-group-name');
    const name = nameInput.value.trim();
    if (!name) {
        showToast('그룹 이름을 입력하세요', 'error');
        return;
    }

    try {
        await invoke('create_watchlist_group', {
            accessToken: auth.accessToken || '',
            name: name
        });
        nameInput.value = '';
        showToast('그룹이 생성되었습니다', 'success');
        // 목록 새로고침
        document.getElementById('btn-add-watchlist').click();
    } catch (error) {
        showToast(error.toString(), 'error');
    }
});

// 관심종목 모달 닫기
document.getElementById('watchlist-modal-close')?.addEventListener('click', () => {
    document.getElementById('watchlist-modal').style.display = 'none';
});

document.getElementById('watchlist-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'watchlist-modal') {
        document.getElementById('watchlist-modal').style.display = 'none';
    }
});

// =====================================================
// 시장분석 새 페이지 로드 (STEP A)
// =====================================================

// 국내시장 로드
async function loadMarketKr() {
    const restrictionEl = document.getElementById('market-kr-restriction');
    const contentEl = document.getElementById('market-kr-content');
    if (!restrictionEl || !contentEl) return;

    // auth.user가 없으면 먼저 로드 시도
    if (!auth.user && auth.accessToken) {
        await loadUserInfo();
    }

    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';
    const isPro = ['pro', 'premium'].includes(plan) || role === 'admin';

    if (!isPro) {
        restrictionEl.style.display = 'flex';
        contentEl.style.display = 'none';
        return;
    }

    restrictionEl.style.display = 'none';
    contentEl.style.display = 'block';
    contentEl.innerHTML = '<div class="loading-state">데이터 로딩 중...</div>';

    try {
        // [BUG FIX 3] 타임아웃 적용
        const data = await invokeWithTimeout('get_market_overview', {
            accessToken: auth.accessToken || ''
        }, 10000);

        if (!data) {
            contentEl.innerHTML = '<div class="error-state"><p>데이터를 불러올 수 없습니다</p><button class="btn btn-sm btn-primary" onclick="loadMarketKr()">다시 시도</button></div>';
            return;
        }

        // 지수 카드 + 투자자 동향 UI 렌더링
        contentEl.innerHTML = `
            <div class="market-grid">
                <div class="index-card" id="kr-index-kospi"></div>
                <div class="index-card" id="kr-index-kosdaq"></div>
            </div>
            <div class="market-signal" id="market-signal-kr"></div>
            <div class="investor-section card">
                <h3>투자자별 순매수</h3>
                <div class="investor-grid">
                    <div class="investor-item"><span class="label">외국인</span><span class="value" id="kr-investor-foreign">-</span></div>
                    <div class="investor-item"><span class="label">기관</span><span class="value" id="kr-investor-institution">-</span></div>
                    <div class="investor-item"><span class="label">개인</span><span class="value" id="kr-investor-individual">-</span></div>
                </div>
            </div>
            <div class="sector-section card">
                <h3>주도 섹터 TOP 5</h3>
                <div class="sector-list" id="kr-sector-list"></div>
            </div>
        `;

        // 지수 카드
        const indices = data.indices || {};
        updateIndexCard('kr-index-kospi', indices.kospi);
        updateIndexCard('kr-index-kosdaq', indices.kosdaq);

        // 시장 신호
        const kospiChange = indices.kospi?.change_percent || data.summary?.kospi_change || 0;
        const signalEl = document.getElementById('market-signal-kr');
        if (signalEl) {
            if (kospiChange > 0.5) {
                signalEl.innerHTML = '<span class="signal-emoji">🟢</span><span class="signal-text">시장 상태: 매수 적합</span>';
            } else if (kospiChange < -0.5) {
                signalEl.innerHTML = '<span class="signal-emoji">🔴</span><span class="signal-text">시장 상태: 매수 부적합</span>';
            } else {
                signalEl.innerHTML = '<span class="signal-emoji">🟡</span><span class="signal-text">시장 상태: 중립</span>';
            }
        }

        // 투자자 동향
        const investor = data.investor || {};
        document.getElementById('kr-investor-foreign').textContent = formatBillions(investor.foreign || investor.foreign_net || 0);
        document.getElementById('kr-investor-institution').textContent = formatBillions(investor.institution || investor.institution_net || 0);
        document.getElementById('kr-investor-individual').textContent = formatBillions(investor.individual || investor.individual_net || 0);

        // 섹터 리스트
        const sectors = data.sectors || [];
        const sectorListEl = document.getElementById('kr-sector-list');
        if (sectorListEl) {
            if (sectors.length > 0) {
                sectorListEl.innerHTML = sectors.slice(0, 5).map(s => `
                    <div class="sector-item">
                        <span class="sector-name">${s.name}</span>
                        <span class="sector-change ${(s.change_percent || 0) >= 0 ? 'profit' : 'loss'}">
                            ${(s.change_percent || 0) >= 0 ? '+' : ''}${(s.change_percent || 0).toFixed(2)}%
                        </span>
                    </div>
                `).join('');
            } else {
                sectorListEl.innerHTML = '<div class="empty-state">섹터 데이터 없음</div>';
            }
        }

    } catch (error) {
        console.error('Market KR error:', error);
        contentEl.innerHTML = '<div class="error-state"><p>데이터를 불러올 수 없습니다</p><button class="btn btn-sm btn-primary" onclick="loadMarketKr()">다시 시도</button></div>';
    }
}

// 해외시장 로드
async function loadMarketUs() {
    const restrictionEl = document.getElementById('market-us-restriction');
    const contentEl = document.getElementById('market-us-content');
    if (!restrictionEl || !contentEl) return;

    // auth.user가 없으면 먼저 로드 시도
    if (!auth.user && auth.accessToken) {
        await loadUserInfo();
    }

    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';
    const isPro = ['pro', 'premium'].includes(plan) || role === 'admin';

    if (!isPro) {
        restrictionEl.style.display = 'flex';
        contentEl.style.display = 'none';
        return;
    }

    restrictionEl.style.display = 'none';
    contentEl.style.display = 'block';
    contentEl.innerHTML = '<div class="loading-state">데이터 로딩 중...</div>';

    try {
        // [BUG FIX 3] Yahoo Finance API 직접 호출
        const data = await invokeWithTimeout('get_market_overview', {
            accessToken: auth.accessToken || ''
        }, 10000);

        if (!data) {
            contentEl.innerHTML = '<div class="error-state"><p>데이터를 불러올 수 없습니다</p><button class="btn btn-sm btn-primary" onclick="loadMarketUs()">다시 시도</button></div>';
            return;
        }

        // UI 렌더링
        contentEl.innerHTML = `
            <div class="market-grid us-grid">
                <div class="index-card" id="us-index-sp500"></div>
                <div class="index-card" id="us-index-nasdaq"></div>
                <div class="index-card" id="us-index-dow"></div>
            </div>
            <div class="us-stocks-section card">
                <h3>주요 종목</h3>
                <table class="data-table">
                    <thead><tr><th>종목</th><th>현재가</th><th>등락률</th><th>거래량</th></tr></thead>
                    <tbody id="us-stocks-tbody"></tbody>
                </table>
            </div>
        `;

        // 지수 카드
        const indices = data.indices || {};
        updateIndexCard('us-index-sp500', indices.sp500 || indices['^GSPC']);
        updateIndexCard('us-index-nasdaq', indices.nasdaq || indices['^IXIC']);
        updateIndexCard('us-index-dow', indices.dow || indices['^DJI']);

        // 주요 종목 표시
        const topStocks = data.top_stocks || [];
        const tbody = document.getElementById('us-stocks-tbody');
        if (tbody) {
            if (topStocks.length > 0) {
                tbody.innerHTML = topStocks.slice(0, 10).map(s => {
                    const changeClass = (s.change_percent || 0) >= 0 ? 'profit' : 'loss';
                    return `
                        <tr class="clickable" data-symbol="${s.symbol}" data-exchange="kis_us">
                            <td><strong>${s.symbol}</strong> <span class="text-muted">${s.name || ''}</span></td>
                            <td>$${(s.price || 0).toLocaleString()}</td>
                            <td class="${changeClass}">${(s.change_percent || 0) >= 0 ? '+' : ''}${(s.change_percent || 0).toFixed(2)}%</td>
                            <td>${formatVolume(s.volume || 0)}</td>
                        </tr>
                    `;
                }).join('');

                // 클릭 이벤트
                tbody.querySelectorAll('tr.clickable').forEach(row => {
                    row.addEventListener('click', () => openStockDetail(row.dataset.symbol, 'kis_us'));
                });
            } else {
                tbody.innerHTML = '<tr><td colspan="4" class="empty-cell">데이터 없음</td></tr>';
            }
        }

    } catch (error) {
        console.error('Market US error:', error);
        contentEl.innerHTML = '<div class="error-state"><p>데이터를 불러올 수 없습니다</p><button class="btn btn-sm btn-primary" onclick="loadMarketUs()">다시 시도</button></div>';
    }
}

// [BUG FIX 6] ETF 로드 - 스탁이지 수준 개선
async function loadMarketEtf() {
    const restrictionEl = document.getElementById('market-etf-restriction');
    const contentEl = document.getElementById('market-etf-content');
    if (!restrictionEl || !contentEl) return;

    // auth.user가 없으면 먼저 로드 시도
    if (!auth.user && auth.accessToken) {
        await loadUserInfo();
    }

    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';
    const isPro = ['pro', 'premium'].includes(plan) || role === 'admin';

    if (!isPro) {
        restrictionEl.style.display = 'flex';
        contentEl.style.display = 'none';
        return;
    }

    restrictionEl.style.display = 'none';
    contentEl.style.display = 'block';
    contentEl.innerHTML = '<div class="loading-state">데이터 로딩 중...</div>';

    try {
        const data = await invokeWithTimeout('get_market_etf', {
            accessToken: auth.accessToken || '',
            sector: 'all'
        }, 10000);

        if (!data || !data.success) {
            contentEl.innerHTML = '<div class="error-state"><p>데이터를 불러올 수 없습니다</p><button class="btn btn-sm btn-primary" onclick="loadMarketEtf()">다시 시도</button></div>';
            return;
        }

        // 섹터별 ETF 지도 UI
        const sectors = data.sector_summary || [];
        const etfs = data.etfs || [];
        const topVolume = data.top_volume || [];

        contentEl.innerHTML = `
            <div class="etf-sector-map">
                <h3>섹터별 ETF 지도</h3>
                <div class="sector-cards-grid" id="etf-sector-cards"></div>
            </div>
            <div class="etf-detail-section card" id="etf-sector-detail" style="display:none;">
                <h3 id="etf-detail-title">섹터 상세</h3>
                <table class="data-table">
                    <thead><tr><th>ETF명</th><th>코드</th><th>현재가</th><th>등락률</th><th>거래대금</th></tr></thead>
                    <tbody id="etf-detail-tbody"></tbody>
                </table>
            </div>
            <div class="etf-flow-section card">
                <h3>거래대금 상위 ETF</h3>
                <table class="data-table">
                    <thead><tr><th>ETF명</th><th>현재가</th><th>등락률</th><th>거래대금</th></tr></thead>
                    <tbody id="etf-top-volume-tbody"></tbody>
                </table>
            </div>
        `;

        // 섹터 카드 렌더링
        const sectorCardsEl = document.getElementById('etf-sector-cards');
        if (sectorCardsEl) {
            sectorCardsEl.innerHTML = sectors.map(s => {
                const changeClass = s.avg_change >= 0 ? 'profit' : 'loss';
                const arrow = s.avg_change >= 0 ? '▲' : '▼';
                return `
                    <div class="sector-card" data-sector="${s.sector}">
                        <div class="sector-name">${s.sector}</div>
                        <div class="sector-etf-info">${s.top_etf}</div>
                        <div class="sector-change ${changeClass}">${arrow} ${Math.abs(s.avg_change).toFixed(2)}%</div>
                        <div class="sector-count">${s.count}개 ETF</div>
                    </div>
                `;
            }).join('');

            // 섹터 카드 클릭 이벤트
            sectorCardsEl.querySelectorAll('.sector-card').forEach(card => {
                card.addEventListener('click', () => {
                    const sector = card.dataset.sector;
                    const filtered = etfs.filter(e => e.sector === sector);
                    showEtfSectorDetail(sector, filtered);
                });
            });
        }

        // 거래대금 상위 ETF
        const topVolumeEl = document.getElementById('etf-top-volume-tbody');
        if (topVolumeEl) {
            topVolumeEl.innerHTML = topVolume.slice(0, 10).map(e => {
                const changeClass = (e.change_percent || 0) >= 0 ? 'profit' : 'loss';
                return `
                    <tr class="clickable" data-code="${e.code}">
                        <td><strong>${e.name}</strong></td>
                        <td>${(e.price || 0).toLocaleString()}</td>
                        <td class="${changeClass}">${(e.change_percent || 0) >= 0 ? '+' : ''}${(e.change_percent || 0).toFixed(2)}%</td>
                        <td>${formatBillions(e.volume || 0)}</td>
                    </tr>
                `;
            }).join('') || '<tr><td colspan="4" class="empty-cell">데이터 없음</td></tr>';
        }

    } catch (error) {
        console.error('Market ETF error:', error);
        contentEl.innerHTML = '<div class="error-state"><p>데이터를 불러올 수 없습니다</p><button class="btn btn-sm btn-primary" onclick="loadMarketEtf()">다시 시도</button></div>';
    }
}

function showEtfSectorDetail(sector, etfs) {
    const detailEl = document.getElementById('etf-sector-detail');
    const titleEl = document.getElementById('etf-detail-title');
    const tbody = document.getElementById('etf-detail-tbody');

    if (!detailEl || !tbody) return;

    titleEl.textContent = `${sector} 섹터 ETF`;
    detailEl.style.display = 'block';

    tbody.innerHTML = etfs.map(e => {
        const changeClass = (e.change_percent || 0) >= 0 ? 'profit' : 'loss';
        return `
            <tr class="clickable" data-code="${e.code}">
                <td><strong>${e.name}</strong></td>
                <td>${e.code}</td>
                <td>${(e.price || 0).toLocaleString()}</td>
                <td class="${changeClass}">${(e.change_percent || 0) >= 0 ? '+' : ''}${(e.change_percent || 0).toFixed(2)}%</td>
                <td>${formatBillions(e.volume || 0)}</td>
            </tr>
        `;
    }).join('') || '<tr><td colspan="5" class="empty-cell">해당 섹터의 ETF가 없습니다</td></tr>';
}

// 코인시장 로드
async function loadMarketCrypto() {
    const restrictionEl = document.getElementById('market-crypto-restriction');
    const contentEl = document.getElementById('market-crypto-content');
    if (!restrictionEl || !contentEl) return;

    // auth.user가 없으면 먼저 로드 시도
    if (!auth.user && auth.accessToken) {
        await loadUserInfo();
    }

    const plan = auth.user?.plan || 'free';
    const role = auth.user?.role || 'user';
    const isPro = ['pro', 'premium'].includes(plan) || role === 'admin';

    if (!isPro) {
        restrictionEl.style.display = 'flex';
        contentEl.style.display = 'none';
        return;
    }

    restrictionEl.style.display = 'none';
    contentEl.style.display = 'block';
    contentEl.innerHTML = '<div class="loading-state">데이터 로딩 중...</div>';

    try {
        // [BUG FIX 3] 거래소 API 직접 연동
        const data = await invokeWithTimeout('get_market_crypto', {
            accessToken: auth.accessToken || '',
            exchange: 'all'
        }, 10000);

        if (!data || !data.success) {
            contentEl.innerHTML = '<div class="error-state"><p>데이터를 불러올 수 없습니다</p><button class="btn btn-sm btn-primary" onclick="loadMarketCrypto()">다시 시도</button></div>';
            return;
        }

        // UI 렌더링
        const globalData = data.global || {};
        const kimchi = data.kimchi_premium;
        const coins = data.coins || [];

        contentEl.innerHTML = `
            <div class="crypto-summary-cards">
                <div class="crypto-card">
                    <div class="card-label">BTC 도미넌스</div>
                    <div class="card-value">${globalData.btc_dominance || '-'}%</div>
                </div>
                <div class="crypto-card">
                    <div class="card-label">ETH 도미넌스</div>
                    <div class="card-value">${globalData.eth_dominance || '-'}%</div>
                </div>
                <div class="crypto-card">
                    <div class="card-label">김치 프리미엄</div>
                    <div class="card-value ${kimchi >= 0 ? 'profit' : 'loss'}">${kimchi !== null ? (kimchi >= 0 ? '+' : '') + kimchi.toFixed(2) + '%' : '-'}</div>
                </div>
                <div class="crypto-card">
                    <div class="card-label">총 시가총액</div>
                    <div class="card-value">$${formatBillions(globalData.total_market_cap || 0)}</div>
                </div>
            </div>
            <div class="exchange-filter crypto-exchange-filter">
                <button class="filter-btn active" data-exchange="all">전체</button>
                <button class="filter-btn" data-exchange="binance">Binance</button>
                <button class="filter-btn" data-exchange="upbit">Upbit</button>
            </div>
            <div class="crypto-list-section card">
                <h3>코인 시세</h3>
                <table class="data-table">
                    <thead><tr><th>코인</th><th>거래소</th><th>현재가</th><th>24h 등락률</th><th>거래량</th></tr></thead>
                    <tbody id="crypto-tbody"></tbody>
                </table>
            </div>
        `;

        // 거래소 필터 이벤트
        contentEl.querySelectorAll('.crypto-exchange-filter .filter-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                contentEl.querySelectorAll('.crypto-exchange-filter .filter-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const exchange = btn.dataset.exchange;
                renderCryptoTable(exchange === 'all' ? coins : coins.filter(c => c.exchange === exchange));
            });
        });

        // 테이블 렌더링
        renderCryptoTable(coins);

    } catch (error) {
        console.error('Market Crypto error:', error);
        contentEl.innerHTML = '<div class="error-state"><p>데이터를 불러올 수 없습니다</p><button class="btn btn-sm btn-primary" onclick="loadMarketCrypto()">다시 시도</button></div>';
    }
}

function renderCryptoTable(coins) {
    const tbody = document.getElementById('crypto-tbody');
    if (!tbody) return;

    if (coins.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-cell">데이터 없음</td></tr>';
        return;
    }

    tbody.innerHTML = coins.slice(0, 30).map(c => {
        const changeClass = (c.change_percent || 0) >= 0 ? 'profit' : 'loss';
        const priceStr = c.exchange === 'upbit' && c.symbol?.includes('KRW')
            ? `₩${(c.price || 0).toLocaleString()}`
            : `$${(c.price || 0).toLocaleString()}`;

        return `
            <tr class="clickable" data-symbol="${c.symbol}" data-exchange="${c.exchange}">
                <td><strong>${c.symbol}</strong></td>
                <td><span class="exchange-badge ${c.exchange}">${c.exchange?.toUpperCase()}</span></td>
                <td>${priceStr}</td>
                <td class="${changeClass}">${(c.change_percent || 0) >= 0 ? '+' : ''}${(c.change_percent || 0).toFixed(2)}%</td>
                <td>${formatBillions(c.volume || 0)}</td>
            </tr>
        `;
    }).join('');

    // 클릭 이벤트
    tbody.querySelectorAll('tr.clickable').forEach(row => {
        row.addEventListener('click', () => openStockDetail(row.dataset.symbol, row.dataset.exchange));
    });
}

// =====================================================
// 종목분석 새 페이지 로드 (STEP A)
// =====================================================

// 국내주식 분석 로드
async function loadStockKr() {
    // 검색 자동완성 초기화
    initSearchAutocomplete('stock-kr-search', 'stock-kr-autocomplete', 'kr');
    renderRecentSearches();

    // 하위 탭 이벤트
    document.querySelectorAll('#stock-kr-tabs .sub-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#stock-kr-tabs .sub-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const tabId = tab.dataset.tab;
            document.getElementById('stock-kr-rs-section').style.display = tabId === 'rs' ? 'block' : 'none';
            document.getElementById('stock-kr-high52-section').style.display = tabId === 'high52' ? 'block' : 'none';
            document.getElementById('stock-kr-valuation-section').style.display = tabId === 'valuation' ? 'block' : 'none';
            document.getElementById('stock-kr-reports-section').style.display = tabId === 'reports' ? 'block' : 'none';
        });
    });

    // 검색 버튼 이벤트
    document.getElementById('btn-stock-kr-search')?.addEventListener('click', () => {
        const query = document.getElementById('stock-kr-search')?.value?.trim();
        if (query) {
            // 자동완성의 첫 번째 항목 클릭 시뮬레이션
            const firstItem = document.querySelector('#stock-kr-autocomplete .autocomplete-item');
            if (firstItem) {
                firstItem.click();
            } else {
                searchSymbols(query);
            }
        }
    });

    // RS 데이터 로드
    await loadRsData();

    // 테이블 행 클릭 이벤트 (종목 상세 열기)
    document.querySelectorAll('#rs-tbody tr, #high52-tbody tr, #valuation-tbody tr').forEach(row => {
        row.classList.add('clickable');
        row.addEventListener('click', () => {
            const symbol = row.dataset?.symbol;
            if (symbol) {
                openStockDetail(symbol, 'kis_kr');
            }
        });
    });
}

// RS 데이터 로드 (API 연동)
async function loadRsData() {
    const tbody = document.getElementById('rs-tbody');
    if (!tbody) return;

    tbody.innerHTML = '<tr><td colspan="9" class="empty-cell">RS 데이터 로딩 중...</td></tr>';

    try {
        const result = await invoke('get_analysis_rs', {
            accessToken: auth.accessToken || '',
            market: 'kospi'
        });

        const stocks = result?.stocks || [];
        if (stocks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="9" class="empty-cell">데이터가 없습니다</td></tr>';
            return;
        }

        tbody.innerHTML = stocks.map((s, idx) => {
            const changeVal = s.change || 0;
            const changeClass = changeVal >= 0 ? 'profit' : 'loss';
            const changeStr = changeVal >= 0 ? `+${changeVal.toFixed(2)}%` : `${changeVal.toFixed(2)}%`;
            const rsClass = s.rs_total >= 90 ? 'rs-high' : (s.rs_total >= 70 ? 'rs-mid' : 'rs-low');
            const priceStr = s.price ? s.price.toLocaleString() : '-';
            return `
                <tr class="clickable" data-symbol="${s.code}">
                    <td>${idx + 1}</td>
                    <td><strong>${s.name}</strong></td>
                    <td>${priceStr}</td>
                    <td class="${changeClass}">${changeStr}</td>
                    <td class="rs-score ${rsClass}">${s.rs_total || '-'}</td>
                    <td>${s.rs_1m || '-'}</td>
                    <td>${s.rs_3m || '-'}</td>
                    <td>${s.rs_6m || '-'}</td>
                    <td>-</td>
                </tr>
            `;
        }).join('');

        // 클릭 이벤트 바인딩
        tbody.querySelectorAll('tr.clickable').forEach(row => {
            row.addEventListener('click', () => {
                const symbol = row.dataset.symbol;
                if (symbol) openStockDetail(symbol, 'kis_kr');
            });
        });

    } catch (error) {
        console.error('RS 데이터 로드 실패:', error);
        tbody.innerHTML = '<tr><td colspan="9" class="empty-cell">데이터를 불러올 수 없습니다</td></tr>';
    }
}

// 해외주식 분석 로드
async function loadStockUs() {
    // 탭 이벤트
    document.querySelectorAll('#stock-us-tabs .sub-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            document.querySelectorAll('#stock-us-tabs .sub-tab').forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            const tabId = tab.dataset.tab;
            document.getElementById('stock-us-rs-section').style.display = tabId === 'us-rs' ? 'block' : 'none';
            document.getElementById('stock-us-valuation-section').style.display = tabId === 'us-valuation' ? 'block' : 'none';
        });
    });

    // 검색 이벤트
    const searchInput = document.getElementById('stock-us-search');
    searchInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const query = searchInput.value.trim();
            if (query) searchUsStock(query);
        }
    });

    document.getElementById('btn-stock-us-search')?.addEventListener('click', () => {
        const query = document.getElementById('stock-us-search')?.value?.trim();
        if (query) searchUsStock(query);
    });

    // 샘플 데이터 로드
    await loadUsRsData();
}

async function searchUsStock(query) {
    try {
        const result = await invoke('search_symbols', {
            accessToken: auth.accessToken || '',
            query: query,
            exchange: 'kis_us'
        });
        const symbols = result.symbols || result || [];
        if (symbols.length > 0) {
            openStockDetail(symbols[0].symbol, 'kis_us');
        } else {
            showToast('검색 결과가 없습니다', 'warning');
        }
    } catch (error) {
        showToast('검색 실패', 'error');
    }
}

async function loadUsRsData() {
    const tbody = document.getElementById('us-rs-tbody');
    if (!tbody) return;

    const sampleData = [
        { rank: 1, symbol: 'NVDA', name: 'NVIDIA Corp', price: '$875.28', change: '+4.21%', rs_total: 99, rs_1m: 98, rs_3m: 99 },
        { rank: 2, symbol: 'AAPL', name: 'Apple Inc', price: '$195.89', change: '+1.23%', rs_total: 95, rs_1m: 92, rs_3m: 96 },
        { rank: 3, symbol: 'MSFT', name: 'Microsoft Corp', price: '$428.50', change: '+0.85%', rs_total: 94, rs_1m: 93, rs_3m: 95 },
        { rank: 4, symbol: 'GOOGL', name: 'Alphabet Inc', price: '$175.98', change: '+2.15%', rs_total: 92, rs_1m: 94, rs_3m: 91 },
        { rank: 5, symbol: 'AMZN', name: 'Amazon.com Inc', price: '$185.63', change: '+1.78%', rs_total: 91, rs_1m: 89, rs_3m: 92 },
    ];

    tbody.innerHTML = sampleData.map(s => {
        const changeClass = s.change.startsWith('+') ? 'profit' : 'loss';
        const rsClass = s.rs_total >= 90 ? 'rs-high' : (s.rs_total >= 70 ? 'rs-mid' : 'rs-low');
        return `
            <tr class="clickable" data-symbol="${s.symbol}">
                <td>${s.rank}</td>
                <td><strong>${s.name}</strong> <span style="color:var(--text-muted)">${s.symbol}</span></td>
                <td>${s.price}</td>
                <td class="${changeClass}">${s.change}</td>
                <td class="rs-score ${rsClass}">${s.rs_total}</td>
                <td>${s.rs_1m}</td>
                <td>${s.rs_3m}</td>
            </tr>
        `;
    }).join('');

    tbody.querySelectorAll('tr.clickable').forEach(row => {
        row.addEventListener('click', () => {
            const symbol = row.dataset.symbol;
            if (symbol) openStockDetail(symbol, 'kis_us');
        });
    });
}

// ETF 분석 로드
async function loadStockEtf() {
    const searchInput = document.getElementById('stock-etf-search');
    searchInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const query = searchInput.value.trim();
            if (query) searchEtf(query);
        }
    });

    document.getElementById('btn-stock-etf-search')?.addEventListener('click', () => {
        const query = document.getElementById('stock-etf-search')?.value?.trim();
        if (query) searchEtf(query);
    });

    // 테마 필터 이벤트
    document.querySelectorAll('#stock-etf-theme .theme-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#stock-etf-theme .theme-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadEtfData(btn.dataset.theme);
        });
    });

    await loadEtfData('all');
}

async function searchEtf(query) {
    try {
        const result = await invoke('search_symbols', {
            accessToken: auth.accessToken || '',
            query: query,
            exchange: 'kis_kr'
        });
        const symbols = (result.symbols || result || []).filter(s =>
            s.name?.includes('ETF') || s.symbol?.includes('ETF')
        );
        if (symbols.length > 0) {
            openStockDetail(symbols[0].symbol, 'kis_kr');
        }
    } catch (error) {
        showToast('검색 실패', 'error');
    }
}

async function loadEtfData(theme = 'all') {
    const tbody = document.getElementById('stock-etf-tbody');
    if (!tbody) return;

    const sampleData = [
        { symbol: '069500', name: 'KODEX 200', price: '42,850', change: '+0.82%', nav: '25.5조', volume: '1,234억', theme: '대표' },
        { symbol: '229200', name: 'KODEX 코스닥150', price: '12,340', change: '+1.54%', nav: '3.2조', volume: '456억', theme: '코스닥' },
        { symbol: '305720', name: 'KODEX 2차전지산업', price: '18,650', change: '+2.31%', nav: '2.1조', volume: '892억', theme: '2차전지' },
        { symbol: '381170', name: 'TIGER AI코리아', price: '11,280', change: '+3.45%', nav: '1.5조', volume: '567억', theme: 'AI' },
        { symbol: '091160', name: 'KODEX 반도체', price: '35,200', change: '+1.87%', nav: '4.8조', volume: '2,345억', theme: '반도체' },
    ];

    const filtered = theme === 'all' ? sampleData : sampleData.filter(s => s.theme === theme);

    tbody.innerHTML = filtered.map(s => {
        const changeClass = s.change.startsWith('+') ? 'profit' : 'loss';
        return `
            <tr class="clickable" data-symbol="${s.symbol}">
                <td><strong>${s.name}</strong></td>
                <td>${s.price}</td>
                <td class="${changeClass}">${s.change}</td>
                <td>${s.nav}</td>
                <td>${s.volume}</td>
                <td><span class="theme-tag">${s.theme}</span></td>
            </tr>
        `;
    }).join('') || '<tr><td colspan="6" class="empty-cell">해당 테마의 ETF가 없습니다</td></tr>';

    tbody.querySelectorAll('tr.clickable').forEach(row => {
        row.addEventListener('click', () => {
            const symbol = row.dataset.symbol;
            if (symbol) openStockDetail(symbol, 'kis_kr');
        });
    });
}

// 코인 분석 로드
async function loadStockCrypto() {
    const searchInput = document.getElementById('stock-crypto-search');
    searchInput?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const query = searchInput.value.trim();
            if (query) searchCrypto(query);
        }
    });

    document.getElementById('btn-stock-crypto-search')?.addEventListener('click', () => {
        const query = document.getElementById('stock-crypto-search')?.value?.trim();
        if (query) searchCrypto(query);
    });

    // 거래소 필터 이벤트
    document.querySelectorAll('#stock-crypto-exchange .filter-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#stock-crypto-exchange .filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            loadCryptoData(btn.dataset.exchange);
        });
    });

    await loadCryptoData('all');
}

async function searchCrypto(query) {
    try {
        const result = await invoke('search_symbols', {
            accessToken: auth.accessToken || '',
            query: query,
            exchange: 'binance'
        });
        const symbols = result.symbols || result || [];
        if (symbols.length > 0) {
            openStockDetail(symbols[0].symbol, symbols[0].exchange || 'binance');
        }
    } catch (error) {
        showToast('검색 실패', 'error');
    }
}

async function loadCryptoData(exchange = 'all') {
    const tbody = document.getElementById('stock-crypto-tbody');
    if (!tbody) return;

    const sampleData = [
        { symbol: 'BTC-USDT', name: 'Bitcoin', exchange: 'binance', price: '$97,450', change: '+2.34%', volume: '$45.2B', marketCap: '$1.92T' },
        { symbol: 'ETH-USDT', name: 'Ethereum', exchange: 'binance', price: '$3,456', change: '+3.12%', volume: '$18.5B', marketCap: '$415B' },
        { symbol: 'SOL-USDT', name: 'Solana', exchange: 'okx', price: '$198.50', change: '+5.67%', volume: '$4.2B', marketCap: '$92B' },
        { symbol: 'BTC-KRW', name: '비트코인', exchange: 'upbit', price: '₩142,350,000', change: '+2.15%', volume: '₩1.2조', marketCap: '-' },
        { symbol: 'XRP-USDT', name: 'Ripple', exchange: 'bybit', price: '$2.45', change: '-1.23%', volume: '$2.8B', marketCap: '$138B' },
    ];

    const filtered = exchange === 'all' ? sampleData : sampleData.filter(s => s.exchange === exchange);

    tbody.innerHTML = filtered.map(s => {
        const changeClass = s.change.startsWith('+') ? 'profit' : 'loss';
        return `
            <tr class="clickable" data-symbol="${s.symbol}" data-exchange="${s.exchange}">
                <td><strong>${s.name}</strong> <span style="color:var(--text-muted)">${s.symbol}</span></td>
                <td><span class="exchange-badge ${s.exchange}">${s.exchange.toUpperCase()}</span></td>
                <td>${s.price}</td>
                <td class="${changeClass}">${s.change}</td>
                <td>${s.volume}</td>
                <td>${s.marketCap}</td>
            </tr>
        `;
    }).join('') || '<tr><td colspan="6" class="empty-cell">해당 거래소의 코인이 없습니다</td></tr>';

    tbody.querySelectorAll('tr.clickable').forEach(row => {
        row.addEventListener('click', () => {
            const symbol = row.dataset.symbol;
            const exchange = row.dataset.exchange;
            if (symbol) openStockDetail(symbol, exchange);
        });
    });
}

// =====================================================
// 관심종목 페이지 로드 (STEP A)
// =====================================================

async function loadWatchlist() {
    try {
        const result = await invoke('get_watchlist_items', {
            accessToken: auth.accessToken || '',
            groupId: 'default'
        });

        const items = result.items || [];
        const tbody = document.getElementById('watchlist-tbody');
        const countEl = document.getElementById('watchlist-count');

        if (countEl) countEl.textContent = items.length;

        if (tbody) {
            if (items.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="empty-cell">관심종목이 없습니다. 종목분석에서 ⭐ 버튼을 눌러 추가하세요.</td></tr>';
            } else {
                tbody.innerHTML = items.map(item => `
                    <tr>
                        <td>${item.name || item.symbol}</td>
                        <td>${item.price || '-'}</td>
                        <td class="${item.change >= 0 ? 'profit' : 'loss'}">${item.change >= 0 ? '+' : ''}${item.change || 0}%</td>
                        <td>${item.volume || '-'}</td>
                        <td>${item.memo || '-'}</td>
                        <td><button class="btn btn-sm btn-danger" data-id="${item.id}">삭제</button></td>
                    </tr>
                `).join('');
            }
        }

    } catch (error) {
        console.error('Watchlist error:', error);
    }
}

// 유틸리티 함수
function formatBillions(value) {
    if (value == null) return '-';
    const absVal = Math.abs(value);
    if (absVal >= 1e12) return `${(value / 1e12).toFixed(1)}조`;
    if (absVal >= 1e8) return `${(value / 1e8).toFixed(0)}억`;
    if (absVal >= 1e4) return `${(value / 1e4).toFixed(0)}만`;
    return value.toLocaleString();
}

// =====================================================
// STEP B: 캔들차트 + 검색 자동완성
// =====================================================

// 캔들차트 인스턴스
let detailChart = null;
let previewChart = null;
let currentStockData = null;

// 최근 검색 관리
const MAX_RECENT_SEARCHES = 5;

function getRecentSearches() {
    try {
        return JSON.parse(localStorage.getItem('bbooster_recent_searches') || '[]');
    } catch {
        return [];
    }
}

function addRecentSearch(symbol, name) {
    const recent = getRecentSearches();
    const existing = recent.findIndex(r => r.symbol === symbol);
    if (existing > -1) recent.splice(existing, 1);
    recent.unshift({ symbol, name });
    if (recent.length > MAX_RECENT_SEARCHES) recent.pop();
    localStorage.setItem('bbooster_recent_searches', JSON.stringify(recent));
    renderRecentSearches();
}

function renderRecentSearches() {
    const container = document.getElementById('recent-items-kr');
    if (!container) return;

    const recent = getRecentSearches();
    if (recent.length === 0) {
        document.getElementById('recent-searches-kr')?.style.setProperty('display', 'none');
        return;
    }

    document.getElementById('recent-searches-kr')?.style.setProperty('display', 'flex');
    container.innerHTML = recent.map(r => `
        <span class="recent-item" data-symbol="${r.symbol}">${r.name || r.symbol}</span>
    `).join('');

    container.querySelectorAll('.recent-item').forEach(item => {
        item.addEventListener('click', () => {
            const symbol = item.dataset.symbol;
            openStockDetail(symbol, 'kis_kr');
        });
    });
}

// 검색 자동완성
let autocompleteTimeout = null;

function initSearchAutocomplete(inputId, autocompleteId, market = 'kr') {
    const input = document.getElementById(inputId);
    const autocomplete = document.getElementById(autocompleteId);
    if (!input || !autocomplete) return;

    input.addEventListener('input', () => {
        const query = input.value.trim();
        if (autocompleteTimeout) clearTimeout(autocompleteTimeout);

        if (query.length < 1) {
            autocomplete.style.display = 'none';
            return;
        }

        autocompleteTimeout = setTimeout(async () => {
            try {
                const exchange = market === 'kr' ? 'kis_kr' : (market === 'us' ? 'kis_us' : null);
                const result = await invoke('search_symbols', {
                    accessToken: auth.accessToken || '',
                    query: query,
                    exchange: exchange
                });

                const symbols = result.symbols || result || [];
                if (symbols.length === 0) {
                    autocomplete.style.display = 'none';
                    return;
                }

                autocomplete.innerHTML = symbols.slice(0, 8).map(s => {
                    const changeClass = (s.change || 0) >= 0 ? 'profit' : 'loss';
                    return `
                        <div class="autocomplete-item" data-symbol="${s.symbol}" data-exchange="${s.exchange}">
                            <div>
                                <span class="autocomplete-stock-name">${s.name || s.symbol}</span>
                                <span class="autocomplete-stock-code">${s.symbol}</span>
                            </div>
                            <div>
                                <span class="autocomplete-price">${s.price_formatted || '-'}</span>
                                <span class="autocomplete-change ${changeClass}">${s.change_formatted || ''}</span>
                            </div>
                        </div>
                    `;
                }).join('');

                autocomplete.style.display = 'block';

                autocomplete.querySelectorAll('.autocomplete-item').forEach(item => {
                    item.addEventListener('click', () => {
                        const symbol = item.dataset.symbol;
                        const exchange = item.dataset.exchange;
                        const name = item.querySelector('.autocomplete-stock-name')?.textContent;
                        input.value = name || symbol;
                        autocomplete.style.display = 'none';
                        addRecentSearch(symbol, name);
                        openStockDetail(symbol, exchange);
                    });
                });
            } catch (error) {
                console.error('Autocomplete error:', error);
                autocomplete.style.display = 'none';
            }
        }, 200);
    });

    // 외부 클릭 시 닫기
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !autocomplete.contains(e.target)) {
            autocomplete.style.display = 'none';
        }
    });

    // Enter 키 처리
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const firstItem = autocomplete.querySelector('.autocomplete-item');
            if (firstItem) {
                firstItem.click();
            }
        } else if (e.key === 'Escape') {
            autocomplete.style.display = 'none';
        }
    });
}

// 종목 상세 모달 열기
async function openStockDetail(symbol, exchange) {
    const modal = document.getElementById('stock-detail-modal');
    if (!modal) return;

    modal.style.display = 'flex';
    currentStockData = { symbol, exchange };

    // 로딩 상태 초기화
    const nameEl = document.getElementById('detail-stock-name');
    const codeEl = document.getElementById('detail-stock-code');
    const marketEl = document.getElementById('detail-stock-market');

    if (nameEl) nameEl.textContent = '로딩 중...';
    if (codeEl) codeEl.textContent = symbol || '';
    if (marketEl) marketEl.textContent = exchange?.toUpperCase() || '';

    try {
        // [BUG FIX 2] 종목 상세 정보 - 타임아웃 적용
        const response = await invokeWithTimeout('get_symbol_detail', {
            accessToken: auth.accessToken || '',
            symbol: symbol,
            exchange: exchange
        }, 10000);

        // [BUG FIX 2] 응답 파싱 - 다양한 형태 처리
        let detail = null;
        if (response) {
            // response가 직접 데이터인 경우
            if (typeof response === 'object' && response.name) {
                detail = response;
            }
            // response.data 형태인 경우
            else if (response.data && typeof response.data === 'object') {
                detail = response.data;
            }
            // response가 문자열인 경우 (JSON 파싱 시도)
            else if (typeof response === 'string') {
                try {
                    detail = JSON.parse(response);
                    if (detail.data) detail = detail.data;
                } catch {
                    detail = null;
                }
            }
        }

        if (detail && typeof detail === 'object' && detail.name) {
            updateStockDetailUI(detail);
            initCandleChart(symbol, exchange, '1D');
        } else {
            // 기본값 설정
            if (nameEl) nameEl.textContent = symbol || '-';
            showToast('종목 정보를 불러올 수 없습니다', 'warning');
        }
    } catch (error) {
        console.error('Failed to load stock detail:', error);
        if (nameEl) nameEl.textContent = symbol || '-';
        showToast('종목 정보를 불러올 수 없습니다', 'error');
    }
}

/**
 * [BUG FIX 2] 종목 상세 UI 업데이트 - 안전한 데이터 접근
 */
function updateStockDetailUI(detail) {
    // 안전한 값 추출 함수
    const safeString = (val) => {
        if (val === null || val === undefined) return '-';
        if (typeof val === 'object') return JSON.stringify(val) === '{}' ? '-' : String(val);
        return String(val);
    };

    const safeNumber = (val) => {
        if (val === null || val === undefined || val === '') return 0;
        const num = parseFloat(val);
        return isNaN(num) ? 0 : num;
    };

    const formatPrice = (val) => {
        const num = safeNumber(val);
        if (num === 0) return '-';
        return num.toLocaleString();
    };

    // 기본 정보
    const nameEl = document.getElementById('detail-stock-name');
    const codeEl = document.getElementById('detail-stock-code');
    const marketEl = document.getElementById('detail-stock-market');

    if (nameEl) nameEl.textContent = safeString(detail.name) || safeString(detail.symbol) || '-';
    if (codeEl) codeEl.textContent = safeString(detail.symbol) || safeString(detail.code) || '-';
    if (marketEl) marketEl.textContent = safeString(detail.market) || safeString(detail.exchange) || '-';

    // 가격 정보
    const priceEl = document.getElementById('detail-current-price');
    const price = safeNumber(detail.price) || safeNumber(detail.current_price);
    if (priceEl) priceEl.textContent = price > 0 ? formatPrice(price) : '-';

    // 등락률
    const changeEl = document.getElementById('detail-price-change');
    if (changeEl) {
        const change = safeNumber(detail.change);
        const changePercent = safeNumber(detail.change_percent) || safeNumber(detail.changePercent);

        if (change !== 0 || changePercent !== 0) {
            const sign = change >= 0 ? '+' : '';
            changeEl.textContent = `${sign}${change.toLocaleString()} (${sign}${changePercent.toFixed(2)}%)`;
            changeEl.className = `price-change ${change >= 0 ? 'profit' : 'loss'}`;
        } else {
            changeEl.textContent = '-';
            changeEl.className = 'price-change';
        }
    }

    // 시가/고가/저가/거래량
    const openEl = document.getElementById('detail-open');
    const highEl = document.getElementById('detail-high');
    const lowEl = document.getElementById('detail-low');
    const volumeEl = document.getElementById('detail-volume');

    if (openEl) openEl.textContent = formatPrice(detail.open);
    if (highEl) highEl.textContent = formatPrice(detail.high);
    if (lowEl) lowEl.textContent = formatPrice(detail.low);
    if (volumeEl) volumeEl.textContent = formatVolume(safeNumber(detail.volume)) || '-';

    // 종합 정보
    const marketCapEl = document.getElementById('detail-market-cap');
    if (marketCapEl) marketCapEl.textContent = formatBillions(safeNumber(detail.market_cap)) || '-';
    document.getElementById('detail-high52').textContent = detail.high52?.toLocaleString() || '-';
    document.getElementById('detail-low52').textContent = detail.low52?.toLocaleString() || '-';
    document.getElementById('detail-rs').textContent = detail.rs || '-';
    document.getElementById('detail-sector1').textContent = detail.sector1 || '-';
    document.getElementById('detail-sector2').textContent = detail.sector2 || '-';

    // 밸류에이션
    document.getElementById('detail-per').textContent = detail.per || '-';
    document.getElementById('detail-per-e1').textContent = detail.per_e1 || '-';
    document.getElementById('detail-per-e2').textContent = detail.per_e2 || '-';
    document.getElementById('detail-pbr').textContent = detail.pbr || '-';
    document.getElementById('detail-psr').textContent = detail.psr || '-';
    document.getElementById('detail-div-yield').textContent = detail.div_yield ? `${detail.div_yield}%` : '-';

    // 재무
    document.getElementById('detail-revenue').textContent = formatBillions(detail.revenue) || '-';
    document.getElementById('detail-operating').textContent = formatBillions(detail.operating_income) || '-';
    document.getElementById('detail-net-income').textContent = formatBillions(detail.net_income) || '-';
    document.getElementById('detail-roe').textContent = detail.roe ? `${detail.roe}%` : '-';
    document.getElementById('detail-debt-ratio').textContent = detail.debt_ratio ? `${detail.debt_ratio}%` : '-';
    document.getElementById('detail-eps').textContent = detail.eps?.toLocaleString() || '-';
}

function formatVolume(volume) {
    if (!volume) return '-';
    if (volume >= 1e8) return `${(volume / 1e8).toFixed(0)}억`;
    if (volume >= 1e4) return `${(volume / 1e4).toFixed(0)}만`;
    return volume.toLocaleString();
}

// 캔들차트 초기화 (TradingView Lightweight Charts)
async function initCandleChart(symbol, exchange, period = '1D') {
    const container = document.getElementById('candle-chart');
    if (!container) return;

    // 기존 차트 제거
    container.innerHTML = '';

    // LightweightCharts 사용 가능 확인
    if (typeof LightweightCharts === 'undefined') {
        container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);">차트 라이브러리 로딩 중...</div>';
        return;
    }

    try {
        // 차트 생성
        detailChart = LightweightCharts.createChart(container, {
            width: container.clientWidth,
            height: 350,
            layout: {
                background: { color: '#0D1525' },
                textColor: '#9CA3AF'
            },
            grid: {
                vertLines: { color: '#22304A' },
                horzLines: { color: '#22304A' }
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal
            },
            rightPriceScale: {
                borderColor: '#22304A'
            },
            timeScale: {
                borderColor: '#22304A',
                timeVisible: true,
                secondsVisible: false
            }
        });

        // 캔들스틱 시리즈 추가
        const candleSeries = detailChart.addCandlestickSeries({
            upColor: '#22C55E',
            downColor: '#EF4444',
            borderUpColor: '#22C55E',
            borderDownColor: '#EF4444',
            wickUpColor: '#22C55E',
            wickDownColor: '#EF4444'
        });

        // 샘플 데이터 (실제로는 API에서 가져와야 함)
        const sampleData = generateSampleCandleData(period);
        candleSeries.setData(sampleData);

        // 거래량 시리즈
        const volumeSeries = detailChart.addHistogramSeries({
            color: '#3B82F6',
            priceFormat: { type: 'volume' },
            priceScaleId: '',
            scaleMargins: { top: 0.8, bottom: 0 }
        });

        const volumeData = sampleData.map(d => ({
            time: d.time,
            value: Math.random() * 1e6,
            color: d.close >= d.open ? '#22C55E44' : '#EF444444'
        }));
        volumeSeries.setData(volumeData);

        detailChart.timeScale().fitContent();

        // 리사이즈 핸들러
        const resizeObserver = new ResizeObserver(() => {
            detailChart?.resize(container.clientWidth, 350);
        });
        resizeObserver.observe(container);

    } catch (error) {
        console.error('Chart init error:', error);
        container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);">차트를 불러올 수 없습니다</div>';
    }
}

// 샘플 캔들 데이터 생성 (실제 API 연동 전 테스트용)
function generateSampleCandleData(period) {
    const data = [];
    const now = new Date();
    let numBars = 100;
    let timeStep = 24 * 60 * 60; // 1 day in seconds

    if (period === '1D') {
        numBars = 78; // 9:00 ~ 15:30, 5분봉
        timeStep = 5 * 60;
    } else if (period === '1W') {
        numBars = 5;
        timeStep = 24 * 60 * 60;
    } else if (period === '1M') {
        numBars = 22;
        timeStep = 24 * 60 * 60;
    } else if (period === '3M') {
        numBars = 65;
        timeStep = 24 * 60 * 60;
    } else if (period === '1Y') {
        numBars = 250;
        timeStep = 24 * 60 * 60;
    }

    let basePrice = 50000 + Math.random() * 50000;
    let startTime = Math.floor(now.getTime() / 1000) - (numBars * timeStep);

    for (let i = 0; i < numBars; i++) {
        const time = startTime + (i * timeStep);
        const volatility = basePrice * 0.02;
        const open = basePrice + (Math.random() - 0.5) * volatility;
        const close = open + (Math.random() - 0.5) * volatility;
        const high = Math.max(open, close) + Math.random() * volatility * 0.5;
        const low = Math.min(open, close) - Math.random() * volatility * 0.5;

        data.push({
            time: time,
            open: Math.round(open),
            high: Math.round(high),
            low: Math.round(low),
            close: Math.round(close)
        });

        basePrice = close;
    }

    return data;
}

// 종목 상세 모달 닫기
document.getElementById('stock-detail-modal-close')?.addEventListener('click', () => {
    document.getElementById('stock-detail-modal').style.display = 'none';
    if (detailChart) {
        detailChart.remove();
        detailChart = null;
    }
});

// 모달 외부 클릭 닫기
document.getElementById('stock-detail-modal')?.addEventListener('click', (e) => {
    if (e.target.id === 'stock-detail-modal') {
        document.getElementById('stock-detail-modal').style.display = 'none';
        if (detailChart) {
            detailChart.remove();
            detailChart = null;
        }
    }
});

// 차트 기간 탭 이벤트
document.querySelectorAll('.period-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const period = btn.dataset.period;
        if (currentStockData) {
            initCandleChart(currentStockData.symbol, currentStockData.exchange, period);
        }
    });
});

// 차트 타입 탭 이벤트
document.querySelectorAll('.type-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.type-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        // 라인/캔들 전환 로직 (추후 구현)
    });
});

// 종목 정보 탭 이벤트
document.querySelectorAll('.info-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.info-tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const tabId = tab.dataset.tab;
        document.getElementById('info-overview').style.display = tabId === 'overview' ? 'block' : 'none';
        document.getElementById('info-valuation').style.display = tabId === 'valuation' ? 'block' : 'none';
        document.getElementById('info-financial').style.display = tabId === 'financial' ? 'block' : 'none';
    });
});

// 관심종목 추가 버튼
document.getElementById('btn-add-to-watchlist')?.addEventListener('click', async () => {
    if (!currentStockData) return;
    try {
        await invoke('add_watchlist_item', {
            accessToken: auth.accessToken || '',
            groupId: 'default',
            symbol: currentStockData.symbol,
            exchange: currentStockData.exchange
        });
        showToast('관심종목에 추가되었습니다', 'success');
    } catch (error) {
        showToast('추가 실패: ' + error, 'error');
    }
});

// AI 분석 버튼
document.getElementById('btn-ai-analysis')?.addEventListener('click', () => {
    if (!currentStockData) return;
    document.getElementById('stock-detail-modal').style.display = 'none';
    // AI 분석 모달 열기 (기존 로직 활용)
    requestAiAnalysis(currentStockData.symbol);
});

// window에 openStockDetail 노출 (테이블 클릭에서 사용)
window.openStockDetail = openStockDetail;

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

    // 자동완성 초기화
    initAllAutocompletes();
    initPremiumStrategyAutocomplete();
})();

// Periodic status update
setInterval(() => {
    if (isConnected) {
        updateServerStatus(true);
    }
}, 5000);
